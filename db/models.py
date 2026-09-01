"""資料庫模型定義

主鍵一律用 SQLAlchemy 2.0 通用 `Uuid` 型別:PostgreSQL 存原生 uuid,SQLite 存 CHAR(32),
兩邊程式碼零差異。
"""

import json
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid,
)
from sqlalchemy.orm import relationship

from db.database import Base


def local_now() -> datetime:
    """當前本地時間(naive)。"""
    return datetime.now()


def format_datetime(dt: datetime) -> str | None:
    """datetime → ISO 8601(含時區)。"""
    if dt is None:
        return None
    return dt.astimezone().isoformat()


# 舊名稱相容
format_utc_datetime = format_datetime


def _json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except Exception:
        return []


# ==================== 管理台使用者 ====================

class AdminUser(Base):
    """管理台使用者(單一租戶:所有登入者皆為管理員,沒有 RBAC)。

    auth_provider = local(帳密)/ github / google;第三方登入的帳號 password_hash 可為空。
    """
    __tablename__ = "admin_users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    email = Column(String(128), unique=True, nullable=False, index=True)
    username = Column(String(64), nullable=False)
    password_hash = Column(String(256), nullable=True)
    auth_provider = Column(String(16), default="local", nullable=False)
    provider_sub = Column(String(128), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=local_now, nullable=False)
    last_login = Column(DateTime, nullable=True)
    # 改密後 iat 早於此時間的 session 視同撤銷
    password_changed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<AdminUser(email={self.email}, provider={self.auth_provider})>"

    @property
    def audit_name(self) -> str:
        return f"{self.username} <{self.email}>"

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "email": self.email,
            "username": self.username,
            "auth_provider": self.auth_provider,
            "has_password": bool(self.password_hash),
            "is_active": self.is_active,
            "created_at": format_datetime(self.created_at),
            "last_login": format_datetime(self.last_login),
        }


# ==================== MCP 服務 ====================

class Service(Base):
    """已註冊的 MCP server(Resource Server)。

    oauth_audience = 這台 server 的 canonical resource URI(RFC 8707),也是簽給它的
    token 的 aud。FastMCP 端 JWTVerifier(audience=...) 要填同一個值。
    oauth_scopes = 允許簽發給此服務的 scope(空白分隔;空 = 註冊表內全部)。
    auth_token_encrypted = 外部服務若用自己的靜態 Bearer,存這裡供健康檢查 / 抓 tools 用。
    """
    __tablename__ = "services"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(64), nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=local_now, nullable=False)
    updated_at = Column(DateTime, default=local_now, onupdate=local_now)

    host = Column(String(128), nullable=True)
    port = Column(Integer, nullable=True)
    protocol = Column(String(16), default="http")
    mcp_path = Column(String(128), default="/mcp")
    auth_token_encrypted = Column(String(1024), nullable=True)
    requires_auth = Column(Boolean, default=True, nullable=False)
    tags = Column(String(512), nullable=True)
    source = Column(String(32), default="manual")  # manual / auto_discovered / managed

    oauth_audience = Column(String(256), nullable=True, index=True)
    oauth_scopes = Column(String(512), nullable=True)

    health_status = Column(String(32), default="unknown")
    health_last_checked = Column(DateTime, nullable=True)
    health_response_time_ms = Column(Float, nullable=True)
    health_error_message = Column(String(512), nullable=True)
    health_fail_count = Column(Integer, default=0)

    tools = relationship("MCPTool", back_populates="service", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Service(name={self.name}, host={self.host}:{self.port})>"

    def get_mcp_url(self) -> str | None:
        if not self.host or not self.port:
            return None
        return f"{self.protocol}://{self.host}:{self.port}{self.mcp_path or ''}"

    @property
    def effective_audience(self) -> str | None:
        """aud:優先用明確設定的 oauth_audience,否則用 MCP URL。"""
        return self.oauth_audience or self.get_mcp_url()

    def to_dict(self, include_tools: bool = False, include_health: bool = True) -> dict:
        data = {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": format_datetime(self.created_at),
            "updated_at": format_datetime(self.updated_at),
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "mcp_path": self.mcp_path,
            "mcp_url": self.get_mcp_url(),
            "tags": self.tags.split(",") if self.tags else [],
            "source": self.source,
            "requires_auth": self.requires_auth,
            "has_static_token": bool(self.auth_token_encrypted),
            "oauth_audience": self.oauth_audience,
            "effective_audience": self.effective_audience,
            "oauth_scopes": self.oauth_scopes.split() if self.oauth_scopes else [],
        }
        if include_health:
            data["health"] = {
                "status": self.health_status,
                "last_checked": format_datetime(self.health_last_checked),
                "response_time_ms": self.health_response_time_ms,
                "error_message": self.health_error_message,
                "fail_count": self.health_fail_count,
            }
        if include_tools:
            data["tools"] = [t.to_dict() for t in self.tools]
        return data


class MCPTool(Base):
    __tablename__ = "mcp_tools"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    service_id = Column(Uuid, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    input_schema = Column(Text, nullable=True)
    created_at = Column(DateTime, default=local_now, nullable=False)

    service = relationship("Service", back_populates="tools")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "service_id": str(self.service_id),
            "name": self.name,
            "description": self.description,
            "input_schema": json.loads(self.input_schema) if self.input_schema else None,
            "created_at": format_datetime(self.created_at),
        }


# ==================== OAuth 2.1 Authorization Server ====================

class OAuthSigningKey(Base):
    """JWT 簽章金鑰(RS256)。私鑰 AES 加密入庫;kid 讓多把金鑰並存以支援輪替。"""
    __tablename__ = "oauth_signing_keys"

    kid = Column(String(64), primary_key=True)
    alg = Column(String(16), default="RS256", nullable=False)
    public_jwk = Column(Text, nullable=False)
    private_pem_enc = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=local_now, nullable=False)
    rotated_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "kid": self.kid,
            "alg": self.alg,
            "public_jwk": json.loads(self.public_jwk) if self.public_jwk else None,
            "is_active": self.is_active,
            "created_at": format_datetime(self.created_at),
            "rotated_at": format_datetime(self.rotated_at),
        }


