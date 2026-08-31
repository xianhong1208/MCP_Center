# Roadmap

## 已完成(1.0.0)
- OAuth 2.1 AS 全流程(discovery / DCR / PKCE / refresh 輪替 / revoke / introspect / consent)
- Personal Access Token、FastMCP 接入範例與互通測試
- 管理台帳密登入 + GitHub / Google 登入接口
- SQLite 預設、單一 init migration

## 規劃中
- **管理台第三方登入實戰驗證**:GitHub / Google 接口已寫好但需真實 client_id 走一次。
- **多 issuer / 反向代理**:issuer 與實際對外 URL 不一致時的提示與自動偵測。
- **Token 使用量觀測**:只有走 introspect 的 MCP server 會回報使用次數;離線驗簽(JWKS)的 server 不會。
  可考慮在 FastMCP 端加一個輕量 usage hook。
- **Client 認證強化**:`private_key_jwt`(RFC 7523)供機器對機器。
- **Scope 依服務差異化**:目前 scope 註冊表是全域;可讓每個服務宣告自己的 scope。
- **Orchestrator**:多主機 / 非 Docker runtime。
