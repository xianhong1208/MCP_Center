"""健康檢查 / 抓 tools 時的認證解析。

實際的定時健康檢查在 src/scheduler/cleanup_scheduler.py(_health_check_task);
單次檢查在 src/api/routes.py(check_service_health)。這裡只放兩者共用的邏輯。
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from db.models import Service
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