class OAuthClient(Base):
    """OAuth client(Claude / Cursor / 自寫 agent …)。

    public client(token_endpoint_auth_method=none)靠 PKCE;confidential client 有 secret
    (只存 hash)。created_via = dcr(動態註冊)/ manual(管理台建立)/ system(內建)。
    """
    __tablename__ = "oauth_clients"

    client_id = Column(String(64), primary_key=True)
    client_secret_hash = Column(String(128), nullable=True)
    client_name = Column(String(128), nullable=False)
    client_uri = Column(String(512), nullable=True)
    logo_uri = Column(String(512), nullable=True)
    software_id = Column(String(128), nullable=True)
    redirect_uris = Column(Text, nullable=False, default="[]")
    grant_types = Column(Text, nullable=False, default="[]")
    response_types = Column(Text, nullable=False, default='["code"]')
    scope = Column(String(512), nullable=True)
    token_endpoint_auth_method = Column(String(32), default="none", nullable=False)
    created_via = Column(String(16), default="manual", nullable=False)
    is_approved = Column(Boolean, default=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    owner_id = Column(Uuid, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=local_now, nullable=False)
    updated_at = Column(DateTime, default=local_now, onupdate=local_now, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    def redirect_uri_list(self) -> list:
        return _json_list(self.redirect_uris)

    def grant_type_list(self) -> list:
        return _json_list(self.grant_types)

    def to_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "client_name": self.client_name,
            "client_uri": self.client_uri,
            "logo_uri": self.logo_uri,
            "software_id": self.software_id,
            "redirect_uris": self.redirect_uri_list(),
            "grant_types": self.grant_type_list(),
            "response_types": _json_list(self.response_types) or ["code"],
            "scope": self.scope,
            "token_endpoint_auth_method": self.token_endpoint_auth_method,
            "is_confidential": self.client_secret_hash is not None,
            "created_via": self.created_via,
            "is_approved": self.is_approved,
            "is_active": self.is_active,
            "owner_id": str(self.owner_id) if self.owner_id else None,
            "created_at": format_datetime(self.created_at),
            "updated_at": format_datetime(self.updated_at),
            "last_used_at": format_datetime(self.last_used_at),
        }


class OAuthAuthorizationRequest(Base):
    """/authorize 進來、等使用者登入 + 同意的授權請求(短命)。

    使用者可能還沒登入,要先被導去登入頁再回來,所以請求參數得先落地;
    同意後才轉成 OAuthAuthorizationCode。
    """
    __tablename__ = "oauth_authorization_requests"

    id = Column(String(64), primary_key=True)
    client_id = Column(String(64), ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False, index=True)
    redirect_uri = Column(String(512), nullable=False)
    scope = Column(String(512), nullable=True)
    resource = Column(String(256), nullable=True)
    state = Column(String(512), nullable=True)
    code_challenge = Column(String(128), nullable=False)
    code_challenge_method = Column(String(16), default="S256", nullable=False)
    created_at = Column(DateTime, default=local_now, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    decided_at = Column(DateTime, nullable=True)

    client = relationship("OAuthClient")


class OAuthAuthorizationCode(Base):
    """授權碼:只存 hash、一次性、短 TTL、綁 client + redirect_uri + PKCE。"""
    __tablename__ = "oauth_authorization_codes"

    code_hash = Column(String(64), primary_key=True)
    client_id = Column(String(64), ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Uuid, ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False)
    redirect_uri = Column(String(512), nullable=False)
    scope = Column(String(512), nullable=True)
    resource = Column(String(256), nullable=True)
    code_challenge = Column(String(128), nullable=False)
    code_challenge_method = Column(String(16), default="S256", nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=local_now, nullable=False)

    user = relationship("AdminUser")


class OAuthScope(Base):
    """scope 註冊表(metadata 的 scopes_supported 來源)。"""
    __tablename__ = "oauth_scopes"

    name = Column(String(128), primary_key=True)
    description = Column(String(256), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=local_now, nullable=False)

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description, "is_default": self.is_default}


class OAuthToken(Base):
    """已簽發的 token 紀錄(access / refresh)。

    JWT 本身是自包含的,MCP server 用 JWKS 離線驗;這張表讓管理台能列出「誰對哪個
    服務有存取權」、撤銷(introspect 會查 revoked_at)、以及 refresh token 輪替追蹤。
    kind = access | refresh | pat(管理台簽的 personal access token,本質也是 access)。
    """
    __tablename__ = "oauth_tokens"

    jti = Column(String(64), primary_key=True)
    kind = Column(String(16), nullable=False, index=True)
    # 刪除 client 時保留 token 歷史(client_id 變 NULL、client_name_snapshot 留名字)
    client_id = Column(String(64), ForeignKey("oauth_clients.client_id", ondelete="SET NULL"), nullable=True, index=True)
    client_name_snapshot = Column(String(128), nullable=True)
    user_id = Column(Uuid, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True)
    sub = Column(String(128), nullable=False)
    audience = Column(String(256), nullable=True, index=True)
    service_id = Column(Uuid, ForeignKey("services.id", ondelete="SET NULL"), nullable=True, index=True)
    scope = Column(String(512), nullable=True)
    label = Column(String(128), nullable=True)
    parent_jti = Column(String(64), nullable=True)
    issued_at = Column(DateTime, default=local_now, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    revoke_reason = Column(String(64), nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    last_used_ip = Column(String(45), nullable=True)
    use_count = Column(Integer, default=0, nullable=False)

    client = relationship("OAuthClient")
    user = relationship("AdminUser")
    service = relationship("Service")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < local_now()

    def to_dict(self) -> dict:
        return {
            "jti": self.jti,
            "kind": self.kind,
            "client_id": self.client_id,
            "client_name": self.client.client_name if self.client else self.client_name_snapshot,
            "client_deleted": self.client is None and self.client_name_snapshot is not None,
            "user_id": str(self.user_id) if self.user_id else None,
            "user_email": self.user.email if self.user else None,
            "sub": self.sub,
            "audience": self.audience,
            "service_id": str(self.service_id) if self.service_id else None,
            "service_name": self.service.name if self.service else None,
            "scope": self.scope,
            "scopes": self.scope.split() if self.scope else [],
            "label": self.label,
            "issued_at": format_datetime(self.issued_at),
            "expires_at": format_datetime(self.expires_at),
            "revoked_at": format_datetime(self.revoked_at),
            "revoke_reason": self.revoke_reason,
            "last_used_at": format_datetime(self.last_used_at),
            "last_used_ip": self.last_used_ip,
            "use_count": self.use_count,
            "status": "revoked" if self.is_revoked else ("expired" if self.is_expired else "active"),
        }


class OAuthConsent(Base):
    """使用者對某 client + audience 已授予的 scope(同意頁「記住」的依據)。"""
    __tablename__ = "oauth_consents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True)
    # client 被刪就沒有東西可以再被授權,同意紀錄一起刪(token 歷史另在 oauth_tokens 保留)
    client_id = Column(String(64), ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False, index=True)
    audience = Column(String(256), nullable=True)
    scope = Column(String(512), nullable=True)
    granted_at = Column(DateTime, default=local_now, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "client_id", "audience", name="uq_oauth_consent"),)

    client = relationship("OAuthClient")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "client_id": self.client_id,
            "client_name": self.client.client_name if self.client else None,
            "audience": self.audience,
            "scopes": self.scope.split() if self.scope else [],
            "granted_at": format_datetime(self.granted_at),
        }


class TokenUsage(Base):
    """token 事件流(發證 / 內省 / 撤銷),供 dashboard 統計。"""
    __tablename__ = "token_usage"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    jti = Column(String(64), nullable=True, index=True)
    event = Column(String(16), nullable=False, default="issued", index=True)  # issued / introspect / revoked
    grant_type = Column(String(32), nullable=True)
    client_id = Column(String(64), nullable=True, index=True)
    sub = Column(String(128), nullable=True)
    audience = Column(String(256), nullable=True, index=True)
    service_id = Column(Uuid, ForeignKey("services.id", ondelete="SET NULL"), nullable=True, index=True)
    success = Column(Boolean, default=True, nullable=False)
    ip_address = Column(String(45), nullable=True)
    used_at = Column(DateTime, default=local_now, nullable=False, index=True)

    service = relationship("Service")


# ==================== 審計 ====================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    action = Column(String(64), nullable=False, index=True)
    resource_type = Column(String(32), nullable=False, index=True)
    resource_id = Column(String(128), nullable=True)
    actor_type = Column(String(32), nullable=False)
    actor_id = Column(String(128), nullable=True)
    actor_name = Column(String(128), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(256), nullable=True)
    request_path = Column(String(256), nullable=True)
    request_method = Column(String(10), nullable=True)
    status = Column(String(16), nullable=False, index=True)
    status_code = Column(String(10), nullable=True)
    error_message = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=local_now, nullable=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "request_path": self.request_path,
            "request_method": self.request_method,
            "status": self.status,
            "status_code": self.status_code,
            "error_message": self.error_message,
            "details": json.loads(self.details) if self.details else None,
            "created_at": format_datetime(self.created_at),
        }


