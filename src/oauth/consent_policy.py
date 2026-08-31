"""同意頁政策:什麼情況可以不用再問使用者一次。

OAuth 的同意頁是「人」對「client 可以代表我做什麼」的閘門。每次都問最安全,但
Claude / Cursor 每次重連都跳一次同意頁很煩;完全不問又等於任何 DCR 註冊的 client
都能靜默拿到 token。這裡集中定義取捨。
"""

from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from db.models import AdminUser, OAuthClient
from src.adapters import OAuthConsentAdapter


def should_skip_consent(
    db: Session,
    user: AdminUser,
    client: OAuthClient,
    audience: Optional[str],
    requested_scopes: Iterable[str],
) -> bool:
    """回傳 True 代表可直接核發授權碼、不顯示同意頁。

    預設規則:
      1. 管理台手動建立(created_via=manual)的 client 視為使用者自己信任的 → 略過。
      2. 其他 client:使用者之前對「同 client + 同 audience」按過「記住」,且這次要的
         scope 沒有超出當時授予的範圍 → 略過;否則顯示同意頁。
    """
    requested = set(requested_scopes)
    if client.created_via == "manual":
        return True
    consent = OAuthConsentAdapter.get(db, user.id, client.client_id, audience)
    if consent is None:
        return False
    granted = set((consent.scope or "").split())
    return requested <= granted
