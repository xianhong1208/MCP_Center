"""MCP 服務健康監控

功能：
- 定時健康檢查
- 失敗計數與狀態轉換 (3 次失敗 → OFFLINE)
- 狀態變更回調
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, Awaitable

from sqlalchemy.orm import Session

from src.adapters import ServiceAdapter
from db.models import Service
from src.discovery.scanner import MCPScanner, get_scanner
from src.utils.crypto import decrypt_token

logger = logging.getLogger(__name__)


def resolve_service_auth_token(db: Session, service: Service) -> Optional[str]:
    """健康檢查 / 抓 tools 時要帶的 Bearer。

    ① 服務受 MCP Center 自己的 OAuth 保護(requires_auth 且沒有靜態 token)→ 當場自簽
       aud=該服務的短命 token,免存、免過期。
    ② 服務有自己的靜態 Bearer(auth_token_encrypted)→ 解密使用。
    ③ 不需認證 → None。
    """
    if service.auth_token_encrypted:
        try:
            return decrypt_token(service.auth_token_encrypted)
        except Exception as e:
            logger.warning(f"Failed to decrypt auth token for {service.name}: {e}")
            return None
    if service.requires_auth:
        try:
            from src.oauth import service as oauth_service
            return oauth_service.mint_scanner_token(db, service)
        except Exception as e:
            logger.warning(f"Failed to mint scanner token for {service.name}: {e}")
    return None


class HealthStatus(str, Enum):
    """服務健康狀態"""
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"
    ERROR = "error"


@dataclass
class HealthCheckResult:
    """健康檢查結果"""
    service_id: str
    service_name: str
    status: HealthStatus
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    previous_status: Optional[HealthStatus] = None
    status_changed: bool = False


# 狀態變更回調類型
OnStatusChangeCallback = Callable[[HealthCheckResult], Awaitable[None]]


class HealthMonitor:
    """MCP 服務健康監控器

    定期檢查註冊的 MCP 服務健康狀態，並在狀態變更時觸發回調。
    """

    # 連續失敗多少次後標記為 OFFLINE
    OFFLINE_THRESHOLD = 3

    def __init__(
        self,
        db_session_factory: Callable[[], Session],
        check_interval: int = 30,
        offline_threshold: int = 3,
        scanner: Optional[MCPScanner] = None
    ):
        """初始化健康監控器

        Args:
            db_session_factory: 資料庫 Session 工廠函數
            check_interval: 檢查間隔 (秒)
            offline_threshold: 判定為離線的失敗次數閾值
            scanner: MCP 掃描器 (可選，預設使用全域 instance)
        """
        self.db_session_factory = db_session_factory
        self.check_interval = check_interval
        self.offline_threshold = offline_threshold
        self.scanner = scanner or get_scanner()

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callbacks: list[OnStatusChangeCallback] = []

    def on_status_change(self, callback: OnStatusChangeCallback) -> None:
        """註冊狀態變更回調

        Args:
            callback: 狀態變更時呼叫的 async 函數
        """
        self._callbacks.append(callback)

    async def start_monitoring(self) -> None:
        """開始監控"""
        if self._running:
            logger.warning("Health monitor is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info(f"Health monitor started (interval: {self.check_interval}s)")

    async def stop_monitoring(self) -> None:
        """停止監控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Health monitor stopped")

    async def _monitoring_loop(self) -> None:
        """監控迴圈"""
        while self._running:
            try:
                await self._check_all_services()
            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(self.check_interval)

    async def _check_all_services(self) -> None:
        """檢查所有服務"""
        db = self.db_session_factory()
        try:
            services = ServiceAdapter.get_services_for_health_check(db)
            logger.debug(f"Checking health for {len(services)} services")

            for service in services:
                try:
                    result = await self.check_service_health(service, db)
                    if result.status_changed:
                        await self._notify_status_change(result)
                except Exception as e:
                    logger.error(f"Error checking service {service.name}: {e}")

        finally:
            db.close()

    async def check_service_health(
        self,
        service: Service,
        db: Optional[Session] = None
    ) -> HealthCheckResult:
        """檢查單一服務健康狀態

        Args:
            service: Service 物件
            db: 資料庫 Session (可選，若未提供會建立新的)

        Returns:
            HealthCheckResult 健康檢查結果
        """
        own_db = db is None
        if own_db:
            db = self.db_session_factory()

        try:
            previous_status = HealthStatus(service.health_status) if service.health_status else HealthStatus.UNKNOWN

            auth_token = resolve_service_auth_token(db, service)

            # 執行 MCP 驗證
            verify_result = await self.scanner.verify_mcp_service(
                host=service.host,
                port=service.port,
                path=service.mcp_path,
                protocol=service.protocol,
                auth_token=auth_token
            )

            # 判定狀態
            if verify_result.success:
                new_status = HealthStatus.ONLINE
                error_message = None
                reset_fail = True
                increment_fail = False
            else:
                error_message = verify_result.error
                reset_fail = False
                increment_fail = True

                # 根據失敗次數判定狀態
                fail_count = (service.health_fail_count or 0) + 1
                if fail_count >= self.offline_threshold:
                    new_status = HealthStatus.OFFLINE
                else:
                    new_status = HealthStatus.ERROR

            # 更新資料庫
            ServiceAdapter.update_health(
                db=db,
                service_id=str(service.id),
                status=new_status.value,
                response_time_ms=verify_result.response_time_ms,
                error_message=error_message,
                reset_fail_count=reset_fail,
                increment_fail_count=increment_fail
            )

            status_changed = new_status != previous_status

            return HealthCheckResult(
                service_id=str(service.id),
                service_name=service.name,
                status=new_status,
                response_time_ms=verify_result.response_time_ms,
                error_message=error_message,
                previous_status=previous_status,
                status_changed=status_changed
            )

        finally:
            if own_db:
                db.close()

    async def _notify_status_change(self, result: HealthCheckResult) -> None:
        """通知狀態變更"""
        logger.info(
            f"Service {result.service_name} status changed: "
            f"{result.previous_status} → {result.status}"
        )

        for callback in self._callbacks:
            try:
                await callback(result)
            except Exception as e:
                logger.error(f"Status change callback error: {e}")

    async def force_check(self, service_name: str) -> Optional[HealthCheckResult]:
        """強制檢查指定服務

        Args:
            service_name: 服務名稱

        Returns:
            HealthCheckResult 或 None (若服務不存在)
        """
        db = self.db_session_factory()
        try:
            service = ServiceAdapter.get_by_name(db, service_name)
            if not service:
                return None

            if not service.host or not service.port:
                return HealthCheckResult(
                    service_id=str(service.id),
                    service_name=service.name,
                    status=HealthStatus.UNKNOWN,
                    error_message="Service has no host or port configured"
                )

            return await self.check_service_health(service, db)

        finally:
            db.close()


# 全域 health monitor instance (延遲初始化)
_monitor_instance: Optional[HealthMonitor] = None


def get_health_monitor() -> Optional[HealthMonitor]:
    """取得 HealthMonitor singleton instance"""
    return _monitor_instance


def init_health_monitor(
    db_session_factory: Callable[[], Session],
    check_interval: int = 30
) -> HealthMonitor:
    """初始化 HealthMonitor singleton

    Args:
        db_session_factory: 資料庫 Session 工廠函數
        check_interval: 檢查間隔 (秒)

    Returns:
        HealthMonitor instance
    """
    global _monitor_instance
    _monitor_instance = HealthMonitor(
        db_session_factory=db_session_factory,
        check_interval=check_interval
    )
    return _monitor_instance
