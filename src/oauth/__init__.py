"""MCP Center 作為 OAuth 2.1 Authorization Server。

- signing_keys   RS256 金鑰(私鑰 AES 加密入庫)+ JWKS
- jwt_utils      RS256 簽 / 驗
- service        client、授權碼 + PKCE、token 簽發 / 輪替 / 撤銷 / 內省、resource → aud 綁定
- consent_policy 什麼情況可以略過同意頁
- errors         RFC 6749 錯誤

MCP server(FastMCP)只需:
    JWTVerifier(jwks_uri="<issuer>/.well-known/jwks.json", issuer="<issuer>", audience="<service audience>")
"""
from src.oauth.errors import OAuthError

__all__ = ["OAuthError"]
