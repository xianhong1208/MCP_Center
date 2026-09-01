# MCP Center

**An open-source OAuth 2.1 Authorization Server and control plane for your Model Context Protocol servers.**

MCP Center puts standards-based authentication in front of every MCP server you run. Any [FastMCP](https://github.com/PrefectHQ/fastmcp) server becomes protected with three lines of configuration, and MCP clients such as Claude Code, Claude Desktop and Cursor connect through the OAuth flow they already implement — no custom tokens, no verification callbacks, no per-server auth code.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-green.svg)](pyproject.toml)
[![OAuth 2.1](https://img.shields.io/badge/OAuth-2.1-6366f1.svg)](#how-it-works)
[![Works with FastMCP](https://img.shields.io/badge/FastMCP-3.x-22c55e.svg)](https://gofastmcp.com)
[![Tests](https://img.shields.io/badge/tests-pytest-informational.svg)](#development)

[繁體中文](README.zh-TW.md) · [Quick Start](#-quick-start) · [How it works](#-how-it-works) · [Configuration](#-configuration) · [Console](#-the-console)

```
┌──────────────────────┐   ① 401 + protected-resource metadata   ┌──────────────────────┐
│      MCP client      │ ───────────────────────────────────────▶ │   your FastMCP server │
│ Claude Code / Cursor │ ◀─────────────────────────────────────── │   (resource server)   │
│  Claude Desktop / …  │   ⑤ Authorization: Bearer <JWT>          │                      │
└──────────┬───────────┘                                          └──────────┬───────────┘
           │ ② discovery + dynamic client registration                       │ ④ fetch JWKS, verify
           │ ③ authorize (PKCE) → consent → code → token                     │    iss / aud / exp / scope
           ▼                                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  MCP Center — OAuth 2.1 Authorization Server + console                                    │
│  /.well-known/oauth-authorization-server   /.well-known/jwks.json                        │
│  /oauth/register  /oauth/authorize  /oauth/token  /oauth/revoke  /oauth/introspect       │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

## ✨ Key Features

- **Standards-based authorization server** — RFC 8414 metadata, RFC 7591 dynamic client registration, authorization code + PKCE (S256), refresh-token rotation with replay detection, RFC 7009 revocation, RFC 7662 introspection, RFC 8707 resource indicators and RFC 9207 `iss` responses. Exactly what the [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) asks for.
- **Asymmetric signing, offline verification** — RS256 keys with JWKS publishing and rotation. MCP servers verify tokens locally with their public key; MCP Center is never on the request path.
- **Three-line FastMCP integration** — `RemoteAuthProvider` + `JWTVerifier(jwks_uri, issuer, audience)` and your server is protected. Tokens are bound to each server's audience, so a token for one server never works on another.
- **Consent screen** — dynamically registered clients ask the owner for permission on first connect; decisions can be remembered per client and server. Clients you register yourself skip the prompt.
- **Personal access tokens** — mint long-lived bearer tokens from the console for scripts, CI and clients that cannot run an OAuth flow, complete with ready-to-paste `claude mcp add` and `mcpServers` snippets.
- **Server registry and health** — register or auto-discover MCP servers, sync their tool lists, monitor health every 30 seconds and stream status changes over WebSocket.
- **Marketplace and orchestrator** — deploy MCP servers from a catalog with one click, or paste a standard `{command, args, env}` block and let MCP Center containerize it behind an HTTP bridge.
- **Zero-config start** — SQLite by default, secrets generated on first run, an in-browser setup wizard for the owner account. PostgreSQL and GitHub / Google sign-in are a few environment variables away.

## 🚀 Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). Node.js 18+ is only needed if you work on the console UI.

```bash
git clone https://github.com/xianhong1208/MCP_Center.git
cd MCP_Center
uv sync
cp .env.example .env      # optional: everything has a working default
uv run python main.py
```

Open <http://localhost:4568/setup>, create the owner account, and you are in the console.

> **Deploying somewhere other than `localhost`?** Set `OAUTH_ISSUER` to the public URL (for example `https://mcp.example.com`). It is written into every token as `iss` and into the discovery document, so it has to be reachable by your MCP servers and clients.

## 🏁 Quick Start

### 1. Protect a FastMCP server

Register the server in the console (**Services → Register Service**, host / port / path). Its *audience* defaults to its MCP URL, e.g. `http://127.0.0.1:8000/mcp`. The **Integration** panel on the service page generates the snippet below for you:

```python
from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from pydantic import AnyHttpUrl

auth = RemoteAuthProvider(
    token_verifier=JWTVerifier(
        jwks_uri="http://localhost:4568/.well-known/jwks.json",
        issuer="http://localhost:4568",
        audience="http://127.0.0.1:8000/mcp",   # must match the audience in the console
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

FastMCP serves `/.well-known/oauth-protected-resource` automatically, pointing clients at MCP Center. A complete runnable example lives in [`examples/fastmcp_server.py`](examples/fastmcp_server.py).

### 2. Connect a client

**Clients that speak OAuth** (Claude Code, Claude Desktop, Cursor, the FastMCP `Client`) need nothing up front:

```bash
claude mcp add --transport http demo http://127.0.0.1:8000/mcp
```

On first use the client registers itself with MCP Center, opens the consent screen in your browser, and receives a token after you click **Allow**. Refreshing happens automatically afterwards.

```python
from fastmcp import Client

async with Client("http://127.0.0.1:8000/mcp", auth="oauth") as client:
    print(await client.list_tools())
```

**Everything else** — scripts, CI jobs, clients without OAuth — uses a personal access token issued from **Issue Token** in the console:

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

## 🔐 How it works

MCP Center plays the **authorization server** role from the MCP specification. Your MCP servers are **resource servers**; they never issue or store tokens.

| Step | Who | What happens |
|---|---|---|
| Discovery | client → server → MCP Center | The server answers `401` with a `WWW-Authenticate` pointing at its protected-resource metadata, which names MCP Center as the authorization server. The client fetches `/.well-known/oauth-authorization-server`. |
| Registration | client → MCP Center | The client registers dynamically (`POST /oauth/register`) and gets a `client_id`. Public clients use PKCE; confidential clients get a secret. |
| Authorization | browser → MCP Center | `/oauth/authorize` validates the request, binds it to the target server via the `resource` parameter, and shows the consent screen (or skips it for remembered / trusted clients). |
| Token | client → MCP Center | `/oauth/token` exchanges the code (checking PKCE, redirect URI and resource) for an RS256 access token — `iss`, `sub`, `aud`, `scope`, `client_id`, `jti` — plus a refresh token. |
| Verification | server | The server fetches JWKS once, then verifies signature, issuer, audience, expiry and scopes locally. |
| Revocation | console / client | Revoking a refresh token kills its whole family; `POST /oauth/introspect` reports `active: false` immediately. Access tokens verified offline stay valid until they expire, so keep them short (60 minutes by default) or use `IntrospectionTokenVerifier` on servers that need instant revocation. |

The consent policy is deliberately small and lives in one place — [`src/oauth/consent_policy.py`](src/oauth/consent_policy.py) — so you can change when the prompt appears.

## ⚙️ Configuration

All settings live in [`config/config.yaml`](config/config.yaml) and read their secrets from environment variables (`.env`). The ones you are likely to touch:

| Variable | Default | Purpose |
|---|---|---|
| `OAUTH_ISSUER` | `http://localhost:4568` | Public URL of MCP Center. Also decides the port the server binds. **Change this for any non-local deployment.** |
| `DATABASE_URL` | `sqlite:///data/mcp_center.db` | Point at `postgresql://…` to use PostgreSQL (`uv sync --extra postgres`). |
| `SESSION_SECRET_KEY`, `ENCRYPTION_KEY` | auto-generated | Stored in `data/secrets.json` when unset. `ENCRYPTION_KEY` protects private keys and stored secrets — never rotate it casually. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | — | Create the owner account at first start instead of using `/setup`. |
| `OAUTH_ACCESS_EXPIRE_MINUTES`, `OAUTH_REFRESH_EXPIRE_DAYS` | `60`, `30` | Token lifetimes. |
| `OAUTH_DCR_AUTO_APPROVE` | `true` | Whether dynamically registered clients are usable immediately (the consent screen still gates them) or must be approved in the console. |
| `GITHUB_CLIENT_ID/_SECRET`, `GOOGLE_CLIENT_ID/_SECRET` | — | Enable GitHub / Google sign-in for the console. Callback: `<issuer>/api/session/oauth/<provider>/callback`. |
| `SECURE_COOKIE` | `false` | Set to `true` behind HTTPS. |
| `ENABLE_API_DOCS` | — | `true` exposes OpenAPI at `/docs`. |

Advanced: `SERVER_HOST` / `SERVER_PORT` override the bind address when it must differ from the issuer (e.g. listening on `127.0.0.1` behind a reverse proxy).

## 🖥 The Console

| Page | What you do there |
|---|---|
| **Dashboard** | Service health, token activity, recent events, system status. |
| **Services** | Register / scan MCP servers, set audience and allowed scopes, refresh tools, health checks, integration snippets. |
| **Tokens · Issue Token** | Every token issued by MCP Center — OAuth grants and personal access tokens — with revoke, expiry and last-use information. |
| **OAuth Clients** | Dynamically registered and trusted clients, approve / revoke / delete, scope registry, signing-key rotation. |
| **Marketplace** | Deploy MCP servers from the catalog or bring your own `{command, args, env}`. |
| **Audit Logs** | Who did what, when, from where. |

Sign in with email and password, or with GitHub / Google once configured. The console is single-tenant by design: whoever signs in is the administrator.

## 📚 API Overview

| Group | Endpoints |
|---|---|
| OAuth (public) | `GET /.well-known/oauth-authorization-server` · `GET /.well-known/jwks.json` · `POST /oauth/register` · `GET /oauth/authorize` · `POST /oauth/token` · `POST /oauth/revoke` · `POST /oauth/introspect` |
| Console session | `/api/session/status · setup · login · logout · me` · `/api/session/oauth/{github,google}/start` |
| Management (authenticated) | `/api/services*` · `/api/oauth/{clients,scopes,tokens,consents,keys,activity,overview,snippets}` · `/api/discovery/*` · `/api/marketplace*` · `/api/managed*` · `/api/byo-mcp*` · `/api/stats/*` · `/api/audit/*` · `/api/system/*` |

Set `ENABLE_API_DOCS=true` for the full OpenAPI reference at `/docs`.

## 🛠 Development

```bash
uv sync --all-groups
uv run pytest                       # backend tests, including a live FastMCP interop suite
uv run ruff check src db main.py

cd frontend && npm install
npm run dev                         # Vite on :5173, proxied to the API on :4568
npm run build                       # emits static/web, served by the backend
```

Schema changes: edit `db/models.py`, then `uv run python main.py --migrate-only generate -m "describe change"`. Migrations run automatically at startup.

```
main.py              application entry point and app assembly
config/              config.yaml with environment expansion
db/                  models · crud (data layer) · seed · migrate · alembic/
src/oauth/           authorization server: signing keys, grants, consent policy
src/identity/        console sign-in: passwords, sessions, GitHub / Google providers
src/api/             routers: oauth, session, services, discovery, marketplace, stats, audit
src/adapters/        the only layer allowed to import db.crud
src/discovery/       scanner, health monitor, WebSocket fan-out
src/orchestrator/    Docker-backed managed and bring-your-own MCP servers
frontend/            React console (Vite + Tailwind)
examples/            FastMCP server example
tests/               pytest suite
```

Architecture rule enforced in CI: `routes → adapters → db.crud`. Only `src/adapters/*` may import `db.crud`, and routes never call `db.commit()` directly (`tests/test_architecture_layering.py`).

## 🤝 Contributing

Issues and pull requests are welcome. Keep changes focused, add or update tests for behaviour you touch, and run `uv run pytest` plus `npm run build` before opening a PR.

## 📄 License

[MIT](LICENSE)
