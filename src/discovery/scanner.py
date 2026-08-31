"""MCP 服務發現掃描器

功能：
- 埠掃描 (Python async socket)
- MCP 服務驗證 (JSON-RPC initialize)
- Tool 列表獲取 (tools/list)
- SSE 格式支援
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class MCPToolInfo:
    """MCP Tool 資訊"""
    name: str
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None


@dataclass
class MCPVerifyResult:
    """MCP 服務驗證結果"""
    success: bool
    protocol_version: Optional[str] = None
    server_name: Optional[str] = None
    server_version: Optional[str] = None
    server_description: Optional[str] = None  # 從 serverInfo.description 獲取（如果有）
    capabilities: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    response_time_ms: float = 0.0


@dataclass
class DiscoveredService:
    """發現的服務"""
    host: str
    port: int
    protocol: str = "http"
    mcp_path: str = "/mcp"
    verify_result: Optional[MCPVerifyResult] = None
    tools: List[MCPToolInfo] = field(default_factory=list)

    @property
    def requires_auth(self) -> bool:
        """判斷服務是否需要認證

        如果驗證結果顯示 "(requires auth)" 或有 401 錯誤，表示需要認證。
        如果有成功獲取 tools（不需要 auth_token），表示不需要認證。
        """
        if self.verify_result:
            # 如果 server_name 是 "(requires auth)"，表示服務返回 401
            if self.verify_result.server_name == "(requires auth)":
                return True
            # 如果有成功獲取 tools 且沒有提供 auth_token，表示不需要認證
            if self.tools:
                return False
        # 預設需要認證（較安全的假設）
        return True


class ScannerSSRFError(Exception):
    """連線目標位址被 SSRF 防護拒絕"""


def _resolve_validated_ip(host: str) -> Optional[str]:
    """SSRF 防護:解析 host、驗證每個 IP,回傳可安全連線的單一 IP。

    拒絕 link-local(含雲端 metadata 169.254.169.254)、multicast、reserved、
    unspecified(0.0.0.0)位址;允許 loopback / private(掃描本機 managed 服務
    與內網 MCP 服務是合法用途)。

    關鍵:回傳「已驗證的 IP」給呼叫端 pin 住連線,避免「驗證時解析→連線時再解析」
    之間的 DNS rebinding(第一次回良性 IP 過檢查,第二次回 metadata IP)。host 本身
    為 IP 字面值時直接驗證回傳。解析失敗回 None(交給連線階段的 timeout/error 處理,
    不誤殺)。對應整體安全審查 AUDIT-1(SSRF)。
    """
    import ipaddress as _ip
    import socket as _sock
    try:
        infos = _sock.getaddrinfo(host, None)
    except _sock.gaierror:
        return None
    validated = None
    for info in infos:
        addr = info[4][0].split('%')[0]  # 去除 IPv6 scope id
        try:
            ip = _ip.ip_address(addr)
        except ValueError:
            continue
        # loopback(127.0.0.1 / ::1)為合法的本機掃描目標,明確放行。
        # 注意:IPv6 的 ::1 在 Python 中 is_reserved 為 True,若不先放行會被下方 block
        # 誤殺——當 localhost 同時解析出 IPv4+IPv6 時(常見於容器/CI)即會踩到。
        if ip.is_loopback:
            if validated is None:
                validated = addr
            continue
        if ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ScannerSSRFError(
                f"Refusing to connect to disallowed address {addr} "
                f"(link-local / cloud-metadata / reserved addresses are blocked)"
            )
        if validated is None:
            validated = addr
    return validated


def _url_host(host: str) -> str:
    """組 URL 用的 host:IPv6 需加中括號。"""
    return f"[{host}]" if ":" in host else host


class MCPScanner:
    """MCP 服務掃描器"""

    def __init__(
        self,
        timeout: float = 5.0,
        max_concurrent: int = 50,
        rpc_timeout: Optional[float] = None,
    ):
        """初始化掃描器

        Args:
            timeout: **TCP 埠掃描**的連線超時(秒)。掃描動輒數百個埠且多數是
                關閉的,這裡必須短。
            max_concurrent: 最大同時連線數
            rpc_timeout: **MCP JSON-RPC 呼叫**(initialize / tools/list)的超時
                (秒)。與埠掃描是不同性質:對方可能正在冷啟動(容器內 npx/uvx
                首次要線上安裝套件),沿用埠掃描的短 timeout 會在對方回應前就
                中止連線 —— 實測會讓 supergateway 事後回寫時拋未捕捉例外而整個
                崩潰。預設較寬鬆,可用 MCP_RPC_TIMEOUT 調整。
        """
        self.timeout = timeout
        self.rpc_timeout = rpc_timeout if rpc_timeout is not None else _default_rpc_timeout()
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def scan_ports(
        self,
        host: str,
        ports: List[int]
    ) -> List[int]:
        """掃描開放的埠

        Args:
            host: 主機位址
            ports: 要掃描的埠列表

        Returns:
            開放的埠列表
        """
        # SSRF 防護(AUDIT-1):解析並驗證一次,pin 住 IP 連線(防 DNS rebinding)
        connect_host = _resolve_validated_ip(host) or host
        tasks = [self._check_port(connect_host, port) for port in ports]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        open_ports = []
        for port, result in zip(ports, results):
            if result is True:
                open_ports.append(port)

        return open_ports

    async def _check_port(self, host: str, port: int) -> bool:
        """檢查單一埠是否開放"""
        async with self._semaphore:
            try:
                # 使用 asyncio 建立 TCP 連線
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=self.timeout
                )
                writer.close()
                await writer.wait_closed()
                return True
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                return False
            except Exception as e:
                logger.debug(f"Port scan error {host}:{port}: {e}")
                return False

    async def _read_sse_message(self, response) -> Optional[Dict[str, Any]]:
        """從**仍開著的** SSE 串流增量讀出第一則 JSON-RPC 訊息就返回。

        Streamable HTTP 的回應多為 `text/event-stream` + chunked,且連線會
        保持開啟(伺服器之後可能繼續推送)。若用 `response.read()/text()`
        等「整個 body 結束」,對 SSE 而言永遠不會結束 —— 會一路等到逾時、
        連線被中斷,實測還會讓對端(supergateway)在回寫時因找不到連線而
        拋未捕捉例外整個崩潰。因此這裡逐塊讀,湊到一則完整訊息就停。
        """
        buf = ""
        try:
            async for chunk in response.content.iter_any():
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if not payload:
                            continue
                        try:
                            return json.loads(payload)
                        except json.JSONDecodeError:
                            continue  # 事件可能跨多行,繼續收
        except Exception as e:
            logger.debug(f"SSE incremental read ended: {e}")
        return None

    async def _read_jsonrpc(self, response) -> Optional[Dict[str, Any]]:
        """依 Content-Type 取出 JSON-RPC 回應(SSE 走增量讀,JSON 直接解析)。"""
        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" in content_type:
            return await self._read_sse_message(response)
        try:
            return await response.json()
        except Exception:
            return None

    async def verify_mcp_service(
        self,
        host: str,
        port: int,
        path: str = "/mcp",
        protocol: str = "http",
        auth_token: Optional[str] = None
    ) -> MCPVerifyResult:
        """驗證 MCP 服務

        使用 JSON-RPC initialize 請求驗證服務是否為有效的 MCP 服務。
        """
        # SSRF 防護(AUDIT-1):解析並驗證一次,pin 住 IP 連線(防 DNS rebinding),
        # 保留原始 Host header 讓 vhost 路由不受影響。
        connect_host = _resolve_validated_ip(host) or host
        url = f"{protocol}://{_url_host(connect_host)}:{port}{path}"
        start_time = time.time()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if connect_host != host:
            headers["Host"] = f"{host}:{port}"
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "mcp-center-scanner",
                    "version": "1.0.0"
                }
            }
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.rpc_timeout)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                    ssl=False
                ) as response:
                    elapsed_ms = (time.time() - start_time) * 1000
                    logger.info(f"MCP verify response: status={response.status}, content-type={response.headers.get('Content-Type', 'N/A')}")

                    # 處理非 200 狀態碼
                    # 注意：401 不能直接當作 MCP 服務，因為任何受保護的 HTTP 端點都可能返回 401
                    # 只有收到有效的 JSON-RPC 回應才能確認是 MCP 服務
                    if response.status == 401:
                        # 嘗試解析回應，看是否為 JSON-RPC 格式
                        try:
                            content_type = response.headers.get("Content-Type", "")
                            if "application/json" in content_type or "text/event-stream" in content_type:
                                body = await self._read_jsonrpc(response)
                                # 檢查是否為 JSON-RPC 格式的錯誤回應
                                if body and isinstance(body, dict) and ("jsonrpc" in body or "error" in body):
                                    return MCPVerifyResult(
                                        success=True,
                                        server_name="(requires auth)",
                                        error="Service requires authentication (401)",
                                        response_time_ms=elapsed_ms
                                    )
                        except Exception:
                            pass
                        # 非 JSON-RPC 格式的 401，不視為 MCP 服務
                        return MCPVerifyResult(
                            success=False,
                            error="HTTP 401 (not MCP - no JSON-RPC response)",
                            response_time_ms=elapsed_ms
                        )

                    if response.status != 200:
                        return MCPVerifyResult(
                            success=False,
                            error=f"HTTP {response.status}",
                            response_time_ms=elapsed_ms
                        )

                    # 處理 SSE 或 JSON 回應(SSE 必須增量讀 — 見 _read_sse_message)
                    result = await self._read_jsonrpc(response)

                    if not result:
                        return MCPVerifyResult(
                            success=False,
                            error="Empty response",
                            response_time_ms=elapsed_ms
                        )

                    if "error" in result:
                        return MCPVerifyResult(
                            success=False,
                            error=result["error"].get("message", str(result["error"])),
                            response_time_ms=elapsed_ms
                        )

                    if "result" in result:
                        init_result = result["result"]

                        # 驗證這是有效的 MCP initialize 回應
                        # MCP 回應必須包含 protocolVersion 和 serverInfo
                        protocol_version = init_result.get("protocolVersion")
                        server_info = init_result.get("serverInfo", {})
                        server_name = server_info.get("name")

                        # 至少需要 protocolVersion 或 serverInfo.name 才能確認是 MCP
                        if not protocol_version and not server_name:
                            return MCPVerifyResult(
                                success=False,
                                error="Response missing MCP indicators (no protocolVersion or serverInfo.name)",
                                response_time_ms=elapsed_ms
                            )

                        server_version = server_info.get("version")
                        server_description = init_result.get("instructions") or server_info.get("description")
                        logger.info(f"MCP service verified: name={server_name}, version={server_version}")
                        return MCPVerifyResult(
                            success=True,
                            protocol_version=protocol_version,
                            server_name=server_name,
                            server_version=server_version,
                            server_description=server_description,
                            capabilities=init_result.get("capabilities"),
                            response_time_ms=elapsed_ms
                        )

                    return MCPVerifyResult(
                        success=False,
                        error="Invalid response format",
                        response_time_ms=elapsed_ms
                    )

        except asyncio.TimeoutError:
            return MCPVerifyResult(
                success=False,
                error="Connection timeout",
                response_time_ms=(time.time() - start_time) * 1000
            )
        except aiohttp.ClientError as e:
            return MCPVerifyResult(
                success=False,
                error=f"Connection failed: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            logger.error(f"MCP verify error: {e}")
            return MCPVerifyResult(
                success=False,
                error=str(e),
                response_time_ms=(time.time() - start_time) * 1000
            )

    async def get_tools_list(
        self,
        host: str,
        port: int,
        path: str = "/mcp",
        protocol: str = "http",
        auth_token: Optional[str] = None
    ) -> List[MCPToolInfo]:
        """取得 MCP 服務的 Tool 列表（三步流程：initialize → initialized → tools/list）"""
        # SSRF 防護(AUDIT-1):解析並驗證一次,pin 住 IP 連線(防 DNS rebinding),
        # 保留原始 Host header 讓 vhost 路由不受影響。
        connect_host = _resolve_validated_ip(host) or host
        url = f"{protocol}://{_url_host(connect_host)}:{port}{path}"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if connect_host != host:
            headers["Host"] = f"{host}:{port}"
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            timeout = aiohttp.ClientTimeout(total=self.rpc_timeout)
            async with aiohttp.ClientSession() as session:
                # 步驟 1: Initialize
                init_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "mcp-center-scanner", "version": "1.0.0"}
                    }
                }

                async with session.post(
                    url, json=init_request, headers=headers, timeout=timeout, ssl=False
                ) as init_response:
                    if init_response.status == 401:
                        raise PermissionError("Service requires authentication. Please configure auth_token for this service.")
                    if init_response.status != 200:
                        return []

                    # 獲取 session ID(Streamable HTTP 的 session 由此 header 帶出)
                    session_id = init_response.headers.get("mcp-session-id")

                    # 讀出 initialize 回應。SSE 需增量讀:直接 read() 會等
                    # 串流結束而永遠卡住(見 _read_sse_message 的說明)。
                    await self._read_jsonrpc(init_response)

                # 步驟 2: 發送 initialized 通知
                initialized_notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {}
                }

                notify_headers = headers.copy()
                if session_id:
                    notify_headers["mcp-session-id"] = session_id

                async with session.post(
                    url, json=initialized_notification, headers=notify_headers, timeout=timeout, ssl=False
                ) as notify_response:
                    # 消耗 response body（即使不需要處理，也要讀取以避免連線問題）
                    await notify_response.read()

                # 步驟 3: 獲取工具列表
                tools_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                }

                tools_headers = headers.copy()
                if session_id:
                    tools_headers["mcp-session-id"] = session_id

                async with session.post(
                    url, json=tools_request, headers=tools_headers, timeout=timeout, ssl=False
                ) as response:
                    if response.status == 401:
                        raise PermissionError("Service requires authentication. Please configure auth_token for this service.")

                    if response.status == 200:
                        data = await self._read_jsonrpc(response)

                        if data and "result" in data and "tools" in data["result"]:
                            return [
                                MCPToolInfo(
                                    name=t.get("name", ""),
                                    description=t.get("description"),
                                    input_schema=t.get("inputSchema")
                                )
                                for t in data["result"]["tools"]
                            ]

        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Get tools list error: {e}")

        return []

    async def discover_services(
        self,
        hosts: List[str],
        ports: List[int],
        verify: bool = True,
        get_tools: bool = True,
        auth_token: Optional[str] = None
    ) -> List[DiscoveredService]:
        """發現 MCP 服務

        Args:
            hosts: 主機列表
            ports: 埠列表
            verify: 是否驗證 MCP 服務
            get_tools: 是否取得 Tool 列表
            auth_token: Bearer token (可選，用於需要認證的 MCP 服務)

        Returns:
            DiscoveredService 列表
        """
        discovered = []

        for host in hosts:
            # 掃描開放的埠
            open_ports = await self.scan_ports(host, ports)
            logger.info(f"Found {len(open_ports)} open ports on {host}: {open_ports}")

            # 驗證每個開放的埠
            for port in open_ports:
                service = DiscoveredService(
                    host=host,
                    port=port,
                    protocol="http"
                )

                if verify:
                    # 嘗試 HTTP
                    result = await self.verify_mcp_service(host, port, "/mcp", "http", auth_token)
                    if not result.success:
                        # 嘗試 HTTPS
                        result = await self.verify_mcp_service(host, port, "/mcp", "https", auth_token)
                        if result.success:
                            service.protocol = "https"

                    service.verify_result = result

                    # 只有在驗證成功且不需要認證時才獲取 tools
                    requires_auth = result.server_name == "(requires auth)"
                    if result.success and get_tools and not requires_auth:
                        try:
                            tools = await self.get_tools_list(
                                host, port, "/mcp", service.protocol, auth_token
                            )
                            service.tools = tools
                        except PermissionError:
                            # 服務需要認證，跳過 tools 獲取
                            pass

                # 只添加驗證成功的服務，或不驗證時添加所有服務
                if not verify or (service.verify_result and service.verify_result.success):
                    discovered.append(service)

        return discovered


# 全域 scanner instance
_scanner_instance: Optional[MCPScanner] = None


def _default_rpc_timeout() -> float:
    """MCP JSON-RPC 呼叫的預設 timeout(秒)。

    對方可能正在冷啟動(容器內 npx/uvx 首次需線上安裝),5 秒遠遠不夠。
    BYO 的冷啟動已由 orchestrator 暖機吸收,此處仍保留較寬鬆的預設作為防線。
    """
    import os as _os
    try:
        return float(_os.environ.get("MCP_RPC_TIMEOUT", "60"))
    except ValueError:
        return 60.0


def _default_scan_timeout() -> float:
    """掃描/驗證的預設 timeout(秒)。

    5s 對「已就緒」的服務綽綽有餘,但對冷啟動中的服務會太短。BYO 的冷啟動
    已由 orchestrator 的暖機吸收(見 Orchestrator._warmup_bridge),此處保留
    環境變數以便部署現場微調。
    """
    import os as _os
    try:
        return float(_os.environ.get("MCP_SCAN_TIMEOUT", "5"))
    except ValueError:
        return 5.0


def get_scanner() -> MCPScanner:
    """取得 MCPScanner singleton instance"""
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = MCPScanner(timeout=_default_scan_timeout())
    return _scanner_instance
