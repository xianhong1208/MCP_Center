"""速率限制測試

測試涵蓋：
1. 滑動視窗速率限制
2. IP 白名單
3. 路徑特定限制
"""

import pytest
import time
from unittest.mock import MagicMock, patch


class TestSlidingWindowCounter:
    """滑動視窗計數器測試"""

    def test_counter_initialization(self):
        """測試計數器初始化"""
        from src.middleware.rate_limiter import SlidingWindowCounter

        counter = SlidingWindowCounter(window_size=60)
        assert counter.window_size == 60

    def test_add_request(self):
        """測試添加請求"""
        from src.middleware.rate_limiter import SlidingWindowCounter

        counter = SlidingWindowCounter(window_size=60)

        count = counter.add_request("test_ip")
        assert count == 1

        count = counter.add_request("test_ip")
        assert count == 2

    def test_different_keys_independent(self):
        """測試不同 key 獨立計數"""
        from src.middleware.rate_limiter import SlidingWindowCounter

        counter = SlidingWindowCounter(window_size=60)

        counter.add_request("ip1")
        counter.add_request("ip1")
        counter.add_request("ip2")

        assert counter.get_count("ip1") == 2
        assert counter.get_count("ip2") == 1

    def test_cleanup(self):
        """測試清理功能"""
        from src.middleware.rate_limiter import SlidingWindowCounter

        counter = SlidingWindowCounter(window_size=60)
        counter.add_request("test_ip")

        # cleanup 不應該報錯
        counter.cleanup()

    def test_hour_window_counter_accumulates(self):
        """測試每小時窗口計數器累積計數 (REQ-RATE-LIMITER-13)

        以 3600 秒窗口模擬每小時計數器，
        驗證連續請求會累積且超過小型限制值。
        """
        from src.middleware.rate_limiter import SlidingWindowCounter

        counter = SlidingWindowCounter(window_size=3600)
        hour_limit = 3

        # 前 hour_limit 次不應超過限制
        for expected in range(1, hour_limit + 1):
            assert counter.add_request("hour_ip") == expected

        # 再一次請求即超過每小時限制
        assert counter.add_request("hour_ip") == hour_limit + 1
        assert counter.get_count("hour_ip") > hour_limit


class TestRateLimitConfig:
    """速率限制配置測試"""

    def test_config_defaults(self):
        """測試配置預設值"""
        from src.middleware.rate_limiter import RateLimitConfig

        config = RateLimitConfig()

        assert config.requests_per_minute == 60
        assert config.requests_per_hour == 1000
        assert config.enabled is True
        assert "127.0.0.1" in config.whitelist

    def test_config_custom_values(self):
        """測試自訂配置值"""
        from src.middleware.rate_limiter import RateLimitConfig

        config = RateLimitConfig(
            requests_per_minute=30,
            requests_per_hour=500,
            whitelist=["192.168.1.1"]
        )

        assert config.requests_per_minute == 30
        assert config.requests_per_hour == 500
        assert "192.168.1.1" in config.whitelist

    def test_config_path_limits(self):
        """測試路徑特定限制"""
        from src.middleware.rate_limiter import RateLimitConfig

        config = RateLimitConfig(
            path_limits={
                "/admin/login": 10,
                "/auth/token": 30
            }
        )

        assert config.path_limits["/admin/login"] == 10
        assert config.path_limits["/auth/token"] == 30


class TestIPWhitelist:
    """IP 白名單測試"""

    def test_ip_in_whitelist_direct_match(self):
        """測試直接 IP 匹配"""
        from src.middleware.rate_limiter import is_ip_in_whitelist

        whitelist = ["127.0.0.1", "192.168.1.1"]

        assert is_ip_in_whitelist("127.0.0.1", whitelist) is True
        assert is_ip_in_whitelist("192.168.1.1", whitelist) is True
        assert is_ip_in_whitelist("10.0.0.1", whitelist) is False

    def test_ip_in_whitelist_cidr(self):
        """測試 CIDR 格式匹配"""
        from src.middleware.rate_limiter import is_ip_in_whitelist

        whitelist = ["192.168.1.0/24"]

        assert is_ip_in_whitelist("192.168.1.1", whitelist) is True
        assert is_ip_in_whitelist("192.168.1.100", whitelist) is True
        assert is_ip_in_whitelist("192.168.2.1", whitelist) is False

    def test_ip_in_whitelist_localhost(self):
        """測試 localhost 處理"""
        from src.middleware.rate_limiter import is_ip_in_whitelist

        whitelist = ["localhost", "127.0.0.1"]

        assert is_ip_in_whitelist("localhost", whitelist) is True
        assert is_ip_in_whitelist("127.0.0.1", whitelist) is True


