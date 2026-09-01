"""Security Headers Middleware

對所有 HTTP 回應附加安全相關標頭,防禦 Clickjacking、MIME sniffing 等。
防 Clickjacking / MIME sniffing(對應 SAST 常見的 Legacy Browser Clickjacking 項目)。

說明:
  - X-Frame-Options: DENY 與 CSP frame-ancestors 'none' 雙重防護,
    禁止本站頁面被任何網站以 <iframe>/<frame> 內嵌 → 阻斷 Clickjacking。
    (X-Frame-Options 相容舊瀏覽器;CSP frame-ancestors 為現代標準)
  - X-Content-Type-Options: nosniff,阻止瀏覽器對回應做 MIME type 猜測。
  - Referrer-Policy: 限制跨站 referrer 外洩。
  - 未加 HSTS:避免內網以 HTTP 部署時被瀏覽器強制升級 HTTPS 而中斷;
    若部署於 HTTPS 可由反向代理統一加上。
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """為每個回應加上安全標頭(使用 setdefault,不覆蓋既有標頭)。"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response
