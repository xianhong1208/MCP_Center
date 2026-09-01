"""Managed MCP Orchestrator

啟動/停止/監控從 marketplace catalog 或使用者 BYO 定義安裝的 MCP container。
對外只透過 Orchestrator class 操作,in-memory state 由本類維護。

容器操作一律透過 docker SDK(docker-py)走 Docker Engine API,不 shell out
docker CLI —— 受汙染的參數以型別化參數送進 API,無 OS 命令 sink。

兩種 transport(來源由 LaunchSpec 統一,見 src/orchestrator/launch_spec):
  - http:image 自帶 HTTP server,直接跑。
  - stdio:受控基底 image 內的 supergateway 以 **Streamable HTTP** 橋接
    (POST /mcp + mcp-session-id;非舊版 HTTP+SSE —— 本專案 scanner 只講前者)。
    supergateway 在**容器內** spawn 內層 MCP 指令(npx/uvx/...),我方僅把
    「supergateway + 內層指令」以 list 傳給 docker SDK —— 無 shell、無 host
    subprocess(容器化橋接,消除當初被移除的 subprocess sink)。BYO 內層指令
    經 argv_policy 的 command 白名單 + args 字元白名單。

啟動流程(start):
  1. 從 DB 讀 process,從 catalog 讀對應 entry
  2. 解密 env vars
  3. 用 PortAllocator 分配 port(若 auto_port=True)
  4. docker SDK containers.run 啟動 sibling container
     (-p 127.0.0.1:<port>:<container_port>;image/args/command/env 由 catalog)
  5. 等 port listen 起來(http 30s / stdio 300s,見 _START_TIMEOUT_*)
  6. 抓 sibling container_id
  7. 自動建立 Service row(host=127.0.0.1, port=<port>,
     mcp_path=/mcp, requires_auth=false, source=managed)
  8. 更新 DB:port, container_id, service_id, actual_state=running

停止流程(stop):
  1. docker SDK 停止 + 強制移除 <container_name>
  2. 清 in-memory entry
  3. 更新 DB:actual_state=stopped, container_id=NULL

設計取捨:
  - in-memory dict 在 MCP Center 重啟後消失;reconcile() 會在 startup 時掃
    desired_state=running 但實際 stopped 的 process 並重啟(自我癒合)
  - 不在背景開 health check loop(由既有 health_monitor 透過 Service row 處理)
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import time
from threading import Lock
from typing import Dict, Optional

import docker
from docker import errors as docker_errors
from sqlalchemy.orm import Session

from src.adapters import ManagedMcpProcessAdapter, ServiceAdapter
from db.models import ManagedMcpProcess
from src.marketplace.argv_policy import (
    ArgvPolicyError,
    validate_byo_launch,
    validate_command_tokens,
    validate_docker_args,
    validate_image_ref,
)
from src.orchestrator.progress import get_progress_registry, process_key
from src.orchestrator.launch_spec import resolve_launch_spec
from src.orchestrator.port_allocator import PortAllocator

# supergateway 在容器內監聽 host,對外再 map 到 127.0.0.1:<host port>
_SUPERGATEWAY_BIN = "supergateway"
# stdio 橋接對外的 HTTP 路徑。使用 Streamable HTTP(非舊版 SSE),與本專案
# scanner / health check 所用的協定一致,因此與 http 型 image 同為 /mcp。
_STDIO_HTTP_PATH = "/mcp"

# 啟動後等待 port listening 的上限(秒)。
# http:image 已在本機,啟動只是跑起 process → 30s 足夠。
# stdio(BYO):容器內 npx/uvx 首次需**線上下載套件**再啟動,冷啟動常需數十秒
# 以上,沿用 30s 會讓首次部署幾乎必然逾時。兩者皆可用環境變數覆寫。
_START_TIMEOUT_HTTP = float(os.environ.get("MCP_START_TIMEOUT_HTTP", "30"))
_START_TIMEOUT_STDIO = float(os.environ.get("MCP_START_TIMEOUT_STDIO", "300"))

logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """Orchestrator 操作失敗"""


def _container_name(process_id: str) -> str:
    """sibling container 的名稱規則:固定前綴 + UUID 前 8 字元"""
    return f"mcp-managed-{process_id[:8]}"


def _flags_to_kwargs(flags):
    """把已通過 argv_policy 白名單的 `docker run` flag 序列,轉成 docker SDK
    `containers.run/create` 的 kwargs。

    只需處理 argv_policy._ALLOWED_* 內的 flag(其餘在驗證階段已被拒),因此
    對照是封閉且唯一的。回傳 (kwargs, pull_always)。
    """
    kwargs = {}
    pull_always = False
    i = 0
    while i < len(flags):
        tok = flags[i]
        # 無值 flag → docker SDK 的布林參數
        bool_flags = {
            "--rm": {"auto_remove": True},
            "-i": {"stdin_open": True},
            "-t": {"tty": True},
            "-it": {"stdin_open": True, "tty": True},
            "--init": {"init": True},
        }
        if tok in bool_flags:
            kwargs.update(bool_flags[tok])
            i += 1
            continue
        # 帶值 flag:支援 `--flag=value` 與 `--flag value` 兩式(argv_policy 已驗格式)
        flag, sep, inline = tok.partition("=")
        if sep:
            value = inline
            i += 1
        else:
            value = flags[i + 1]
            i += 2
        if flag == "--network":
            kwargs["network"] = value
        elif flag == "--memory":
            kwargs["mem_limit"] = value
        elif flag == "--cpus":
            kwargs["nano_cpus"] = int(float(value) * 1_000_000_000)
        elif flag == "--pull":
            pull_always = (value == "always")
    return kwargs, pull_always


class Orchestrator:
    """Managed MCP 啟停管理(singleton)

    所有 DB 寫入透過 ManagedMcpProcessAdapter;subprocess state 存 in-memory。
    Thread-safe via _lock(操作頻率不高,粗顆粒鎖足夠)。
    """

    def __init__(self, port_allocator: Optional[PortAllocator] = None):
        self.port_allocator = port_allocator or PortAllocator()
        self._subprocesses: Dict[str, subprocess.Popen] = {}
        self._lock = Lock()
        self._docker = None

    def _client(self):
        """取得(並快取)Docker Engine API client。

        改用 docker SDK(走 Docker socket)取代 shell out `docker` CLI:受汙染
        資料以型別化參數送進 API,不再組成 OS 命令字串 —— 從根本消除 command
        injection sink(SAST:Stored Command Injection)。
        """
        if self._docker is None:
            try:
                self._docker = docker.from_env()
            except docker_errors.DockerException as e:
                raise OrchestratorError(f"無法連線 Docker daemon: {e}") from e
        return self._docker

    # ---------- Public API ----------

    def image_exists(self, image_ref: str) -> bool:
        """檢查 docker image 是否已存在本機(docker SDK,不走 CLI)。"""
        try:
            self._client().images.get(image_ref)
            return True
        except docker_errors.ImageNotFound:
            return False

    def load_image(self, tar_path: str) -> list:
        """從 tar 檔載入 image(等同 `docker load -i`,但走 docker SDK)。

        Returns:
            載入的 image tags 清單(如 ["mit2i:v1.0.0"])。

        Raises:
            OrchestratorError: tar 不存在 / 格式錯誤 / daemon 錯誤。
        """
        try:
            with open(tar_path, "rb") as f:
                images = self._client().images.load(f)
        except FileNotFoundError as e:
            raise OrchestratorError(f"image tar 不存在: {tar_path}") from e
        except docker_errors.DockerException as e:
            raise OrchestratorError(f"docker load 失敗: {e}") from e
        tags = []
        for img in images:
            tags.extend(img.tags or [])
        logger.info(f"Image loaded from {tar_path}: tags={tags}")
        return tags

    def container_logs(self, process_id: str, tail: int = 200) -> str:
        """取得 container 的輸出(含已退出者)。

        容器崩潰後的死因只存在於它的 log,因此 BYO 不使用 --rm(auto_remove
        會連 log 一起刪掉);stop/uninstall 才明確移除。容器已不存在時回明確訊息
        而非拋錯 —— 呼叫端是除錯用途,不該因為查不到而失敗。
        """
        name = _container_name(process_id)
        try:
            container = self._client().containers.get(name)
        except docker_errors.NotFound:
            return f"(container '{name}' 不存在 —— 可能已被移除或從未建立)"
        except docker_errors.DockerException as e:
            return f"(無法連線 Docker: {e})"
        try:
            raw = container.logs(tail=tail, timestamps=True)
            status = container.status
        except docker_errors.DockerException as e:
            return f"(讀取 log 失敗: {e})"
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        return f"[container status: {status}]\n{text}"

    def start(self, db: Session, process_id: str) -> ManagedMcpProcess:
        """啟動一個 Managed MCP process

        若已在 _subprocesses 內(代表 in-memory 認為仍在跑),先 stop 再 start。
        """
        with self._lock, get_progress_registry().track(process_key(process_id), "start"):
            return self._start_locked(db, process_id)

    def stop(self, db: Session, process_id: str) -> ManagedMcpProcess:
        """停止 process(graceful → forceful)+ 清 sibling container"""
        with self._lock, get_progress_registry().track(process_key(process_id), "stop"):
            return self._stop_locked(db, process_id)

    def is_running(self, process_id: str) -> bool:
        """檢查 process 是否真的在跑。

        Docker 真實狀態優先,in-memory subprocess 只當輔助 — 因為 MCP Center
        重啟後 _subprocesses 會清空,但 sibling container 仍由 host daemon
        維護。先前的版本只查 in-memory 結果重啟時誤判 → 把活著的 container
        殺掉重起。
        """
        with self._lock:
            container_name = _container_name(process_id)
            # HTTP 模式:container 在跑就算 running(running_only 過濾掉 exited)
            if self._lookup_container_id(container_name, running_only=True):
                return True
            # stdio 模式:supergateway subprocess 還活著就算
            proc = self._subprocesses.get(process_id)
            if proc is not None:
                return proc.poll() is None
            return False

    def reconcile(self, db: Session) -> None:
        """啟動時呼叫:對齊 desired_state=running 的 process 與實際 docker 狀態。

        三種情境:
          (a) container 仍活著 → 補 in-memory sentinel,不重啟(零中斷)
          (b) container 不見 → 重新 start
          (c) start 失敗 → 標記 actual_state=failed
        """
        targets = ManagedMcpProcessAdapter.list_all(
            db, desired_state="running"
        )
        for p in targets:
            process_id = str(p.id)
            container_name = _container_name(process_id)
            cid = self._lookup_container_id(container_name, running_only=True)

            if cid:
                # (a) Container 還活著,只是 MCP Center 重啟掉了 in-memory state
                with self._lock:
                    # HTTP 模式 sentinel = None;stdio 模式重啟後 supergateway
                    # 子進程已成 orphan,無 Popen handle 可回收 — 仍放 None,
                    # 容忍 stdio 模式在這情境下無 SIGTERM 能力(下次 stop 走
                    # _force_remove_container 仍能清掉 container)
                    self._subprocesses.setdefault(process_id, None)
                logger.info(
                    f"Reconcile: recovered {p.name} ({process_id}), "
                    f"container {cid[:12]} still alive"
                )
                continue

            # (b) Container 真的不在 → 重啟
            try:
                logger.info(f"Reconcile: restarting managed process {p.name} ({process_id})")
                self.start(db, process_id)
            except Exception as e:
                # (c)
                logger.error(f"Reconcile failed for {process_id}: {e}")
                ManagedMcpProcessAdapter.update_state(
                    db, process_id,
                    actual_state="failed",
                    last_error=f"reconcile: {e}",
                )

    # ---------- Internal ----------

    def _start_locked(self, db: Session, process_id: str) -> ManagedMcpProcess:
        process = ManagedMcpProcessAdapter.get_by_id(db, process_id)
        if not process:
            raise OrchestratorError(f"Process {process_id} not found")

        # 解析啟動描述(catalog 檔 或 使用者 BYO 定義皆可)
        try:
            spec = resolve_launch_spec(db, process)
        except LookupError as e:
            raise OrchestratorError(str(e)) from e

        # 若已在 memory 中,先 stop
        if process_id in self._subprocesses:
            logger.info(f"Process {process_id} already in memory, stopping first")
            self._stop_locked(db, process_id)

        progress = get_progress_registry()
        pkey = process_key(process_id)

        # 1. 分配 port
        progress.stage(pkey, "allocating_port")
        if process.auto_port:
            port = self.port_allocator.allocate(db, exclude_process_id=process_id)
        else:
            if not process.port:
                raise OrchestratorError("auto_port=False but no port set")
            port = process.port

        # 2. 解密 env vars
        env_vars = process.get_env_vars()

        # 3. 從 LaunchSpec 取啟動參數(來源無關)
        transport = spec.transport
        container_port = spec.container_port
        container_name = _container_name(process_id)

        # 啟動前清除可能殘留的同名 container
        self._force_remove_container(container_name)

        image_ref = spec.image_ref
        image_args = " ".join(spec.run_flags) or "--rm"
        image_command = list(spec.entrypoint_args)  # http 分支用(catalog)

        # ------------------------------------------------------------------
        # 執行邊界的 argv 政策檢查(Stored Command/Argument Injection 防線)
        #
        # 上面三個值全部是從 DB 讀出來的(image_ref / image_args /
        # image_command,後者還經過 json.loads),接下來會直接展開成 `docker
        # run` 的 argv。install 時 DockerSpec 已經驗過 catalog,但這裡仍要
        # 再驗一次 — 不是多餘:
        #
        #   1. 這是 *Stored* injection。威脅模型包含「攻擊者已能寫 DB」
        #      (SQL injection、洩漏的 DB 憑證、內部誤用 CRUD)。那條路徑
        #      完全繞過 catalog,只驗寫入端等於沒防。
        #   2. 靜態掃描無法把「寫進 DB 前驗過」和「從 DB 讀出來用」連起來,
        #      sanitizer 必須實際出現在 DB 讀取與 subprocess 之間。
        #
        # 政策本身在 src/marketplace/argv_policy(與 DockerSpec 共用同一份)。
        # 驗不過就讓 start 失敗:呼叫端會標成 actual_state=failed 並寫
        # last_error,明確可見,而不是靜默改寫成「安全」的值。
        # ------------------------------------------------------------------
        # 依 transport 決定容器內要跑什麼,並在此(執行邊界)套 argv 政策:
        #   http  → 直接跑 image,command = 驗過的 entrypoint args
        #   stdio → 跑受控基底 image 內的 supergateway,橋接內層 MCP 指令
        #           (BYO:內層指令走 command 白名單 + args 字元白名單)
        # image_ref / docker flags 兩種都要驗。
        try:
            validate_image_ref(image_ref)
            image_args_tokens = validate_docker_args(image_args.split())
            if transport == "http":
                validated = validate_command_tokens(image_command)
                container_command = validated or None
            elif transport == "stdio":
                inner_cmd, inner_args = validate_byo_launch(
                    spec.stdio_command[0] if spec.stdio_command else "",
                    spec.stdio_command[1:] if spec.stdio_command else [],
                )
                # supergateway 在容器內 spawn 內層指令並橋接 stdio↔HTTP。
                # 我方僅把「supergateway + 內層指令」以 list 傳給 docker SDK,
                # 無 shell、無 host subprocess(消除當初被移除的 sink)。
                inner = " ".join([inner_cmd] + inner_args)
                # 輸出用 Streamable HTTP(而非 supergateway 預設的舊版 HTTP+SSE):
                # MCP 有兩種 HTTP 傳輸,本專案的 scanner/health check 講的是
                # Streamable HTTP(POST /mcp + mcp-session-id header)。舊版 SSE
                # 需要 GET /sse 開串流再 POST /message,scanner 不支援 —— 用預設
                # 會導致「位址對、協定不對」,服務永遠 offline 且抓不到 tools。
                # --stateful:以 session 保存 initialize 狀態,scanner 的三步流程
                # (initialize → initialized → tools/list)才成立;stateless 模式
                # 每次請求獨立,tools/list 會因未 initialize 而失敗。
                # supergateway 無 --host flag;app.listen(port) 已綁全介面,
                # 對外仍只綁 127.0.0.1(由 ports= 決定)。
                container_command = [
                    _SUPERGATEWAY_BIN, "--stdio", inner,
                    "--outputTransport", "streamableHttp",
                    "--stateful",
                    "--streamableHttpPath", _STDIO_HTTP_PATH,
                    "--port", str(container_port),
                ]
            else:
                raise ArgvPolicyError(f"不支援的 transport: {transport!r}")
        except ArgvPolicyError as e:
            logger.error(
                f"Refusing to start {process.name} ({process_id}): "
                f"docker argv 政策檢查失敗: {e}"
            )
            raise OrchestratorError(f"docker argv 政策檢查失敗: {e}") from e

        logger.info(
            f"Starting managed MCP {process.name}: "
            f"transport={transport}, port={port}, image={image_ref}, "
            f"env_count={len(env_vars)}"
        )

        # docker SDK 直接建立並啟動(取代 `docker run` shell-out)。受汙染資料
        # (image/command/env/flags)以型別化參數送進 Engine API,全程無 OS 命令
        # sink。stdio 也走 container(supergateway 在容器內 spawn 內層指令),
        # 與 http 共用同一條 docker SDK 路徑。argv_policy 白名單 flag → SDK kwargs。
        run_kwargs, pull_always = _flags_to_kwargs(image_args_tokens)

        # stdio 橋接的韌性:supergateway 在「client 先斷線、child 後回應」時會拋
        # 未捕捉例外而整個退出(上游 bug,實測可重現)。任何一次逾時的健康檢查
        # 都可能把橋接器打死,因此交給 docker 自動拉回。
        # 注意:restart_policy 與 auto_remove(--rm)互斥,故僅在未設 --rm 時套用
        # (BYO 已改用 --init,不帶 --rm)。
        if transport == "stdio" and not run_kwargs.get("auto_remove"):
            run_kwargs["restart_policy"] = {"Name": "on-failure", "MaximumRetryCount": 10}
        client = self._client()
        if pull_always:
            progress.stage(pkey, "pulling_image", image_ref)
            try:
                client.images.pull(image_ref)
            except docker_errors.DockerException as e:
                raise OrchestratorError(f"docker pull 失敗: {image_ref}: {e}") from e
        progress.stage(pkey, "creating_container", image_ref)
        try:
            client.containers.run(
                image_ref,
                command=container_command,
                name=container_name,
                detach=True,
                environment=dict(env_vars),
                ports={f"{container_port}/tcp": ("127.0.0.1", port)},
                **run_kwargs,
            )
            logger.info(f"Container started for {process.name}: {container_name}")
        except docker_errors.ImageNotFound as e:
            raise OrchestratorError(f"docker image not found: {image_ref}") from e
        except docker_errors.APIError as e:
            raise OrchestratorError(
                f"docker run failed: {getattr(e, 'explanation', None) or e}"
            ) from e

        # container 自己跑,無外部 bridge process;放一個 sentinel
        self._subprocesses[process_id] = None

        # 等 port 開始 listening。
        # stdio(BYO)首次啟動時,容器內的 npx/uvx 需**現場下載套件**,可能遠超過
        # http 模式(image 已在本機)的等待時間 —— 用較長的 timeout,否則首次部署
        # 幾乎必然逾時失敗。可用環境變數覆寫。
        start_timeout = _START_TIMEOUT_STDIO if transport == "stdio" else _START_TIMEOUT_HTTP
        progress.stage(pkey, "waiting_port", str(port))
        try:
            logger.info(
                f"Waiting up to {start_timeout:.0f}s for port {port} "
                f"({process.name}, transport={transport})"
            )
            self._wait_for_port("127.0.0.1", port, timeout=start_timeout)
            logger.info(f"Port {port} is listening for {process.name}")
        except TimeoutError as e:
            logger.error(f"Port {port} did not open for {process.name}: {e}")
            self._stop_locked(db, process_id)
            raise OrchestratorError(f"Port {port} did not open: {e}") from e

        # stdio 橋接:暖機一次,讓容器內的 npx/uvx 先完成下載與啟動。
        # supergateway 的 stateful 模式是「第一個請求進來才 spawn child」,
        # 而 npx 首次需線上安裝套件(數十秒)。若把這段成本留給後續的健康
        # 檢查(timeout 僅數秒),必然先斷線,supergateway 事後回寫還會因
        # 找不到連線而拋未捕捉例外整個崩潰(實測)。這裡用部署階段本就
        # 允許的長 timeout 先扛下來,之後的請求就都是熱的。
        if transport == "stdio":
            progress.stage(pkey, "warming_up")
            self._warmup_bridge(port, _STDIO_HTTP_PATH, start_timeout)

        # 撈 container_id
        sibling_container_id = self._lookup_container_id(container_name)
        logger.info(f"Container ID for {process.name}: {sibling_container_id}")

        # 自動建立 Service row(若還沒有)。
        # 路徑依 transport:http image 自帶 /mcp;stdio 經 supergateway → /sse。
        if transport == "stdio":
            mcp_path = _STDIO_HTTP_PATH   # supergateway 以 Streamable HTTP 對外
            description = f"自訂 MCP(BYO):{' '.join(spec.stdio_command)}"
        else:
            mcp_path = "/mcp"
            description = f"Managed via marketplace catalog '{process.catalog_id}'"
        progress.stage(pkey, "registering_service")
        service_id = self._ensure_service(
            db, process, port, mcp_path=mcp_path, description=description,
        )

        # 更新 DB
        updated = ManagedMcpProcessAdapter.update_state(
            db, process_id,
            actual_state="running",
            container_id=sibling_container_id or "",
            bridge_container_id="",
            port=port,
            service_id=str(service_id) if service_id else None,
            last_error="",
        )
        logger.info(
            f"Managed MCP started: name={process.name}, port={port}, "
            f"container={sibling_container_id}, service_id={service_id}"
        )
        return updated

    @staticmethod
    def _warmup_bridge(port: int, path: str, timeout: float) -> None:
        """對 stdio 橋接送一次 initialize,觸發並等待容器內的 child 真正就緒。

        Best-effort:失敗只記 log,不讓部署失敗 —— 暖機是效能與穩定性的最佳化,
        真正的健康狀態由既有的 health check 判定。
        """
        import json as _json

        body = _json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "mcp-center-warmup", "version": "1.0.0"},
            },
        })
        req = (
            f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            f"Content-Type: application/json\r\n"
            f"Accept: application/json, text/event-stream\r\n"
            f"Content-Length: {len(body)}\r\n\r\n{body}"
        ).encode()
        deadline = time.monotonic() + timeout
        sock = None
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=10)
            sock.sendall(req)
            sock.settimeout(min(30.0, timeout))
            buf = b""
            while time.monotonic() < deadline:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf += chunk
                if b"data:" in buf or b'"result"' in buf or b'"error"' in buf:
                    logger.info(f"Bridge warmup done on port {port}")
                    return
            logger.warning(f"Bridge warmup on port {port} did not complete within {timeout:.0f}s")
        except OSError as e:
            logger.warning(f"Bridge warmup on port {port} failed: {e}")
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

    def _stop_locked(self, db: Session, process_id: str) -> ManagedMcpProcess:
        process = ManagedMcpProcessAdapter.get_by_id(db, process_id)
        if not process:
            raise OrchestratorError(f"Process {process_id} not found")

        logger.info(f"Stopping managed MCP: name={process.name}, id={process_id}")
        # http 模式無外部 bridge process(sentinel=None);移除 in-memory entry
        self._subprocesses.pop(process_id, None)

        # 清 container(docker stop + docker rm -f)
        container_name = _container_name(process_id)
        logger.info(f"Stopping container: {container_name}")
        get_progress_registry().stage(process_key(process_id), "stopping_container")
        self._docker_stop_container(container_name)
        self._force_remove_container(container_name)
        logger.info(f"Managed MCP stopped: name={process.name}")

        # 更新 DB — 清 container refs 但保留 port(使用者設定不因 stop 消失)
        return ManagedMcpProcessAdapter.update_state(
            db, process_id,
            actual_state="stopped",
            container_id="",
            bridge_container_id="",
        )

    # ---------- Helpers ----------

    @staticmethod
    def _wait_for_port(host: str, port: int, timeout: float) -> None:
        """Poll until something is listening at host:port, or timeout."""
        deadline = time.monotonic() + timeout
        last_err = None
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, port), timeout=1.0):
                    return
            except OSError as e:
                last_err = e
                time.sleep(0.3)
        raise TimeoutError(
            f"Port {host}:{port} did not become listening within {timeout}s "
            f"(last={last_err})"
        )

    def _docker_stop_container(self, name: str) -> None:
        """停止指定 container(docker SDK),不存在或失敗都忽略。"""
        try:
            self._client().containers.get(name).stop(timeout=10)
        except docker_errors.NotFound:
            pass
        except docker_errors.DockerException as e:
            logger.debug(f"stop container {name} ignored: {e}")

    def _force_remove_container(self, name: str) -> None:
        """強制移除 container(docker SDK),不存在或失敗都忽略。"""
        try:
            self._client().containers.get(name).remove(force=True)
        except docker_errors.NotFound:
            pass
        except docker_errors.DockerException as e:
            logger.debug(f"remove container {name} ignored: {e}")

    def _lookup_container_id(self, name: str, running_only: bool = False) -> Optional[str]:
        """查 container ID,回傳第一個相符者或 None(docker SDK)。

        running_only=True:只回正在跑的;exited/created 視同沒有。
        running_only=False:含 stopped/exited,僅用於清殘留時辨識。
        filters name 為子字串比對,與原 `docker ps -f name=` 行為一致;
        container 名稱唯一(mcp-managed-<uuid8>),不會誤匹配。
        """
        try:
            matches = self._client().containers.list(
                all=not running_only, filters={"name": name}
            )
            return matches[0].id if matches else None
        except docker_errors.DockerException:
            return None

    @staticmethod
    def _ensure_service(
        db: Session, process: ManagedMcpProcess, port: int,
        mcp_path: str = "/mcp", description: Optional[str] = None,
    ):
        """為 Managed Process 自動建立(或更新)對應的 Service row

        Service 的 host=127.0.0.1, port=<bridge port>, requires_auth=False,
        source="managed"。下游 agent 用 127.0.0.1:port 直連(因為 MCP Center
        是 --network host,127.0.0.1 等同 host loopback)。

        mcp_path 由呼叫端依 transport 決定 —— http 的 image 自帶 /mcp;
        stdio 走 supergateway,端點是 /sse。寫死單一路徑會讓其中一種永遠連不上。
        """
        # 已有 service_id 就更新(port 與 path 都要,才能修好舊資料的錯誤路徑)
        if process.service_id:
            existing = ServiceAdapter.get_by_id(db, str(process.service_id))
            if existing:
                ServiceAdapter.update(db, str(existing.id), port=port, mcp_path=mcp_path)
                logger.info(
                    f"Updated existing Service {existing.id}: port={port}, mcp_path={mcp_path}"
                )
                return existing.id

        # 新建
        logger.info(f"Creating new Service for managed process {process.name}")
        svc = ServiceAdapter.create(
            db=db,
            name=process.name,
            description=description or f"Managed via marketplace catalog '{process.catalog_id}'",
            host="127.0.0.1",
            port=port,
            protocol="http",
            mcp_path=mcp_path,
            source="managed",
            requires_auth=False,  # 信任 host 本機網路,agent 直連無需 token
        )
        logger.info(f"Created Service {svc.id} for {process.name} at 127.0.0.1:{port}{mcp_path}")
        return svc.id


# -------- Singleton --------

_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
