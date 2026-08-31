# Changelog

## 1.0.0 — 2026-08-31

個人專案第一版。從原本的企業內部「Token Server」重寫為 **MCP 生態系的 OAuth 2.1 Authorization Server + 管理台**。

### 核心
- MCP Center 自己當 Authorization Server:RS256 簽章、`/.well-known/oauth-authorization-server`(RFC 8414)、
  `/.well-known/jwks.json`、動態註冊(RFC 7591)、authorization code + PKCE(S256)、refresh token 輪替與重放偵測、
  撤銷(RFC 7009)、內省(RFC 7662)、resource → audience 綁定(RFC 8707)、同意頁。
- FastMCP server 只需 `JWTVerifier(jwks_uri, issuer, audience)` 即可驗證,不再回呼任何自訂端點。
- 管理台可直接簽發 Personal Access Token(貼到 `Authorization: Bearer` 即可用)。
- 管理台登入:email + 密碼(bcrypt),另留 GitHub / Google 登入接口(填 client_id 即啟用)。
- 首次啟動走 `/setup` 建立擁有者帳號;密鑰(session / 加密)未設定時自動產生並存到 `data/secrets.json`。

### 移除
- 自家 opaque token、HS256 JWT、`/auth/verify` 回呼式驗證。
- RBAC(角色 / 權限)、多使用者管理、Service 成員、安全問題、Email 驗證、註冊審核、License 授權檔。

### 基礎
- 預設 SQLite(零依賴),PostgreSQL 可選;主鍵改用 SQLAlchemy 通用 `Uuid`。
- Alembic 從單一 `init` migration 重新開始。
- 保留:服務登錄 / 掃描 / 健康監控 / tools 同步、Marketplace + Docker orchestrator、BYO MCP、審計日誌。
