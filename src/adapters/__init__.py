"""資料存取 Adapter 層(三層架構的中間層)

    API routes / 服務層  ─▶  Adapter(本層)  ─▶  db.crud(資料層)

上層一律 `from src.adapters import XAdapter`,不直接 import db.crud。
不變量(由 tests/test_architecture_layering.py 守住):只有 src/adapters/* 會 import db.crud。
"""

from db.crud import normalize_audience, normalize_service_host  # 純工具函式,經本層 re-export

from src.adapters.admin_adapter import AdminUserAdapter
from src.adapters.managed_adapter import (
    BYODefinitionAdapter,
    ManagedMcpProcessAdapter,
    MCPToolAdapter,
)
from src.adapters.oauth_adapter import (
    AuditLogAdapter,
    OAuthAuthRequestAdapter,
    OAuthClientAdapter,
    OAuthCodeAdapter,
    OAuthConsentAdapter,
    OAuthKeyAdapter,
    OAuthScopeAdapter,
    OAuthTokenAdapter,
    TokenUsageAdapter,
)
from src.adapters.service_adapter import ServiceAdapter

__all__ = [
    "ServiceAdapter",
    "MCPToolAdapter",
    "AdminUserAdapter",
    "BYODefinitionAdapter",
    "ManagedMcpProcessAdapter",
    "TokenUsageAdapter",
    "AuditLogAdapter",
    "OAuthKeyAdapter",
    "OAuthClientAdapter",
    "OAuthAuthRequestAdapter",
    "OAuthCodeAdapter",
    "OAuthScopeAdapter",
    "OAuthTokenAdapter",
    "OAuthConsentAdapter",
    "normalize_service_host",
    "normalize_audience",
]
