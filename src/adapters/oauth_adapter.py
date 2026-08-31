"""OAuth 領域 Adapter(signing keys / clients / codes / tokens / consents / scopes)+ 事件統計 + 審計清理。"""

from db.crud import (
    AuditLogCRUD,
    OAuthAuthRequestCRUD,
    OAuthClientCRUD,
    OAuthCodeCRUD,
    OAuthConsentCRUD,
    OAuthScopeCRUD,
    OAuthSigningKeyCRUD,
    OAuthTokenCRUD,
    TokenUsageCRUD,
)
from src.adapters.exceptions import NotFoundError


class OAuthKeyAdapter(OAuthSigningKeyCRUD):
    """簽章金鑰。"""


class OAuthClientAdapter(OAuthClientCRUD):

    @classmethod
    def get_existing(cls, db, client_id):
        client = cls.get(db, client_id)
        if not client:
            raise NotFoundError(code="oauth.client_not_found", fallback="OAuth client not found")
        return client


class OAuthAuthRequestAdapter(OAuthAuthRequestCRUD):
    """/authorize 進來、等待同意的請求。"""


class OAuthCodeAdapter(OAuthCodeCRUD):
    """授權碼。"""


class OAuthScopeAdapter(OAuthScopeCRUD):
    """scope 註冊表。"""


class OAuthTokenAdapter(OAuthTokenCRUD):

    @classmethod
    def get_existing(cls, db, jti):
        token = cls.get(db, jti)
        if not token:
            raise NotFoundError(code="oauth.token_not_found", fallback="Token not found")
        return token


class OAuthConsentAdapter(OAuthConsentCRUD):
    """使用者已授予的同意。"""


class TokenUsageAdapter(TokenUsageCRUD):
    """token 事件 / 統計。"""


class AuditLogAdapter(AuditLogCRUD):
    """審計日誌清理。"""
