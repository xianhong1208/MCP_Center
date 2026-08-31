"""配置模型定義"""

from typing import Dict, List

from pydantic import BaseModel


class DatabaseConfig(BaseModel):
    """資料庫配置

    預設 SQLite 單檔(零依賴);設 DATABASE_URL 為 postgresql://... 即切換 PostgreSQL。
    """
    url: str = "sqlite:///data/mcp_center.db"
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    # 0 = 從 oauth.issuer 推(見 ConfigModel.effective_port)
    port: int = 0


class SessionConfig(BaseModel):
    """管理台登入 session(httpOnly cookie 內的 HS256 JWT)。

    secret_key 為空時由 secrets store 自動產生並持久化(data/secrets.json)。
    """
    secret_key: str = ""
    expire_hours: int = 12
    idle_timeout_minutes: int = 30


class OAuthConfig(BaseModel):
    """OAuth 2.1 Authorization Server 設定。

    issuer 會寫進每個簽發 JWT 的 iss claim 與 discovery metadata,是所有 MCP server
    驗 token 的信任錨點;對外部署時務必填公開網址(變更後既有 token 全部失效)。
    """
    issuer: str = "http://localhost:4568"
    signing_key_bits: int = 2048
    access_expire_minutes: int = 60
    refresh_expire_days: int = 30
    auth_code_ttl_seconds: int = 120
    # 個人專案預設:動態註冊(DCR)的 client 直接可用;人的同意頁才是真正的閘門。
    dcr_auto_approve: bool = True
    # 管理台直接簽發的 Personal Access Token 可設定的最長天數
    pat_max_days: int = 365


class OAuthLoginProviderConfig(BaseModel):
    """管理台第三方登入(GitHub / Google)接口設定。client_id 為空即停用。"""
    client_id: str = ""
    client_secret: str = ""


class IdentityConfig(BaseModel):
    """管理台身分驗證:本地帳密 + 可插拔的第三方登入。"""
    local_enabled: bool = True
    github: OAuthLoginProviderConfig = OAuthLoginProviderConfig()
    google: OAuthLoginProviderConfig = OAuthLoginProviderConfig()
    # 允許用第三方登入的 email 白名單(空 = 只允許已存在的帳號)
    allowed_emails: List[str] = []
    # 首次啟動時自動建立的擁有者帳號(兩者皆設才建立;之後可用 /setup 頁面建立)
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""


class RateLimitConfig(BaseModel):
    enabled: bool = True
    requests_per_minute: int = 120
    requests_per_hour: int = 2000
    whitelist: List[str] = ["127.0.0.1", "localhost", "::1"]
    path_limits: Dict[str, int] = {}


class SecurityConfig(BaseModel):
    trusted_proxies: List[str] = ["127.0.0.1", "::1"]
    # cookie 的 Secure 旗標;走 HTTPS 部署時設 true
    secure_cookie: bool = False
    cookie_samesite: str = "lax"


class CORSConfig(BaseModel):
    allowed_origins: List[str] = ["http://localhost:4568", "http://localhost:5173"]
    allow_methods: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers: List[str] = ["Content-Type", "Authorization", "X-Requested-With"]
    allow_credentials: bool = True


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "colorized"
    log_dir: str = "logs"
    rotation: str = "00:00"
    rotation_max_size: str = "50 MB"
    retention: str = "30 days"
    compression: str = "zip"


DEFAULT_PORT = 4568


class ConfigModel(BaseModel):
    database: DatabaseConfig = DatabaseConfig()
    server: ServerConfig = ServerConfig()
    session: SessionConfig = SessionConfig()
    oauth: OAuthConfig = OAuthConfig()
    identity: IdentityConfig = IdentityConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    security: SecurityConfig = SecurityConfig()
    cors: CORSConfig = CORSConfig()
    logging: LoggingConfig = LoggingConfig()

    @property
    def effective_port(self) -> int:
        """實際 bind 的 port:明確設定 > OAUTH_ISSUER 裡的 port > 4568。

        issuer 是 https 網域(反向代理)時 URL 沒有 port,回 4568 讓 nginx 轉過來。
        """
        if self.server.port and self.server.port > 0:
            return self.server.port
        from urllib.parse import urlparse
        try:
            explicit = urlparse(self.oauth.issuer).port
        except ValueError:
            explicit = None
        return explicit or DEFAULT_PORT
