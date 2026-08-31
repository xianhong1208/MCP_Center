"""Marketplace + Managed MCP API routes

Endpoints:
  GET  /api/marketplace                   列出所有 catalog 項目(含已安裝狀態)
  GET  /api/marketplace/{catalog_id}      catalog 詳情(用於前端 install 表單)
  POST /api/managed                       從 catalog 安裝 + (可選)立即啟動
  GET  /api/managed                       列出已安裝的 Managed MCP
  GET  /api/managed/progress              進行中長操作的目前階段(前端輪詢用)
  GET  /api/managed/{id}                  單一 Managed MCP 詳情
  PUT  /api/managed/{id}/env-vars         更新 env vars(running 中會自動重啟)
  POST /api/managed/{id}/start            啟動
  POST /api/managed/{id}/stop             停止
  DELETE /api/managed/{id}                uninstall(stop + 刪 row + 刪 Service)

所有端點需登入(session)。

Single instance 規則:目前一個 catalog_id 只允許一個 process(install 時檢查)。
若要改成多實例,移除 install 內的 409 檢查即可。
"""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db import get_db
from src.adapters import BYODefinitionAdapter, ManagedMcpProcessAdapter
from src.adapters.exceptions import AdapterError


def _adapter_http_exc(e: AdapterError) -> HTTPException:
    """AdapterError → HTTPException(managed 路由的 detail 格式:params 永遠存在)。"""
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "params": e.params, "fallback": e.fallback},
    )
from db.models import AdminUser
from src.api.schemas import (
    ByoCreateRequest,
    ByoDefinitionInfo,
    ByoDeployRequest,
    ByoListResponse,
    ManagedActionResponse,
    ManagedInstallRequest,
    ManagedListResponse,
    ManagedProgressItem,
    ManagedProgressResponse,
    MarketplaceImageInstallResponse,
    ManagedProcessInfo,
    ManagedUpdateEnvRequest,
    MarketplaceCatalogInfo,
    MarketplaceDockerInfo,
    MarketplaceEnvVarInfo,
    MarketplaceListResponse,
)
from src.audit import (
    ActorType,
    AuditAction,
    AuditService,
    AuditStatus,
    ResourceType,
)
from src.identity import get_current_user
from src.logging import get_logger
from src.marketplace.loader import get_catalog_loader
from src.marketplace.schema import CatalogEntry
from src.orchestrator.launch_spec import MCP_RUNTIME_IMAGE, user_source_id
from src.orchestrator.manager import OrchestratorError, get_orchestrator
from src.orchestrator.progress import catalog_key, get_progress_registry

logger = get_logger("api.managed")

router = APIRouter()


# ---------- Helpers ----------

def _catalog_to_info(
    db: Session, entry: CatalogEntry
) -> MarketplaceCatalogInfo:
    """把 CatalogEntry 轉成 API response 物件,並標註 installed / image 狀態"""
    installed_processes = ManagedMcpProcessAdapter.list_all(db, catalog_id=entry.id)
    installed = bool(installed_processes)
    installed_id = str(installed_processes[0].id) if installed_processes else None

    # 離線安裝三態:image 是否已 load(docker SDK)、tar 是否就位
    image_ref = f"{entry.docker.image}:{entry.docker.tag}"
    try:
        image_installed = get_orchestrator().image_exists(image_ref)
    except Exception:
        # docker daemon 不可達時不擋列表,狀態顯示未安裝
        image_installed = False
    tar_path = get_catalog_loader().image_tar_path(entry)

    return MarketplaceCatalogInfo(
        image_installed=image_installed,
        image_tar_present=tar_path.is_file(),
        image_tar_name=entry.image_tar_name(),
        id=entry.id,
        name=entry.name,
        description=entry.description,
        category=entry.category,
        icon=entry.icon,
        docker=MarketplaceDockerInfo(
            image=entry.docker.image,
            tag=entry.docker.tag,
            args=entry.docker.args,
        ),
        env_vars=[
            MarketplaceEnvVarInfo(
                name=ev.name, label=ev.label, help=ev.help,
                required=ev.required, secret=ev.secret, default=ev.default,
                pattern=ev.pattern, error_message=ev.error_message,
            )
            for ev in entry.env_vars
        ],
        docs_url=entry.docs_url,
        installed=installed,
        installed_process_id=installed_id,
    )