class TestRateLimiter:
    """速率限制器測試"""

    def test_limiter_initialization(self):
        """測試限制器初始化"""
        from src.middleware.rate_limiter import RateLimiter, RateLimitConfig

        config = RateLimitConfig(requests_per_minute=60)
        limiter = RateLimiter(config)

        assert limiter.config.requests_per_minute == 60

    @pytest.mark.asyncio
    async def test_limiter_allows_whitelisted_ip(self):
        """測試白名單 IP 允許通過"""
        from src.middleware.rate_limiter import RateLimiter, RateLimitConfig

        config = RateLimitConfig(
            requests_per_minute=1,
            whitelist=["127.0.0.1"]
        )
        limiter = RateLimiter(config)

        # 白名單 IP 應該總是允許
        allowed, reason, retry_after = await limiter.is_allowed("127.0.0.1")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_limiter_blocks_after_limit(self):
        """測試超過限制後封鎖"""
        from src.middleware.rate_limiter import RateLimiter, RateLimitConfig

        config = RateLimitConfig(
            requests_per_minute=2,
            whitelist=[]  # 清空白名單
        )
        limiter = RateLimiter(config)

        # 前兩次應該通過
        allowed1, _, _ = await limiter.is_allowed("10.0.0.1")
        allowed2, _, _ = await limiter.is_allowed("10.0.0.1")
        assert allowed1 is True
        assert allowed2 is True

        # 第三次應該被封鎖
        allowed3, reason, _ = await limiter.is_allowed("10.0.0.1")
        assert allowed3 is False
        assert "rate_limit" in reason

    @pytest.mark.asyncio
    async def test_limiter_blocks_after_hour_limit(self):
        """測試超過每小時限制後封鎖 (REQ-RATE-LIMITER-13)

        每分鐘限制設得很寬鬆、每小時限制設得很小，
        讓請求先觸發小時限制而非分鐘限制，
        驗證超過每小時限制時會回傳 rate_limit_hour。
        """
        from src.middleware.rate_limiter import RateLimiter, RateLimitConfig

        config = RateLimitConfig(
            requests_per_minute=100,  # 分鐘限制放寬，避免先被分鐘限制擋下
            requests_per_hour=3,       # 每小時只允許 3 次
            whitelist=[]               # 清空白名單
        )
        limiter = RateLimiter(config)

        # 前 3 次應該通過（未超過每小時限制）
        for _ in range(3):
            allowed, _, _ = await limiter.is_allowed("10.0.0.9")
            assert allowed is True

        # 第 4 次超過每小時限制，應被封鎖並回報 rate_limit_hour
        allowed, reason, retry_after = await limiter.is_allowed("10.0.0.9")
        assert allowed is False
        assert reason == "rate_limit_hour"
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_limiter_disabled(self):
        """測試禁用限制器"""
        from src.middleware.rate_limiter import RateLimiter, RateLimitConfig

        config = RateLimitConfig(
            enabled=False,
            requests_per_minute=1
        )
        limiter = RateLimiter(config)

        # 即使超過限制也應該允許
        for _ in range(10):
            allowed, _, _ = await limiter.is_allowed("10.0.0.1")
            assert allowed is True

    @pytest.mark.asyncio
    async def test_limiter_path_specific_limit(self):
        """測試路徑特定限制"""
        from src.middleware.rate_limiter import RateLimiter, RateLimitConfig

        config = RateLimitConfig(
            requests_per_minute=100,
            path_limits={"/admin/login": 2},
            whitelist=[]
        )
        limiter = RateLimiter(config)

        # 對 /admin/login 路徑，限制為 2
        await limiter.is_allowed("10.0.0.2", "/admin/login")
        await limiter.is_allowed("10.0.0.2", "/admin/login")
        allowed, _, _ = await limiter.is_allowed("10.0.0.2", "/admin/login")
        assert allowed is False


class TestRateLimiterSingleton:
    """速率限制器單例測試"""

    def test_get_instance(self):
        """測試取得單例實例"""
        from src.middleware.rate_limiter import RateLimiter, RateLimitConfig

        # 先重置
        RateLimiter.reset_instance()

        config = RateLimitConfig(requests_per_minute=100)
        instance1 = RateLimiter.get_instance(config)
        instance2 = RateLimiter.get_instance()

        assert instance1 is instance2

        # 清理
        RateLimiter.reset_instance()


class TestRateLimitIntegration:
    """速率限制整合測試"""

    def test_api_rate_limit(self, client, db_session):
        """測試 API 速率限制"""
        # 健康檢查端點應該可以存取
        response = client.get("/health")
        assert response.status_code == 200