# ==================== Managed / BYO MCP ====================

class ManagedMcpProcess(Base):
    """由 MCP Center 用 Docker 啟動的 MCP(來自 marketplace catalog 或 BYO 定義)。"""
    __tablename__ = "managed_mcp_processes"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(64), nullable=False, index=True)
    catalog_id = Column(String(64), nullable=False, index=True)
    service_id = Column(Uuid, ForeignKey("services.id", ondelete="SET NULL"), nullable=True, index=True)
    docker_image = Column(String(256), nullable=False)
    image_args = Column(String(512), nullable=True)
    image_command = Column(Text, nullable=True)
    env_vars_encrypted = Column(Text, nullable=True)
    bridge_type = Column(String(32), nullable=False, default="supergateway")
    port = Column(Integer, nullable=True)
    auto_port = Column(Boolean, nullable=False, default=True)
    desired_state = Column(String(16), nullable=False, default="stopped")
    actual_state = Column(String(16), nullable=False, default="unknown")
    container_id = Column(String(128), nullable=True)
    bridge_container_id = Column(String(128), nullable=True)
    last_error = Column(Text, nullable=True)
    last_log_lines = Column(Text, nullable=True)
    created_at = Column(DateTime, default=local_now, nullable=False)
    updated_at = Column(DateTime, default=local_now, onupdate=local_now, nullable=False)
    created_by = Column(Uuid, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)

    service = relationship("Service", foreign_keys=[service_id])
    creator = relationship("AdminUser", foreign_keys=[created_by])

    def get_env_var_names(self) -> list:
        if not self.env_vars_encrypted:
            return []
        try:
            from src.utils.crypto import decrypt_token
            raw = decrypt_token(self.env_vars_encrypted)
            data = json.loads(raw) if raw else {}
            return list(data.keys())
        except Exception:
            return []

    def get_env_vars(self) -> dict:
        """解密成明文 dict —— 僅供 orchestrator 啟動容器用,絕不可回傳到 API / log。"""
        if not self.env_vars_encrypted:
            return {}
        from src.utils.crypto import decrypt_token
        raw = decrypt_token(self.env_vars_encrypted)
        return json.loads(raw) if raw else {}

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "catalog_id": self.catalog_id,
            "service_id": str(self.service_id) if self.service_id else None,
            "docker_image": self.docker_image,
            "image_args": self.image_args,
            "env_var_names": self.get_env_var_names(),
            "bridge_type": self.bridge_type,
            "port": self.port,
            "auto_port": self.auto_port,
            "desired_state": self.desired_state,
            "actual_state": self.actual_state,
            "container_id": self.container_id,
            "bridge_container_id": self.bridge_container_id,
            "last_error": self.last_error,
            "created_at": format_datetime(self.created_at),
            "updated_at": format_datetime(self.updated_at),
            "created_by": str(self.created_by) if self.created_by else None,
        }


class UserMcpDefinition(Base):
    """使用者自帶(BYO)的 stdio MCP 啟動定義({command, args, env schema})。"""
    __tablename__ = "user_mcp_definitions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(64), nullable=False, unique=True, index=True)
    command = Column(String(32), nullable=False)
    args_json = Column(Text, nullable=True)
    container_port = Column(Integer, nullable=False, default=8000)
    env_schema_json = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created_by_id = Column(Uuid, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=local_now)

    def get_args(self) -> list:
        return _json_list(self.args_json)

    def get_env_schema(self) -> list:
        return _json_list(self.env_schema_json)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "command": self.command,
            "args": self.get_args(),
            "container_port": self.container_port,
            "env_schema": self.get_env_schema(),
            "description": self.description,
            "created_by_id": str(self.created_by_id) if self.created_by_id else None,
            "created_at": format_datetime(self.created_at),
        }
