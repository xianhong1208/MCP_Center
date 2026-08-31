"""Rate Limiter Middleware

基於 IP 的請求頻率限制，防止 API 濫用。
使用滑動窗口算法實現。
"""

import asyncio
import time
import ipaddress
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


def is_ip_in_whitelist(client_ip: str, whitelist: List[str]) -> bool:
    """檢查 IP 是否在白名單中（支援 CIDR 格式）

    Args:
        client_ip: 客戶端 IP 地址
        whitelist: 白名單列表，可包含單一 IP 或 CIDR 格式

    Returns:
        True 如果 IP 在白名單中
    """
    # 直接匹配
    if client_ip in whitelist:
        return True

    try:
        ip = ipaddress.ip_address(client_ip)
        for entry in whitelist:
            # 跳過非 IP 格式（如 "localhost"）
            if entry in ("localhost", "::1"):
                continue
            try:
                # 嘗試作為網段解析
                if "/" in entry:
                    network = ipaddress.ip_network(entry, strict=False)
                    if ip in network:
                        return True
                else:
                    # 作為單一 IP 解析
                    if ip == ipaddress.ip_address(entry):
                        return True
            except ValueError:
                continue
    except ValueError:
        pass

    return False


@dataclass
class RateLimitConfig:
    """Rate Limit 配置"""
    requests_per_minute: int = 60  # 每分鐘最大請求數
    requests_per_hour: int = 1000  # 每小時最大請求數
    burst_size: int = 10  # 突發請求容許數
    enabled: bool = True
    # 白名單 IP（不受限制）
    whitelist: list = field(default_factory=lambda: ["127.0.0.1", "localhost"])
    # 特定路徑的自定義限制
    path_limits: Dict[str, int] = field(default_factory=dict)
    # 信任的反向代理 IP（只有來自這些 IP 的請求才會解析 X-Forwarded-For）
    trusted_proxies: list = field(default_factory=lambda: ["127.0.0.1", "::1"])


class SlidingWindowCounter:
    """滑動窗口計數器"""

    def __init__(self, window_size: int = 60):
        self.window_size = window_size  # 窗口大小（秒）
        self.requests: Dict[str, list] = defaultdict(list)

    def add_request(self, key: str) -> int:
        """添加請求並返回窗口內的請求數"""
        now = time.time()
        window_start = now - self.window_size

        # 清理過期的請求記錄
        self.requests[key] = [t for t in self.requests[key] if t > window_start]

        # 添加當前請求
        self.requests[key].append(now)

        return len(self.requests[key])

    def get_count(self, key: str) -> int:
        """獲取當前窗口內的請求數"""
        now = time.time()
        window_start = now - self.window_size
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        return len(self.requests[key])

    def cleanup(self):
        """清理所有過期記錄"""
        now = time.time()
        for key in list(self.requests.keys()):
            window_start = now - self.window_size
            self.requests[key] = [t for t in self.requests[key] if t > window_start]
            if not self.requests[key]:
                del self.requests[key]


class RateLimiter:
    """Rate Limiter 實例"""

    _instance: Optional['RateLimiter'] = None

    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        self.minute_counter = SlidingWindowCounter(window_size=60)
        self.hour_counter = SlidingWindowCounter(window_size=3600)
        self.blocked_until: Dict[str, float] = {}  # 被封鎖的 IP
        self._lock = asyncio.Lock()  # 保護並發存取

    @classmethod
    def get_instance(cls, config: RateLimitConfig = None) -> 'RateLimiter':
        """獲取單例實例"""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置實例（用於測試）"""
        cls._instance = None

    async def is_allowed(self, client_ip: str, path: str = None) -> tuple[bool, str, int]:
        """
        檢查請求是否允許

        Returns:
            (allowed, reason, retry_after)
        """
        if not self.config.enabled:
            return True, "", 0

        # 白名單檢查（支援 CIDR）— 不需要鎖
        if is_ip_in_whitelist(client_ip, self.config.whitelist):
            return True, "", 0

        async with self._lock:
            # 檢查是否被暫時封鎖
            if client_ip in self.blocked_until:
                if time.time() < self.blocked_until[client_ip]:
                    retry_after = int(self.blocked_until[client_ip] - time.time())
                    return False, "too_many_requests", retry_after
                else:
                    del self.blocked_until[client_ip]

            # 獲取限制值
            minute_limit = self.config.requests_per_minute
            hour_limit = self.config.requests_per_hour

            # 特定路徑可能有自定義限制
            if path and path in self.config.path_limits:
                minute_limit = self.config.path_limits[path]

            # 檢查每分鐘限制
            minute_count = self.minute_counter.add_request(f"{client_ip}:minute")
            if minute_count > minute_limit:
                # 超過限制，暫時封鎖 60 秒
                self.blocked_until[client_ip] = time.time() + 60
                return False, "rate_limit_minute", 60

            # 檢查每小時限制
            hour_count = self.hour_counter.add_request(f"{client_ip}:hour")
            if hour_count > hour_limit:
                # 超過小時限制，封鎖到下一個小時
                self.blocked_until[client_ip] = time.time() + 300  # 5 分鐘
                return False, "rate_limit_hour", 300

            return True, "", 0

    def get_stats(self, client_ip: str) -> dict:
        """獲取客戶端的請求統計"""
        return {
            "minute_count": self.minute_counter.get_count(f"{client_ip}:minute"),
            "minute_limit": self.config.requests_per_minute,
            "hour_count": self.hour_counter.get_count(f"{client_ip}:hour"),
            "hour_limit": self.config.requests_per_hour,
            "is_blocked": client_ip in self.blocked_until,
        }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI Rate Limit 中間件"""

    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self.limiter = RateLimiter.get_instance(config)
        # 不限制的路徑
        self.excluded_paths = ["/docs", "/redoc", "/openapi.json", "/health"]

    async def dispatch(self, request: Request, call_next):
        # 排除特定路徑
        if any(request.url.path.startswith(p) for p in self.excluded_paths):
            return await call_next(request)

        # 獲取客戶端 IP
        client_ip = self._get_client_ip(request)

        # 檢查是否允許
        allowed, reason, retry_after = await self.limiter.is_allowed(
            client_ip,
            request.url.path
        )

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Too many requests. Please retry after {retry_after} seconds.",
                    "reason": reason,
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)}
            )

        # 添加 rate limit headers
        response = await call_next(request)
        stats = self.limiter.get_stats(client_ip)
        response.headers["X-RateLimit-Limit"] = str(stats["minute_limit"])
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, stats["minute_limit"] - stats["minute_count"])
        )

        return response

    def _get_client_ip(self, request: Request) -> str:
        """獲取客戶端真實 IP

        安全性考量：只有當直接連接的 IP 來自信任的代理時，
        才會解析 X-Forwarded-For 或 X-Real-IP header。
        這可以防止攻擊者透過偽造這些 header 來繞過 rate limiting。
        """
        # 獲取直接連接的 IP
        direct_ip = request.client.host if request.client else "unknown"

        # 只有來自信任代理的請求才解析 forwarded headers
        if is_ip_in_whitelist(direct_ip, self.config.trusted_proxies):
            # 優先使用 X-Forwarded-For
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                # 取第一個 IP（原始客戶端 IP）
                return forwarded.split(",")[0].strip()

            # 其次使用 X-Real-IP
            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                return real_ip

        # 非信任代理或無 forwarded header，使用直接連接的 IP
        return direct_ip