def _process_to_info(db: Session, p) -> ManagedProcessInfo:
    """把 ORM ManagedMcpProcess 轉成 API response,順便算 connection_url"""
    catalog = get_catalog_loader().get(p.catalog_id)
    catalog_name = catalog.name if catalog else None

    # 給廠商 agent 用的連線 URL(MCP Center 跑在 host network,127.0.0.1 = host)
    connection_url = (
        f"http://127.0.0.1:{p.port}/mcp" if p.port and p.actual_state == "running"
        else None
    )

    raw = p.to_dict()
    return ManagedProcessInfo(
        id=raw["id"],
        name=raw["name"],
        catalog_id=raw["catalog_id"],
        catalog_name=catalog_name,
        service_id=raw["service_id"],
        docker_image=raw["docker_image"],
        image_args=raw["image_args"],
        env_var_names=raw["env_var_names"],
        bridge_type=raw["bridge_type"],
        port=raw["port"],
        auto_port=raw["auto_port"],
        desired_state=raw["desired_state"],
        actual_state=raw["actual_state"],
        container_id=raw["container_id"],
        last_error=raw["last_error"],
        created_at=raw["created_at"],
        updated_at=raw["updated_at"],
        connection_url=connection_url,
    )


def _validate_env_vars(catalog: CatalogEntry, env_vars: dict) -> None:
    """根據 catalog schema 驗 env vars。失敗就 raise HTTPException(400)。"""
    provided_keys = set(env_vars.keys())
    expected = {ev.name: ev for ev in catalog.env_vars}

    # 1. 不認得的 key
    extra = provided_keys - set(expected.keys())
    if extra:
        extras_list = sorted(extra)
        raise HTTPException(
            status_code=400,
            detail={
                "error": "managed.env_vars_unknown",
                "params": {"catalog_id": catalog.id, "extras": extras_list},
                "fallback": f"Unknown env vars for {catalog.id}: {extras_list}",
            },
        )

    # 2. required 缺失
    for name, ev in expected.items():
        if ev.required and (name not in env_vars or env_vars[name] in (None, "")):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "managed.env_var_required_missing",
                    "params": {"name": name},
                    "fallback": f"Required env var '{name}' is missing or empty",
                },
            )

    # 3. pattern 驗證
    for name, value in env_vars.items():
        if value in (None, ""):
            continue
        ev = expected[name]
        if ev.pattern and not re.match(ev.pattern, str(value)):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "managed.env_var_pattern_failed",
                    "params": {"name": name, "error_message": ev.error_message or ""},
                    "fallback": ev.error_message or f"Env var '{name}' failed pattern validation",
                },
            )


# ---------- Marketplace endpoints ----------

@router.get(
    "/api/managed/progress",
    response_model=ManagedProgressResponse,
    tags=["Managed MCP"],
)
async def list_managed_progress(
    _: AdminUser = Depends(get_current_user),
):
    """列出進行中的長操作與其目前階段(供前端輪詢顯示「正在做什麼」)。

    部署 / 啟停 / 載入 image 的 HTTP 回應要等整件事做完;這個端點讓前端在等待
    期間能把「等 port 開」「暖機下載套件中」等階段呈現給使用者,而不是一顆轉圈。
    純記憶體、無 DB 存取,輪詢成本極低。
    註:必須宣告在 /api/managed/{process_id} 之前,否則 "progress" 會被當成 id。
    """
    import time as _time
    now = _time.time()
    items = [
        ManagedProgressItem(**item, elapsed_seconds=round(now - item["started_at"], 1))
        for item in get_progress_registry().snapshot()
    ]
    return ManagedProgressResponse(items=items)


