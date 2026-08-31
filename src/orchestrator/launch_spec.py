"""LaunchSpec:orchestrator 的統一啟動描述

把兩種來源正規化成同一份描述,讓 orchestrator 不必在乎來源是「檔案 catalog」
還是「使用者 BYO 定義」:

  - catalog(repo YAML) → 既有 http / stdio image。
  - user definition(BYO) → 受控基底 image + supergateway 橋接內層 stdio 指令。

BYO 的執行模型(設計文件 §3-4):一切都在 container 內。內層 MCP 指令
(npx/uvx/node/python + args)由基底 image 內的 supergateway spawn,並橋接
stdio↔HTTP;我方只把「supergateway + 內層指令」以 **list** 傳給 docker SDK
(無 shell、無 subprocess sink)。
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional

from db.models import ManagedMcpProcess

# 受控基底 image:內含 node(supergateway)+ python + uv,平台維護、pin 版本。
# 離線環境需先 docker load 進來(一次性平台設定)。可用環境變數覆寫。
MCP_RUNTIME_IMAGE = os.environ.get("MCP_RUNTIME_IMAGE", "mcp-runtime:1")

# BYO 來源前綴:ManagedMcpProcess.catalog_id = "user:<definition_uuid>"
USER_SOURCE_PREFIX = "user:"


@dataclass
class LaunchSpec:
    """orchestrator 啟動一個 managed process 所需的全部資訊(來源無關)。"""
    source_kind: str            # "catalog" | "user"
    source_id: str              # catalog id 或 definition uuid
    name: str
    transport: str              # "http" | "stdio"
    image_ref: str              # http: 使用者 image:tag;stdio-BYO: 受控基底 image
    container_port: int
    run_flags: List[str] = field(default_factory=list)     # docker run flag tokens
    entrypoint_args: List[str] = field(default_factory=list)  # http: image entrypoint args
    stdio_command: List[str] = field(default_factory=list)    # stdio-BYO: 內層 MCP 指令 tokens


def is_user_source(catalog_id: Optional[str]) -> bool:
    return bool(catalog_id) and catalog_id.startswith(USER_SOURCE_PREFIX)


def user_source_id(definition_id: str) -> str:
    """把 definition uuid 包成 ManagedMcpProcess.catalog_id 用的來源字串。"""
    return f"{USER_SOURCE_PREFIX}{definition_id}"


def _definition_uuid(catalog_id: str) -> str:
    return catalog_id[len(USER_SOURCE_PREFIX):]


def resolve_launch_spec(db, process: ManagedMcpProcess) -> LaunchSpec:
    """把一個 ManagedMcpProcess 解析成 LaunchSpec(catalog 或 user 皆可)。

    Raises:
        LookupError: 來源(catalog 檔或 user 定義)已不存在。
    """
    import json

    catalog_id = process.catalog_id

    # ---- BYO 使用者定義:受控基底 image + supergateway 橋接內層 stdio 指令 ----
    if is_user_source(catalog_id):
        # 經 adapter 存取(維持「只有 src/adapters 碰 db.crud」不變量)
        from src.adapters.managed_adapter import BYODefinitionAdapter

        definition = BYODefinitionAdapter.get_by_id(db, _definition_uuid(catalog_id))
        if not definition:
            raise LookupError(f"BYO definition '{catalog_id}' not found")
        inner = [definition.command] + definition.get_args()
        return LaunchSpec(
            source_kind="user",
            source_id=str(definition.id),
            name=process.name,
            transport="stdio",
            image_ref=MCP_RUNTIME_IMAGE,
            container_port=definition.container_port or 8000,
            run_flags=(process.image_args or "--rm").split(),
            stdio_command=inner,
        )

    # ---- 檔案 catalog:沿用既有 http / stdio image ----
    from src.marketplace.loader import get_catalog_loader

    catalog = get_catalog_loader().get(catalog_id)
    if not catalog:
        raise LookupError(f"Catalog entry '{catalog_id}' not found")

    entrypoint_args = []
    if process.image_command:
        try:
            v = json.loads(process.image_command)
            if isinstance(v, list):
                entrypoint_args = v
        except Exception:
            entrypoint_args = []

    return LaunchSpec(
        source_kind="catalog",
        source_id=catalog_id,
        name=process.name,
        transport=getattr(catalog.docker, "transport", "http"),
        image_ref=process.docker_image,
        container_port=getattr(catalog.docker, "container_port", 8080),
        run_flags=(process.image_args or "--rm").split(),
        entrypoint_args=entrypoint_args,
    )
