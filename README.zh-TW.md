# MCP Center

**你的 MCP server 們共用的 OAuth 2.1 Authorization Server + 管理台。**

MCP Center 讓每一台用 [FastMCP](https://github.com/PrefectHQ/fastmcp) 寫的 MCP server 都只需要三行設定就能受標準 OAuth 保護,
而 Claude / Cursor / Claude Code 這些 MCP client 則能靠內建的 OAuth 流程(動態註冊 + PKCE)自動連上——不用再自己發 token、寫驗證 API。

```
┌──────────────────────┐   1. 401 + resource metadata    ┌──────────────────────┐
│  MCP client          │ ─────────────────────────────▶ │  你的 FastMCP server  │
│  (Claude / Cursor /  │ ◀───────────────────────────── │  (Resource Server)   │
│   Claude Code / …)   │   5. Authorization: Bearer JWT  │                      │
└──────────┬───────────┘                                 └──────────┬───────────┘
           │ 2. discovery + DCR                                     │ 4. 抓 JWKS 公鑰,離線驗簽
           │ 3. authorize(PKCE)→ 同意頁 → code → token              │    (iss / aud / exp / scope)
           ▼                                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  MCP Center = OAuth 2.1 Authorization Server + 管理台                          │
│  /.well-known/oauth-authorization-server  /.well-known/jwks.json             │
│  /oauth/register  /oauth/authorize  /oauth/token  /oauth/revoke  /oauth/introspect │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 功能

- **標準 OAuth 2.1 AS**:RFC 8414 metadata、RFC 7591 動態註冊、authorization code + PKCE(S256)、refresh token 輪替與重放偵測、RFC 7009 撤銷、RFC 7662 內省、RFC 8707 resource → audience 綁定、RFC 9207 `iss` 回應。
- **RS256 + JWKS**:私鑰只在 MCP Center(AES 加密入庫、可輪替),MCP server 只拿公鑰。
- **同意頁**:動態註冊的 client 第一次連線要人按「允許」;可記住;管理台手動登記的 client 免同意。
- **Personal Access Token**:管理台直接簽長效 token,貼到 `Authorization: Bearer` 就能用(給 CLI / 腳本 / 不支援 OAuth 的 client)。
- **MCP server 目錄**:登錄、掃描發現、健康監控(每 30 秒)、tools 同步、一鍵產生接入設定片段。
- **Marketplace + Docker orchestrator**:從 catalog 一鍵部署 MCP server;或貼一段 `{command, args, env}`(BYO)容器化成 HTTP MCP。
- **管理台登入**:email + 密碼;GitHub / Google 登入接口(填 client_id 即啟用)。
- **零設定啟動**:SQLite 單檔、密鑰自動產生,`git clone` 後兩個指令就能跑。

## 快速開始

需求:Python 3.11+、[uv](https://docs.astral.sh/uv/)、(前端開發才需要)Node.js 18+。

```bash
git clone https://github.com/xianhong1208/MCP_Center.git
cd MCP_Center
uv sync
cp .env.example .env          # 可以先不改
uv run python main.py
```

打開 <http://localhost:4568/setup> 建立擁有者帳號,登入後就是管理台。

> 想要一開機就有帳號:在 `.env` 設 `ADMIN_EMAIL` / `ADMIN_PASSWORD`。
> 要對外部署:一定要把 `OAUTH_ISSUER` 改成公開網址(它會寫進每個 token 的 `iss`,MCP server 靠它做 discovery)。

## 讓一台 FastMCP server 受保護

1. 管理台 → **Services** → 新增(host / port / path)。服務的 *audience* 預設就是它的 MCP URL,例如 `http://127.0.0.1:8000/mcp`。
2. 服務詳情頁的 **Integration** 面板會產生下面這段(也可以直接照抄改):

```python
from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from pydantic import AnyHttpUrl

auth = RemoteAuthProvider(
    token_verifier=JWTVerifier(
        jwks_uri="http://localhost:4568/.well-known/jwks.json",
        issuer="http://localhost:4568",
        audience="http://127.0.0.1:8000/mcp",   # = 管理台上這個服務的 audience
    ),
    authorization_servers=[AnyHttpUrl("http://localhost:4568")],
    base_url="http://127.0.0.1:8000",
)
mcp = FastMCP(name="demo", auth=auth)

@mcp.tool
def hello(name: str) -> str:
    return f"Hello, {name}!"

mcp.run(transport="http", host="127.0.0.1", port=8000)
```

完整範例:[`examples/fastmcp_server.py`](examples/fastmcp_server.py)。FastMCP 會自動提供 `/.well-known/oauth-protected-resource`,指向 MCP Center。

## 讓 client 連上

**支援 OAuth 的 client(Claude Code / Claude Desktop / Cursor / FastMCP Client)** — 什麼都不用先做:

```bash
claude mcp add --transport http demo http://127.0.0.1:8000/mcp
```

第一次連線時 client 會自動向 MCP Center 註冊、開瀏覽器到同意頁,你按「允許」就完成。

**不支援 OAuth 的 client / 腳本** — 管理台 → **Issue Token** 簽一個 Personal Access Token:

```bash
claude mcp add --transport http demo http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer <PERSONAL_ACCESS_TOKEN>"
```

```python
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

async with Client("http://127.0.0.1:8000/mcp", auth=BearerAuth("<PERSONAL_ACCESS_TOKEN>")) as c:
    print(await c.list_tools())
```

## 設定

所有設定在 [`config/config.yaml`](config/config.yaml),敏感值由環境變數(`.env`)帶入。常用的:

| 環境變數 | 預設 | 說明 |
|---|---|---|
| `OAUTH_ISSUER` | `http://localhost:4568` | token 的 `iss` 與 discovery 網址,**程式也直接 bind 這裡的 port**。對外部署必改。 |
| `DATABASE_URL` | `sqlite:///data/mcp_center.db` | 改成 `postgresql://…` 即用 PostgreSQL(`uv sync --extra postgres`)。 |
| `SESSION_SECRET_KEY` / `ENCRYPTION_KEY` | 自動產生 | 留空會產生並存到 `data/secrets.json`;`ENCRYPTION_KEY` 設定後**不可再換**。 |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | — | 首次啟動自動建立擁有者;不設就走 `/setup`。 |
| `OAUTH_DCR_AUTO_APPROVE` | `true` | 動態註冊的 client 免審核(同意頁仍是閘門);設 `false` 需在管理台核准。 |
| `OAUTH_ACCESS_EXPIRE_MINUTES` / `OAUTH_REFRESH_EXPIRE_DAYS` | `60` / `30` | token 有效期。 |
| `GITHUB_CLIENT_ID(_SECRET)` / `GOOGLE_CLIENT_ID(_SECRET)` | — | 管理台第三方登入;callback 為 `<issuer>/api/session/oauth/<provider>/callback`。 |
| `SECURE_COOKIE` | `false` | HTTPS 部署時設 `true`。 |
| `ENABLE_API_DOCS` | — | 設 `true` 開 `/docs`。 |

## 端點總覽

| 類別 | 端點 |
|---|---|
| OAuth(公開) | `GET /.well-known/oauth-authorization-server`、`GET /.well-known/jwks.json`、`POST /oauth/register`、`GET /oauth/authorize`、`POST /oauth/token`、`POST /oauth/revoke`、`POST /oauth/introspect` |
| 管理台登入 | `/api/session/status|setup|login|logout|me`、`/api/session/oauth/{github,google}/start` |
| 管理 API(需登入) | `/api/services*`、`/api/oauth/{clients,scopes,tokens,consents,keys,activity,overview,snippets}`、`/api/discovery/*`、`/api/marketplace*`、`/api/managed*`、`/api/byo-mcp*`、`/api/stats/*`、`/api/audit/*`、`/api/system/*` |

設 `ENABLE_API_DOCS=true` 後 <http://localhost:4568/docs> 有完整 OpenAPI。

### 只需要設 `OAUTH_ISSUER`

`OAUTH_ISSUER` 是**別人看到的公開網址**(寫進 token 的 `iss` 與 discovery 文件),程式會直接 bind 它的 port:

| 情境 | `OAUTH_ISSUER` | 實際 bind |
|---|---|---|
| 本機開發 | `http://localhost:4568` | `0.0.0.0:4568` |
| 區網其他機器要用 | `http://192.168.1.10:4568` | `0.0.0.0:4568` |
| nginx / 網域 | `https://mcp.yourdomain.com` | `0.0.0.0:4568`(URL 沒 port 就用 4568,由 nginx 轉進來) |

只有 bind 位址要和 issuer 不同時(例如反向代理後面只想聽 `127.0.0.1`)才需要進階變數 `SERVER_HOST` / `SERVER_PORT`。

## 撤銷與有效期(值得知道)

MCP server 用 JWKS **離線**驗簽,所以在管理台撤銷一個 access token,對「只驗簽」的 server 不會立即生效(要等它過期);
撤銷會立刻讓 refresh 失效、也會讓 `/oauth/introspect` 回 `active=false`。要即時撤銷就把 access 有效期調短,或在 FastMCP 端改用
`IntrospectionTokenVerifier(introspection_url="<issuer>/oauth/introspect", client_id=..., client_secret=...)`(client 在管理台登記為 confidential)。

## 開發

```bash
uv sync --all-groups
uv run pytest                       # 後端測試(SQLite 暫存檔,含與真實 FastMCP 的互通測試)
uv run ruff check src db main.py

cd frontend && npm install
npm run dev                         # http://localhost:5173,API 代理到 4568
npm run build                       # 輸出到 ../static/web,由後端一起 serve
```

DB schema 變更:改 `db/models.py` → `uv run python main.py --migrate-only generate -m "..."` → 啟動時自動套用。

### 專案結構

```
main.py                 啟動 / FastAPI app 組裝 / SPA
config/config.yaml      設定(環境變數展開)
db/                     models、crud(資料層)、seed、migrate
alembic/                migrations
src/oauth/              OAuth 2.1 AS:signing_keys、service、consent_policy、jwt_utils
src/identity/           管理台登入:passwords、session、providers/(github, google)、service
src/api/                routes(services / stats / audit / system)、oauth_routes、oauth_admin_routes、
                        session_routes、discovery_routes、managed_routes、schemas
src/adapters/           三層架構中間層(只有這裡可以 import db.crud)
src/discovery/          MCP 掃描 / 健康監控 / WebSocket
src/marketplace/        catalog 載入 / argv 政策
src/orchestrator/       Docker 部署 managed / BYO MCP
frontend/               React 管理台
examples/               FastMCP server 範例
tests/                  pytest
```

### 三層不變量

`routes → adapters → db.crud`。只有 `src/adapters/*` 可以 import `db.crud`;route 不直接 `db.commit()`。
`tests/test_architecture_layering.py` 在 CI 守這條線。

## 授權

[MIT](LICENSE)