@router.get(
    "/api/marketplace",
    response_model=MarketplaceListResponse,
    tags=["Managed MCP"],
)
async def list_marketplace(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    """列出所有 marketplace catalog 項目,標註已安裝狀態"""
    loader = get_catalog_loader()
    entries = loader.load_all()
    # docker 查詢為同步 I/O:整批丟到 worker thread(共用 db Session,故單一 thread 依序跑),
    # 避免卡住 event loop。
    items = await asyncio.to_thread(lambda: [_catalog_to_info(db, e) for e in entries.values()])
    return MarketplaceListResponse(catalog=items, total_count=len(items))


@router.get(
    "/api/marketplace/{catalog_id}",
    response_model=MarketplaceCatalogInfo,
    tags=["Managed MCP"],
)
async def get_catalog_entry(
    catalog_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    entry = get_catalog_loader().get(catalog_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "managed.catalog_not_found",
                "params": {"catalog_id": catalog_id},
                "fallback": f"Catalog '{catalog_id}' not found",
            },
        )
    return await asyncio.to_thread(_catalog_to_info, db, entry)


@router.post(
    "/api/marketplace/{catalog_id}/install",
    response_model=MarketplaceImageInstallResponse,
    tags=["Managed MCP"],
)
async def install_marketplace_image(
    catalog_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """「安裝」:從 catalog/images/<tar> 載入 docker image(離線,docker SDK)。

    三態流程的第一步:安裝(docker load)→ 部署(POST /api/managed)。
    tar 不存在時回 404,錯誤訊息附手動 `docker load -i` 指令供備援。
    """
    entry = get_catalog_loader().get(catalog_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "managed.catalog_not_found",
                "params": {"catalog_id": catalog_id},
                "fallback": f"Catalog '{catalog_id}' not found",
            },
        )

    image_ref = f"{entry.docker.image}:{entry.docker.tag}"
    orchestrator = get_orchestrator()

    # 已安裝 → 冪等回應
    if await asyncio.to_thread(orchestrator.image_exists, image_ref):
        return MarketplaceImageInstallResponse(
            success=True,
            message=f"Image '{image_ref}' already installed",
            image_installed=True,
        )

    tar_path = get_catalog_loader().image_tar_path(entry)
    if not tar_path.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "managed.image_tar_not_found",
                "params": {"path": str(tar_path)},
                "fallback": (
                    f"Image tar not found: {tar_path}。請將 image tar 放至該路徑後重試,"
                    f"或於主機手動執行:docker load -i {tar_path}"
                ),
            },
        )

    logger.info(f"Installing image for catalog={catalog_id}: tar={tar_path}, user={current_user.username}")
    progress = get_progress_registry()
    pkey = catalog_key(catalog_id)
    progress.begin(pkey, "install_image", "loading_image")
    try:
        # docker load 讀整個 tar(可達數 GB、數分鐘):必須離開 event loop
        loaded_tags = await asyncio.to_thread(orchestrator.load_image, str(tar_path))
        progress.stage(pkey, "verifying_image", image_ref)
        # 驗證 load 出來的確實含預期 image(tar 放錯內容時明確報錯)
        image_installed = await asyncio.to_thread(orchestrator.image_exists, image_ref)
    except OrchestratorError as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "managed.image_load_failed",
                "params": {"reason": str(e)},
                "fallback": f"Image load failed: {e}",
            },
        )
    finally:
        progress.end(pkey)
    if not image_installed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "managed.image_tar_mismatch",
                "params": {"expected": image_ref, "loaded": loaded_tags},
                "fallback": (
                    f"Tar loaded (tags={loaded_tags}) 但不含 catalog 期望的 image "
                    f"'{image_ref}',請確認 tar 內容或 catalog 的 image/tag 設定"
                ),
            },
        )

    AuditService.log_from_request(
        db=db, request=http_request,
        action=AuditAction.CREATE_SERVICE,
        resource_type=ResourceType.SERVICE,
        status=AuditStatus.SUCCESS,
        resource_id=catalog_id,
        actor_type=ActorType.ADMIN,
        actor_id=str(current_user.id),
        actor_name=current_user.audit_name,
        details={"action": "install_image", "image": image_ref, "tags": loaded_tags},
    )
    return MarketplaceImageInstallResponse(
        success=True,
        message=f"Image '{image_ref}' installed",
        image_installed=True,
        loaded_tags=loaded_tags,
    )


