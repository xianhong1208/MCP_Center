"""管理台身分驗證(誰可以登入 MCP Center 管理台)。

與 `src/oauth`(MCP Center 作為 OAuth 2.1 Authorization Server,發 token 給 MCP client)
是兩件事:這裡回答「人是誰」,那裡回答「client 能對哪個 MCP server 做什麼」。

- passwords    bcrypt
- session      httpOnly cookie 內的 HS256 JWT、FastAPI 依賴(get_current_user)
- providers    可插拔的第三方登入(GitHub / Google)
- service      登入 / 首次設定 / 改密 / 第三方帳號對應
"""
from src.identity.session import (
    AuthenticationRequired,
    get_current_user,
    get_optional_current_user,
    session_manager,
)

__all__ = [
    "AuthenticationRequired",
    "get_current_user",
    "get_optional_current_user",
    "session_manager",
]
