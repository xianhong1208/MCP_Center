"""例外處理測試

測試涵蓋：
1. 認證例外
2. 資料庫例外
3. 服務例外
4. 基礎例外
"""



class TestAuthExceptions:
    """認證例外測試"""

    def test_authentication_error(self):
        """測試認證錯誤例外"""
        from src.exceptions.auth import AuthenticationError

        exc = AuthenticationError("Authentication failed")
        assert exc.status_code == 401
        assert exc.code == "AUTHENTICATION_ERROR"

    def test_invalid_credentials_error(self):
        """測試無效憑證例外"""
        from src.exceptions.auth import InvalidCredentialsError

        exc = InvalidCredentialsError()
        assert exc.status_code == 401

    def test_token_expired_error(self):
        """測試 Token 過期例外"""
        from src.exceptions.auth import TokenExpiredError

        exc = TokenExpiredError(expired_at="2024-01-01T00:00:00")
        assert exc.status_code == 401
        assert exc.code == "TOKEN_EXPIRED"

    def test_token_not_found_error(self):
        """測試 Token 不存在例外"""
        from src.exceptions.auth import TokenNotFoundError

        exc = TokenNotFoundError(token_preview="abc123...")
        assert exc.status_code == 404
        assert exc.code == "TOKEN_NOT_FOUND"

    def test_invalid_token_error(self):
        """測試無效 Token 例外"""
        from src.exceptions.auth import InvalidTokenError

        exc = InvalidTokenError(reason="Malformed JWT")
        assert exc.status_code == 401
        assert exc.code == "INVALID_TOKEN"

    def test_token_revoked_error(self):
        """測試 Token 已撤銷例外"""
        from src.exceptions.auth import TokenRevokedError

        exc = TokenRevokedError()
        assert exc.status_code == 401
        assert exc.code == "TOKEN_REVOKED"

    def test_insufficient_scope_error(self):
        """測試權限不足例外"""
        from src.exceptions.auth import InsufficientScopeError

        exc = InsufficientScopeError(required_scopes=["admin"], token_scopes=["read"])
        assert exc.status_code == 403
        assert exc.code == "INSUFFICIENT_SCOPE"

    def test_service_mismatch_error(self):
        """測試服務不匹配例外"""
        from src.exceptions.auth import ServiceMismatchError

        exc = ServiceMismatchError()
        assert exc.status_code == 403


class TestDatabaseExceptions:
    """資料庫例外測試"""

    def test_database_error(self):
        """測試資料庫錯誤例外"""
        from src.exceptions.database import DatabaseError

        exc = DatabaseError("Connection failed")
        assert exc.status_code == 500

    def test_record_not_found_error(self):
        """測試記錄不存在例外"""
        from src.exceptions.database import RecordNotFoundError

        exc = RecordNotFoundError(model="user", identifier="123")
        assert exc.status_code == 404
        assert exc.code == "RECORD_NOT_FOUND"

    def test_duplicate_record_error(self):
        """測試重複記錄例外"""
        from src.exceptions.database import DuplicateRecordError

        exc = DuplicateRecordError(field="username", value="admin")
        assert exc.status_code == 409
        assert exc.code == "DUPLICATE_RECORD"


class TestServiceExceptions:
    """服務例外測試"""

    def test_service_error(self):
        """測試服務錯誤例外"""
        from src.exceptions.service import ServiceError

        exc = ServiceError()
        assert exc.status_code == 400
        assert exc.code == "SERVICE_ERROR"

    def test_service_not_found_error(self):
        """測試服務不存在例外"""
        from src.exceptions.service import ServiceNotFoundError

        exc = ServiceNotFoundError(service_name="my-service")
        assert exc.status_code == 404
        assert exc.code == "SERVICE_NOT_FOUND"

    def test_service_already_exists_error(self):
        """測試服務已存在例外"""
        from src.exceptions.service import ServiceAlreadyExistsError

        exc = ServiceAlreadyExistsError(service_name="my-service")
        assert exc.status_code == 409


class TestBaseExceptions:
    """基礎例外測試"""

    def test_token_server_error(self):
        """測試基礎錯誤例外"""
        from src.exceptions.base import MCPCenterError

        exc = MCPCenterError(message="Test error", code="TEST_ERROR")
        assert exc.message == "Test error"
        assert exc.code == "TEST_ERROR"
        assert exc.status_code == 500

    def test_token_server_http_exception(self):
        """測試 HTTP 例外"""
        from src.exceptions.base import MCPCenterHTTPException

        exc = MCPCenterHTTPException(
            message="Custom error",
            status_code=400,
            code="CUSTOM_ERROR"
        )
        assert exc.message == "Custom error"
        assert exc.status_code == 400
        assert exc.code == "CUSTOM_ERROR"

    def test_exception_to_dict(self):
        """測試例外轉換為字典"""
        from src.exceptions.base import MCPCenterError

        exc = MCPCenterError(
            message="Test error",
            code="TEST_CODE",
            details={"key": "value"}
        )

        result = exc.to_dict()
        assert result["error"] == "TEST_CODE"
        assert result["message"] == "Test error"
        assert result["details"]["key"] == "value"

    def test_exception_to_http_exception(self):
        """測試例外轉換為 HTTPException"""
        from src.exceptions.base import MCPCenterHTTPException
        from fastapi import HTTPException

        exc = MCPCenterHTTPException(
            message="HTTP error",
            status_code=404
        )

        http_exc = exc.to_http_exception()
        assert isinstance(http_exc, HTTPException)
        assert http_exc.status_code == 404


class TestExceptionHandlerMiddleware:
    """例外處理 middleware 測試 (REQ-EXCEPTIONS-10)"""

    def test_custom_exception_converted_to_json_error_response(self):
        """自訂例外經 handler 轉為正確的 JSON 錯誤回應與狀態碼"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.exceptions.base import MCPCenterError
        from src.exceptions.handlers import register_exception_handlers

        class TeapotError(MCPCenterError):
            code = "IM_A_TEAPOT"
            message = "short and stout"
            status_code = 418

        # 建立最小 app,註冊 handlers,並加一個會拋自訂例外的路由
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/boom")
        def boom():
            raise TeapotError(details={"pot": "tea"})

        client = TestClient(app)
        response = client.get("/boom")

        # 狀態碼取自例外
        assert response.status_code == 418

        # error body 形狀符合 to_dict() 契約
        body = response.json()
        assert body["error"] == "IM_A_TEAPOT"
        assert body["message"] == "short and stout"
        assert body["details"]["pot"] == "tea"


class TestExceptionInAPI:
    """API 中例外處理測試"""

    def test_invalid_session_returns_401(self, client):
        response = client.get("/api/session/me", headers={"Authorization": "Bearer invalid-token"})
        assert response.status_code == 401

    def test_missing_auth_returns_401(self, client):
        assert client.get("/api/services").status_code == 401

    def test_not_found_service_returns_404(self, owner_client):
        response = owner_client.get("/api/services/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "service.not_found"