@router.get("/api/managed/{process_id}/logs", tags=["Managed MCP"])
async def get_managed_logs(
    process_id: str,
    tail: int = 200,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    """取得該 managed process 容器的輸出(含已退出的容器)。

    容器崩潰時,死因只在它自己的 log 裡;沒有這支端點就得手動下 docker 指令。
    """
    try:
        ManagedMcpProcessAdapter.get_existing(db, process_id)
    except AdapterError as e:
        raise _adapter_http_exc(e)
    logs = await asyncio.to_thread(get_orchestrator().container_logs, process_id, tail)
    return {"process_id": process_id, "logs": logs}


# ---------- BYO(自帶啟動指令)MCP 定義 ----------
# 等同授權任意 container 執行 —— 只有登入的擁有者能用(見 docs/design/byo-mcp-launch.md)。

@router.post("/api/byo-mcp", response_model=ByoDefinitionInfo, tags=["Managed MCP"])
async def create_byo_definition(
    request: ByoCreateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """建立 BYO MCP 定義(貼標準 {command, args, env})。

    command/args 經 argv 政策驗證(command 白名單 + args 字元白名單)。
    """
    try:
        d = BYODefinitionAdapter.create_definition(
            db,
            name=request.name,
            command=request.command,
            args=request.args,
            container_port=request.container_port,
            env_schema=[e.model_dump() for e in request.env_schema],
            description=request.description,
            created_by_id=str(current_user.id),
        )
    except AdapterError as e:
        raise _adapter_http_exc(e)

    AuditService.log_from_request(
        db=db, request=http_request,
        action=AuditAction.CREATE_SERVICE,
        resource_type=ResourceType.SERVICE,
        status=AuditStatus.SUCCESS,
        resource_id=str(d.id),
        actor_type=ActorType.ADMIN,
        actor_id=str(current_user.id),
        actor_name=current_user.audit_name,
        details={"action": "create_byo_definition", "name": d.name,
                 "command": d.command, "args": d.get_args()},
    )
    return ByoDefinitionInfo(**d.to_dict())


@router.get("/api/byo-mcp", response_model=ByoListResponse, tags=["Managed MCP"])
async def list_byo_definitions(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    """列出所有 BYO 定義。"""
    defs = BYODefinitionAdapter.list_all(db)
    return ByoListResponse(
        definitions=[ByoDefinitionInfo(**d.to_dict()) for d in defs],
        total_count=len(defs),
    )


@router.delete("/api/byo-mcp/{definition_id}", tags=["Managed MCP"])
async def delete_byo_definition(
    definition_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """刪除 BYO 定義(已部署則擋,需先 uninstall)。"""
    try:
        BYODefinitionAdapter.delete_guarded(db, definition_id)
    except AdapterError as e:
        raise _adapter_http_exc(e)

    AuditService.log_from_request(
        db=db, request=http_request,
        action=AuditAction.DELETE_SERVICE,
        resource_type=ResourceType.SERVICE,
        status=AuditStatus.SUCCESS,
        resource_id=definition_id,
        actor_type=ActorType.ADMIN,
        actor_id=str(current_user.id),
        actor_name=current_user.audit_name,
        details={"action": "delete_byo_definition"},
    )
    return {"message": "BYO definition deleted"}


@router.post(
    "/api/byo-mcp/{definition_id}/deploy",
    response_model=ManagedActionResponse,
    tags=["Managed MCP"],
)
async def deploy_byo_definition(
    definition_id: str,
    request: ByoDeployRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """部署 BYO 定義:在受控 container 內以 supergateway 橋接,導出 127.0.0.1:port。"""
    try:
        definition = BYODefinitionAdapter.get_existing(db, definition_id)
        # single-instance:同定義已部署 → 409
        ManagedMcpProcessAdapter.assert_not_installed(db, user_source_id(str(definition.id)))
    except AdapterError as e:
        raise _adapter_http_exc(e)

    # env vars 驗證:只允許定義 schema 內宣告的 key(擋未知 key)
    declared = {e["name"] for e in definition.get_env_schema()}
    extras = set(request.env_vars) - declared
    if extras:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "byo.unknown_env_vars",
                "params": {"extras": sorted(extras)},
                "fallback": f"Unknown env vars: {sorted(extras)}",
            },
        )

    name = request.name or definition.name
    # 建立 managed process:image=受控基底,catalog_id=user:<id>(orchestrator 由此解析內層指令)
    process = ManagedMcpProcessAdapter.create(
        db=db,
        name=name,
        catalog_id=user_source_id(str(definition.id)),
        docker_image=MCP_RUNTIME_IMAGE,
        # 刻意不用 --rm:auto_remove 會在容器退出時連同 log 一併刪除,導致
        # 崩潰後完全查不出死因(stop/uninstall 本來就會明確 force remove)。
        # --init 提供 PID 1 收屍,避免 supergateway spawn 的子行程變殭屍。
        image_args="--init",
        image_command=None,
        env_vars=request.env_vars,
        port=request.port,
        created_by=str(current_user.id),
    )

    started_ok = True
    err_msg = None
    if request.auto_start:
        try:
            ManagedMcpProcessAdapter.set_desired_state(db, str(process.id), "running")
            process = await asyncio.to_thread(get_orchestrator().start, db, str(process.id))
        except Exception as e:
            started_ok = False
            err_msg = str(e)
            logger.error(f"BYO deploy: process created but start failed: {e}")
            ManagedMcpProcessAdapter.update_state(
                db, str(process.id), actual_state="failed", last_error=err_msg,
            )
            process = ManagedMcpProcessAdapter.get_by_id(db, str(process.id))

    AuditService.log_from_request(
        db=db, request=http_request,
        action=AuditAction.CREATE_SERVICE,
        resource_type=ResourceType.SERVICE,
        status=AuditStatus.SUCCESS if started_ok else AuditStatus.FAILURE,
        resource_id=str(process.id),
        actor_type=ActorType.ADMIN,
        actor_id=str(current_user.id),
        actor_name=current_user.audit_name,
        details={"action": "deploy_byo", "definition_id": str(definition.id),
                 "auto_start": request.auto_start, "error": err_msg},
    )
    msg = (
        f"Deployed and started {name}" if started_ok and request.auto_start
        else f"Deployed {name} (start failed: {err_msg})" if not started_ok
        else f"Deployed {name} (not started)"
    )
    return ManagedActionResponse(
        success=started_ok, message=msg, process=_process_to_info(db, process),
    )


# ---------- Managed MCP endpoints ----------

@router.get(
    "/api/managed",
    response_model=ManagedListResponse,
    tags=["Managed MCP"],
)
async def list_managed(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    procs = ManagedMcpProcessAdapter.list_all(db)
    return ManagedListResponse(
        processes=[_process_to_info(db, p) for p in procs],
        total_count=len(procs),
    )


@router.get(
    "/api/managed/{process_id}",
    response_model=ManagedProcessInfo,
    tags=["Managed MCP"],
)
async def get_managed(
    process_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_user),
):
    try:
        p = ManagedMcpProcessAdapter.get_existing(db, process_id)
    except AdapterError as e:
        raise _adapter_http_exc(e)
    return _process_to_info(db, p)


@router.post(
    "/api/managed",
    response_model=ManagedActionResponse,
    tags=["Managed MCP"],
)
async def install_managed(
    request: ManagedInstallRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """從 catalog 安裝 + (預設)立即啟動"""
    logger.info(f"Install request: catalog={request.catalog_id}, name={request.name}, port={request.port}, user={current_user.username}")
    catalog = get_catalog_loader().get(request.catalog_id)
    if not catalog:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "managed.catalog_not_found",
                "params": {"catalog_id": request.catalog_id},
                "fallback": f"Catalog '{request.catalog_id}' not found",
            },
        )

    # Single instance check(邏輯在 adapter)
    try:
        ManagedMcpProcessAdapter.assert_not_installed(db, request.catalog_id)
    except AdapterError as e:
        raise _adapter_http_exc(e)

    # 部署前置:image 必須已「安裝」(離線兩階段流程;不自動 load,明確引導)
    image_ref = f"{catalog.docker.image}:{catalog.docker.tag}"
    if not await asyncio.to_thread(get_orchestrator().image_exists, image_ref):
        tar_path = get_catalog_loader().image_tar_path(catalog)
        raise HTTPException(
            status_code=400,
            detail={
                "error": "managed.image_not_installed",
                "params": {"image": image_ref, "catalog_id": catalog.id},
                "fallback": (
                    f"Image '{image_ref}' 尚未安裝。請先執行「安裝」"
                    f"(POST /api/marketplace/{catalog.id}/install),"
                    f"或於主機手動執行:docker load -i {tar_path}"
                ),
            },
        )

    # Env vars 驗證(會 raise 400)
    _validate_env_vars(catalog, request.env_vars)

    # 建立 DB row (port=None → auto_port=True, port=int → auto_port=False)
    name = request.name or catalog.id
    process = ManagedMcpProcessAdapter.create(
        db=db,
        name=name,
        catalog_id=catalog.id,
        docker_image=f"{catalog.docker.image}:{catalog.docker.tag}",
        image_args=" ".join(catalog.docker.args),
        image_command=list(catalog.docker.command) if catalog.docker.command else None,
        env_vars=request.env_vars,
        port=request.port,
        created_by=str(current_user.id),
    )

    # 預設 auto_start
    started_ok = True
    err_msg = None
    if request.auto_start:
        try:
            ManagedMcpProcessAdapter.set_desired_state(db, str(process.id), "running")
            process = await asyncio.to_thread(get_orchestrator().start, db, str(process.id))
        except (OrchestratorError, Exception) as e:
            started_ok = False
            err_msg = str(e)
            logger.error(f"Install: process created but start failed: {e}")
            ManagedMcpProcessAdapter.update_state(
                db, str(process.id),
                actual_state="failed",
                last_error=err_msg,
            )
            process = ManagedMcpProcessAdapter.get_by_id(db, str(process.id))

    # Audit
    AuditService.log_from_request(
        db=db, request=http_request,
        action=AuditAction.CREATE_SERVICE,  # 沿用既有 enum,日後可加 INSTALL_MANAGED
        resource_type=ResourceType.SERVICE,
        status=AuditStatus.SUCCESS if started_ok else AuditStatus.FAILURE,
        resource_id=str(process.id),
        actor_type=ActorType.ADMIN,
        actor_id=str(current_user.id),
        actor_name=current_user.audit_name,
        details={"catalog_id": catalog.id, "auto_start": request.auto_start, "error": err_msg},
    )

    msg = (
        f"Installed and started {catalog.name}" if started_ok and request.auto_start
        else f"Installed {catalog.name} (start failed: {err_msg})" if not started_ok
        else f"Installed {catalog.name} (not started)"
    )
    return ManagedActionResponse(
        success=started_ok,
        message=msg,
        process=_process_to_info(db, process),
    )


@router.post(
    "/api/managed/{process_id}/start",
    response_model=ManagedActionResponse,
    tags=["Managed MCP"],
)
async def start_managed(
    process_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    logger.info(f"Start request: process_id={process_id}, user={current_user.username}")
    try:
        p = ManagedMcpProcessAdapter.get_existing(db, process_id)
    except AdapterError as e:
        raise _adapter_http_exc(e)

    try:
        ManagedMcpProcessAdapter.set_desired_state(db, process_id, "running")
        p = await asyncio.to_thread(get_orchestrator().start, db, process_id)
    except OrchestratorError as e:
        ManagedMcpProcessAdapter.update_state(
            db, process_id, actual_state="failed", last_error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "managed.start_failed",
                "params": {"reason": str(e)},
                "fallback": f"Start failed: {e}",
            },
        )

    AuditService.log_from_request(
        db=db, request=http_request,
        action=AuditAction.UPDATE_SERVICE,
        resource_type=ResourceType.SERVICE,
        status=AuditStatus.SUCCESS,
        resource_id=process_id,
        actor_type=ActorType.ADMIN,
        actor_id=str(current_user.id),
        actor_name=current_user.audit_name,
        details={"action": "start_managed"},
    )
    return ManagedActionResponse(
        success=True, message=f"Started {p.name}",
        process=_process_to_info(db, p),
    )


@router.post(
    "/api/managed/{process_id}/stop",
    response_model=ManagedActionResponse,
    tags=["Managed MCP"],
)
async def stop_managed(
    process_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    logger.info(f"Stop request: process_id={process_id}, user={current_user.username}")
    try:
        p = ManagedMcpProcessAdapter.get_existing(db, process_id)
    except AdapterError as e:
        raise _adapter_http_exc(e)

    try:
        ManagedMcpProcessAdapter.set_desired_state(db, process_id, "stopped")
        p = await asyncio.to_thread(get_orchestrator().stop, db, process_id)
    except OrchestratorError as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "managed.stop_failed",
                "params": {"reason": str(e)},
                "fallback": f"Stop failed: {e}",
            },
        )

    AuditService.log_from_request(
        db=db, request=http_request,
        action=AuditAction.UPDATE_SERVICE,
        resource_type=ResourceType.SERVICE,
        status=AuditStatus.SUCCESS,
        resource_id=process_id,
        actor_type=ActorType.ADMIN,
        actor_id=str(current_user.id),
        actor_name=current_user.audit_name,
        details={"action": "stop_managed"},
    )
    return ManagedActionResponse(
        success=True, message=f"Stopped {p.name}",
        process=_process_to_info(db, p),
    )


@router.put(
    "/api/managed/{process_id}/env-vars",
    response_model=ManagedActionResponse,
    tags=["Managed MCP"],
)
async def update_env_vars(
    process_id: str,
    request: ManagedUpdateEnvRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """覆寫 env vars(明文進、加密存)。若正在 running 會自動重啟以套用。"""
    logger.info(f"Update env vars: process_id={process_id}, keys={list(request.env_vars.keys())}, user={current_user.username}")
    try:
        p = ManagedMcpProcessAdapter.get_existing(db, process_id)
    except AdapterError as e:
        raise _adapter_http_exc(e)

    catalog = get_catalog_loader().get(p.catalog_id)
    if not catalog:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "managed.catalog_removed_from_image",
                "params": {"catalog_id": p.catalog_id},
                "fallback": f"Catalog '{p.catalog_id}' not found(已從 image 中移除?)",
            },
        )
    _validate_env_vars(catalog, request.env_vars)

    was_running = (p.actual_state == "running")
    if was_running:
        await asyncio.to_thread(get_orchestrator().stop, db, process_id)

    ManagedMcpProcessAdapter.update_env_vars(db, process_id, request.env_vars)

    if was_running:
        try:
            p = await asyncio.to_thread(get_orchestrator().start, db, process_id)
        except OrchestratorError as e:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "managed.env_updated_restart_failed",
                    "params": {"reason": str(e)},
                    "fallback": f"Env updated but restart failed: {e}",
                },
            )
    else:
        p = ManagedMcpProcessAdapter.get_by_id(db, process_id)

    AuditService.log_from_request(
        db=db, request=http_request,
        action=AuditAction.UPDATE_SERVICE,
        resource_type=ResourceType.SERVICE,
        status=AuditStatus.SUCCESS,
        resource_id=process_id,
        actor_type=ActorType.ADMIN,
        actor_id=str(current_user.id),
        actor_name=current_user.audit_name,
        details={"action": "update_env_vars", "keys": list(request.env_vars.keys())},
    )
    return ManagedActionResponse(
        success=True,
        message=("Env vars updated and restarted" if was_running
                 else "Env vars updated (process not running)"),
        process=_process_to_info(db, p),
    )


