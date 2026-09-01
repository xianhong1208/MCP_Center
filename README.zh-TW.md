# MCP Center

**開源的 OAuth 2.1 Authorization Server 與 Model Context Protocol server 控制台。**

MCP Center 把標準化的身分驗證放在你每一台 MCP server 前面。任何 [FastMCP](https://github.com/PrefectHQ/fastmcp) server 只需三行設定就受到保護;Claude Code、Claude Desktop、Cursor 這類 MCP client 則直接用它們內建的 OAuth 流程連上——不用自訂 token、不用驗證回呼、不用在每台 server 各寫一套驗證。

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-green.svg)](pyproject.toml)
[![OAuth 2.1](https://img.shields.io/badge/OAuth-2.1-6366f1.svg)](#-運作原理)
[![Works with FastMCP](https://img.shields.io/badge/FastMCP-3.x-22c55e.svg)](https://gofastmcp.com)
[![Tests](https://img.shields.io/badge/tests-pytest-informational.svg)](#-開發)

[English](README.md) · [快速開始](#-快速開始) · [運作原理](#-運作原理) · [設定](#️-設定) · [控制台](#-控制台)

```
┌──────────────────────┐   ① 401 + protected-resource metadata   ┌──────────────────────┐
│      MCP client      │ ───────────────────────────────────────▶ │  你的 FastMCP server  │
│ Claude Code / Cursor │ ◀─────────────────────────────────────── │   (resource server)   │
│  Claude Desktop / …  │   ⑤ Authorization: Bearer <JWT>          │                      │
└──────────┬───────────┘                                          └──────────┬───────────┘
           │ ② discovery + 動態註冊(DCR)                                       │ ④ 抓 JWKS 公鑰,離線驗簽
           │ ③ authorize(PKCE)→ 同意頁 → code → token                         │    iss / aud / exp / scope
           ▼                                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  MCP Center — OAuth 2.1 Authorization Server + 控制台                                      │
│  /.well-known/oauth-authorization-server   /.well-known/jwks.json                        │
│  /oauth/register  /oauth/authorize  /oauth/token  /oauth/revoke  /oauth/introspect       │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

## ✨ 主要特色

- **標準化的授權伺服器** — RFC 8414 metadata、RFC 7591 動態註冊、authorization code + PKCE(S256)、refresh token 輪替與重放偵測、RFC 7009 撤銷、RFC 7662 內省、RFC 8707 resource indicator、RFC 9207 `iss` 回應。正是 [MCP 授權規範](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)要求的那一套。
- **非對稱簽章、離線驗證** — RS256 金鑰,公開 JWKS、可輪替。MCP server 用公鑰在本地驗 token;MCP Center 不在請求路徑上。
- **三行接上 FastMCP** — `RemoteAuthProvider` + `JWTVerifier(jwks_uri, issuer, audience)` 就完成保護。token 綁定每台 server 的 audience,給 A 的 token 永遠不能打 B。
- **同意頁** — 動態註冊的 client 第一次連線要請擁有者按「允許」;可依 client + server 記住。你自己在控制台登記的 client 免同意。
- **Personal Access Token** — 從控制台簽長效 bearer token 給腳本、CI 與不會走 OAuth 的 client,附上可直接貼的 `claude mcp add` 與 `mcpServers` 片段。
- **服務登錄與健康監控** — 手動登記或自動掃描 MCP server、同步 tools 列表、每 30 秒健康檢查、狀態變更經 WebSocket 即時推播。
- **Marketplace 與 orchestrator** — 從 catalog 一鍵部署 MCP server;或貼一段標準的 `{command, args, env}`,由 MCP Center 容器化並掛上 HTTP bridge。
- **零設定啟動** — 預設 SQLite、首次啟動自動產生密鑰、瀏覽器內的擁有者帳號設定精靈。PostgreSQL 與 GitHub / Google 登入只差幾個環境變數。

## 🚀 安裝

需要 Python 3.11+ 與 [uv](https://docs.astral.sh/uv/)。只有要改控制台前端時才需要 Node.js 18+。

```bash
git clone https://github.com/xianhong1208/MCP_Center.git
cd MCP_Center
uv sync
cp .env.example .env      # 可省略:所有設定都有可用的預設值
uv run python main.py
```

打開 <http://localhost:4568/setup> 建立擁有者帳號,就進入控制台了。

> **不是部署在 `localhost`?** 把 `OAUTH_ISSUER` 設成公開網址(例如 `https://mcp.example.com`)。它會寫進每個 token 的 `iss` 與 discovery 文件,MCP server 和 client 都必須連得到它。

## 🏁 快速開始

### 1. 保護一台 FastMCP server

在控制台登記這台 server(**Services → Register Service**,host / port / path)。它的 *audience* 預設就是它的 MCP URL,例如 `http://127.0.0.1:8000/mcp`。服務頁的 **Integration** 面板會替你產生下面這段:

```python
from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from pydantic import AnyHttpUrl

auth = RemoteAuthProvider(
    token_verifier=JWTVerifier(
        jwks_uri="http://localhost:4568/.well-known/jwks.json",
        issuer="http://localhost:4568",
        audience="http://127.0.0.1:8000/mcp",   # 必須和控制台上的 audience 一致
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

FastMCP 會自動提供 `/.well-known/oauth-protected-resource`,把 client 指向 MCP Center。完整可執行的範例在 [`examples/fastmcp_server.py`](examples/fastmcp_server.py)。

### 2. 連上 client

**支援 OAuth 的 client**(Claude Code、Claude Desktop、Cursor、FastMCP `Client`)什麼都不用先做:

```bash
claude mcp add --transport http demo http://127.0.0.1:8000/mcp
```

第一次使用時 client 會自己向 MCP Center 註冊、在瀏覽器開啟同意頁,你按 **Allow** 之後就拿到 token,之後自動 refresh。

```python
from fastmcp import Client

async with Client("http://127.0.0.1:8000/mcp", auth="oauth") as client:
    print(await client.list_tools())
```

**其他情況** — 腳本、CI、不支援 OAuth 的 client — 在控制台的 **Issue Token** 簽一個 Personal Access Token:

```bash
claude mcp add --transport http demo http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer <PERSONAL_ACCESS_TOKEN>"
```

```python
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

async with Client("http://127.0.0.1:8000/mcp", auth=BearerAuth("<PERSONAL_ACCESS_TOKEN>")) as client:
    print(await client.list_tools())
```

## 🔐 運作原理

MCP Center 扮演 MCP 規範中的 **authorization server**;你的 MCP server 是 **resource server**,從不簽發、也不儲存 token。

| 步驟 | 誰 | 發生什麼事 |
|---|---|---|
| Discovery | client → server → MCP Center | server 回 `401` 並在 `WWW-Authenticate` 指向它的 protected-resource metadata,裡面寫著 MCP Center 是授權伺服器;client 再抓 `/.well-known/oauth-authorization-server`。 |
| 註冊 | client → MCP Center | client 動態註冊(`POST /oauth/register`)拿到 `client_id`。public client 用 PKCE;confidential client 拿到 secret。 |
| 授權 | 瀏覽器 → MCP Center | `/oauth/authorize` 驗證參數、用 `resource` 參數綁定目標 server,顯示同意頁(記住過或受信任的 client 直接略過)。 |
| Token | client → MCP Center | `/oauth/token` 用授權碼(檢查 PKCE、redirect URI、resource)換出 RS256 access token — `iss`、`sub`、`aud`、`scope`、`client_id`、`jti` — 以及 refresh token。 |
| 驗證 | server | server 抓一次 JWKS,之後在本地驗簽章、issuer、audience、有效期與 scope。 |
| 撤銷 | 控制台 / client | 撤銷 refresh token 會讓整條鏈失效;`POST /oauth/introspect` 立刻回 `active: false`。離線驗簽的 access token 會撐到過期,所以預設只有 60 分鐘;需要即時撤銷的 server 改用 `IntrospectionTokenVerifier`。 |

同意頁的政策刻意做得很小、集中在一個地方 — [`src/oauth/consent_policy.py`](src/oauth/consent_policy.py) — 想改「什麼時候要問」就改這裡。

## ⚙️ 設定

所有設定在 [`config/config.yaml`](config/config.yaml),敏感值從環境變數(`.env`)讀取。你可能會碰到的:

| 變數 | 預設 | 用途 |
|---|---|---|
| `OAUTH_ISSUER` | `http://localhost:4568` | MCP Center 的公開網址,同時決定程式 bind 的 port。**非本機部署一定要改。** |
| `DATABASE_URL` | `sqlite:///data/mcp_center.db` | 指向 `postgresql://…` 即改用 PostgreSQL(`uv sync --extra postgres`)。 |
| `SESSION_SECRET_KEY`、`ENCRYPTION_KEY` | 自動產生 | 未設定時存在 `data/secrets.json`。`ENCRYPTION_KEY` 保護私鑰與儲存的 secret,不要隨意更換。 |
| `ADMIN_EMAIL`、`ADMIN_PASSWORD` | — | 首次啟動直接建立擁有者帳號,不用走 `/setup`。 |
| `OAUTH_ACCESS_EXPIRE_MINUTES`、`OAUTH_REFRESH_EXPIRE_DAYS` | `60`、`30` | token 有效期。 |
| `OAUTH_DCR_AUTO_APPROVE` | `true` | 動態註冊的 client 是否立即可用(同意頁仍是閘門),或必須在控制台核准。 |
| `GITHUB_CLIENT_ID/_SECRET`、`GOOGLE_CLIENT_ID/_SECRET` | — | 啟用控制台的 GitHub / Google 登入。Callback:`<issuer>/api/session/oauth/<provider>/callback`。 |
| `SECURE_COOKIE` | `false` | 走 HTTPS 時設 `true`。 |
| `ENABLE_API_DOCS` | — | `true` 會在 `/docs` 開放 OpenAPI。 |

進階:`SERVER_HOST` / `SERVER_PORT` 可覆寫 bind 位址,只在它必須和 issuer 不同時使用(例如反向代理後面只聽 `127.0.0.1`)。

## 🖥 控制台

| 頁面 | 在這裡做什麼 |
|---|---|
| **Dashboard** | 服務健康、token 活動、最近事件、系統狀態。 |
| **Services** | 登記 / 掃描 MCP server、設定 audience 與允許的 scope、更新 tools、健康檢查、接入片段。 |
| **Tokens · Issue Token** | MCP Center 簽發過的所有 token — OAuth 授權與 Personal Access Token — 含撤銷、到期與最後使用資訊。 |
| **OAuth Clients** | 動態註冊與受信任的 client,核准 / 撤銷 / 刪除,scope 註冊表,簽章金鑰輪替。 |
| **Marketplace** | 從 catalog 部署 MCP server,或自帶 `{command, args, env}`。 |
| **Audit Logs** | 誰、何時、從哪裡、做了什麼。 |

用 email + 密碼登入,設定好之後也可用 GitHub / Google。控制台刻意設計為單租戶:登入的人就是管理員。

## 📚 API 總覽

| 類別 | 端點 |
|---|---|
| OAuth(公開) | `GET /.well-known/oauth-authorization-server` · `GET /.well-known/jwks.json` · `POST /oauth/register` · `GET /oauth/authorize` · `POST /oauth/token` · `POST /oauth/revoke` · `POST /oauth/introspect` |
| 控制台 session | `/api/session/status · setup · login · logout · me` · `/api/session/oauth/{github,google}/start` |
| 管理 API(需登入) | `/api/services*` · `/api/oauth/{clients,scopes,tokens,consents,keys,activity,overview,snippets}` · `/api/discovery/*` · `/api/marketplace*` · `/api/managed*` · `/api/byo-mcp*` · `/api/stats/*` · `/api/audit/*` · `/api/system/*` |

設 `ENABLE_API_DOCS=true` 後 `/docs` 有完整 OpenAPI 參考。

## 🛠 開發

```bash
uv sync --all-groups
uv run pytest                       # 後端測試,含與真實 FastMCP 的互通測試
uv run ruff check src db main.py

cd frontend && npm install
npm run dev                         # Vite 在 :5173,API 代理到 :4568
npm run build                       # 輸出到 static/web,由後端一起 serve
```

Schema 變更:改 `db/models.py`,然後 `uv run python main.py --migrate-only generate -m "描述變更"`。啟動時自動套用 migration。

```
main.py              程式進入點與 app 組裝
config/              config.yaml(支援環境變數展開)
db/                  models · crud(資料層)· seed · migrate · alembic/
src/oauth/           授權伺服器:簽章金鑰、grant、同意政策
src/identity/        控制台登入:密碼、session、GitHub / Google provider
src/api/             routers:oauth、session、services、discovery、marketplace、stats、audit
src/adapters/        唯一可以 import db.crud 的層
src/discovery/       掃描器、健康監控、WebSocket 廣播
src/orchestrator/    以 Docker 管理的 managed / 自帶 MCP server
frontend/            React 控制台(Vite + Tailwind)
examples/            FastMCP server 範例
tests/               pytest 測試
```

CI 守住的架構規則:`routes → adapters → db.crud`。只有 `src/adapters/*` 可以 import `db.crud`,route 不直接呼叫 `db.commit()`(`tests/test_architecture_layering.py`)。

## 🤝 貢獻

歡迎 issue 與 pull request。改動請保持聚焦,為你碰到的行為補上或更新測試,送 PR 前跑過 `uv run pytest` 與 `npm run build`。

## 📄 授權

[MIT](LICENSE)
