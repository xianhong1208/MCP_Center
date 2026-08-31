"""Adapter 層 domain 例外

Adapter(中間層)只拋這些**不依賴 HTTP** 的 domain 例外;由 route(HTTP 邊界)
負責轉譯成 HTTPException。每個例外帶 status_code / code / fallback 三個屬性,
讓 route 用**單一** except 通用轉譯,對應原本 inline HTTPException 的回應格式:

    from fastapi import HTTPException
    from src.adapters.exceptions import AdapterError
    ...
    try:
        ...
    except AdapterError as e:
        raise HTTPException(status_code=e.status_code,
                            detail={"error": e.code, "fallback": e.fallback})

如此 adapter 保持純粹(不 import fastapi),route 仍完整保留原本的回應契約
(狀態碼 + {"error", "fallback"})。
"""

from typing import Optional


class AdapterError(Exception):
    """Adapter 層 domain 例外基底(HTTP-agnostic)。

    子類以類別屬性設定預設 status_code;各呼叫點以 code / fallback 指定
    對應原本的 error code 與訊息,確保 route 轉譯後回應逐字不變。
    """

    status_code: int = 400
    code: str = "adapter.error"
    fallback: str = "Operation failed"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        fallback: Optional[str] = None,
        params: Optional[dict] = None,
    ):
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        if fallback is not None:
            self.fallback = fallback
        # params 對應原本 HTTPException detail 的 "params"(僅部分 error 有);
        # route 翻譯時只在非空時帶入,以維持原回應格式。
        self.params = params or {}
        super().__init__(message or self.fallback)

    def to_detail(self) -> dict:
        """組成與原本 inline HTTPException 相同的 detail dict。"""
        detail = {"error": self.code, "fallback": self.fallback}
        if self.params:
            detail["params"] = self.params
        return detail


class NotFoundError(AdapterError):
    """資源不存在。"""
    status_code = 404
    code = "not_found"
    fallback = "Resource not found"


class PermissionDeniedError(AdapterError):
    """權限不足 / 非擁有者。"""
    status_code = 403
    code = "permission.denied"
    fallback = "Permission denied"


class ConflictError(AdapterError):
    """狀態衝突(如重複、已存在)。"""
    status_code = 409
    code = "conflict"
    fallback = "Conflict"


class ValidationFailedError(AdapterError):
    """輸入驗證失敗。"""
    status_code = 400
    code = "validation_failed"
    fallback = "Validation failed"
