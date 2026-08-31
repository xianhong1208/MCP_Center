"""受 MCP Center 保護的 FastMCP server 範例。

    uv run python examples/fastmcp_server.py

前置:MCP Center 跑在 http://localhost:4568,並在管理台 Services 登錄了
host=127.0.0.1 port=8000 path=/mcp 的服務(audience = http://127.0.0.1:8000/mcp)。

之後用任何支援 OAuth 的 MCP client 連 http://127.0.0.1:8000/mcp 即可,例如:
    claude mcp add --transport http demo http://127.0.0.1:8000/mcp
或用管理台簽的 Personal Access Token:
    claude mcp add --transport http demo http://127.0.0.1:8000/mcp --header "Authorization: Bearer <PAT>"
"""

import os

from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from pydantic import AnyHttpUrl

MCP_CENTER = os.environ.get("MCP_CENTER_URL", "http://localhost:4568").rstrip("/")
HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "8000"))
BASE_URL = f"http://{HOST}:{PORT}"
AUDIENCE = os.environ.get("MCP_AUDIENCE", f"{BASE_URL}/mcp")

auth = RemoteAuthProvider(
    token_verifier=JWTVerifier(
        jwks_uri=f"{MCP_CENTER}/.well-known/jwks.json",
        issuer=MCP_CENTER,
        audience=AUDIENCE,
        # required_scopes=["mcp:tools:invoke"],  # 想強制 scope 時打開
    ),
    authorization_servers=[AnyHttpUrl(MCP_CENTER)],
    base_url=BASE_URL,
)

mcp = FastMCP(name="demo", instructions="MCP Center demo server", auth=auth)


@mcp.tool
def hello(name: str) -> str:
    """打招呼。"""
    return f"Hello, {name}!"


@mcp.tool
def whoami() -> dict:
    """看看目前這張 token 是誰、給哪個 client、有哪些 scope。"""
    token = get_access_token()
    return {
        "subject": token.subject,
        "client_id": token.client_id,
        "scopes": token.scopes,
        "email": (token.claims or {}).get("email"),
    }


if __name__ == "__main__":
    print(f"MCP Center : {MCP_CENTER}")
    print(f"MCP URL    : {BASE_URL}/mcp   (audience={AUDIENCE})")
    mcp.run(transport="http", host=HOST, port=PORT)