@router.delete(
    "/api/managed/{process_id}",
    response_model=ManagedActionResponse,
    tags=["Managed MCP"],
)
async def uninstall_managed(
    process_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_user),
):
    """uninstall:停止 → 刪 Service row → 刪 token + usage → 刪 process row"""
    logger.info(f"Uninstall request: process_id={process_id}, user={current_user.username}")
    try:
        p = ManagedMcpProcessAdapter.get_existing(db, process_id)
    except AdapterError as e:
        raise _adapter_http_exc(e)

    name = p.name
    catalog_id = p.catalog_id

    # 1. Stop(忽略已停的錯;orchestrator 為外部程序,由 route 協調)
    try:
        await asyncio.to_thread(get_orchestrator().stop, db, process_id)
    except Exception as e:
        logger.warning(f"Stop during uninstall failed (continuing): {e}")

    # 2+3. 清 Service 相關資料 + 刪 process row(邏輯在 adapter)
    ManagedMcpProcessAdapter.purge_with_service(db, p, logger)

    AuditService.log_from_request(
        db=db, request=http_request,
        action=AuditAction.DELETE_SERVICE,
        resource_type=ResourceType.SERVICE,
        status=AuditStatus.SUCCESS,
        resource_id=process_id,
        actor_type=ActorType.ADMIN,
        actor_id=str(current_user.id),
        actor_name=current_user.audit_name,
        details={"catalog_id": catalog_id, "name": name},
    )
    return ManagedActionResponse(
        success=True,
        message=f"Uninstalled {name}",
        process=None,
    )
