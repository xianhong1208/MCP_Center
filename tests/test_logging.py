"""日誌模組測試

測試涵蓋：
1. 日誌中間件
2. 請求日誌
"""



class TestLoggingMiddleware:
    """日誌中間件測試"""

    def test_request_logging(self, client):
        """測試請求日誌記錄"""
        # 健康檢查請求應該被記錄
        response = client.get("/health")
        assert response.status_code == 200


class TestMiddlewareConfig:
    """中間件配置測試"""

    def test_middleware_class_exists(self):
        """測試中間件類存在"""
        from src.logging.middleware import RequestLoggingMiddleware

        assert RequestLoggingMiddleware is not None


class TestRequestIdInjection:
    """REQ-LOGGING-03: request-id 注入

    generate_request_id() 產生 id,並可透過 request-context 傳遞
    (set 之後由 context 取回相同的 request_id)。
    """

    def teardown_method(self):
        from src.logging.logger import clear_request_context

        clear_request_context()

    def test_generate_request_id_produces_id(self):
        """generate_request_id() 產生非空字串 id,且每次不同"""
        from src.logging.logger import generate_request_id

        rid1 = generate_request_id()
        rid2 = generate_request_id()

        assert isinstance(rid1, str)
        assert len(rid1) > 0
        assert rid1 != rid2  # UUID 來源,碰撞機率可忽略

    def test_request_id_carried_by_context(self):
        """set_request_context 設定 request_id 後,context 能取回同一值"""
        from src.logging.logger import (
            generate_request_id,
            set_request_context,
            get_request_context,
        )

        rid = generate_request_id()
        set_request_context(request_id=rid)

        ctx = get_request_context()
        assert ctx["request_id"] == rid


class TestRequestContextTracking:
    """REQ-LOGGING-04: 透過 contextvars 追蹤 request-context

    set/get/clear request context 正常運作,且 request_context() context
    manager 進出時能正確設定與還原。
    """

    def teardown_method(self):
        from src.logging.logger import clear_request_context

        clear_request_context()

    def test_set_and_get_context(self):
        """set_request_context 後可用 get_request_context 取回,並可累加"""
        from src.logging.logger import (
            set_request_context,
            get_request_context,
        )

        set_request_context(request_id="abc123", method="GET")
        set_request_context(path="/health")  # 應累加而非覆蓋

        ctx = get_request_context()
        assert ctx["request_id"] == "abc123"
        assert ctx["method"] == "GET"
        assert ctx["path"] == "/health"

    def test_get_context_returns_copy(self):
        """get_request_context 回傳副本,外部修改不影響內部狀態"""
        from src.logging.logger import (
            set_request_context,
            get_request_context,
        )

        set_request_context(request_id="orig")
        ctx = get_request_context()
        ctx["request_id"] = "mutated"

        assert get_request_context()["request_id"] == "orig"

    def test_clear_context(self):
        """clear_request_context 清空 context"""
        from src.logging.logger import (
            set_request_context,
            get_request_context,
            clear_request_context,
        )

        set_request_context(request_id="xyz")
        clear_request_context()

        assert get_request_context() == {}

    def test_request_context_manager_sets_and_restores(self):
        """request_context() context manager 進入時設定,離開時還原"""
        from src.logging.logger import (
            request_context,
            get_request_context,
        )

        assert get_request_context() == {}

        with request_context(request_id="ctx-1", user="admin"):
            ctx = get_request_context()
            assert ctx["request_id"] == "ctx-1"
            assert ctx["user"] == "admin"

        # 離開後應還原成空
        assert get_request_context() == {}


class TestSetupLogging:
    """REQ-LOGGING-05: setup_logging() 設定 loguru sinks 不報錯"""

    def test_setup_logging_runs_and_logger_usable(self, tmp_path):
        """呼叫 setup_logging() 不報錯,且回傳的 logger 可正常使用"""
        from src.logging.logger import setup_logging, get_logger

        # 使用暫存目錄避免污染 repo 的 logs/
        setup_logging(level="INFO", format_type="colorized", log_dir=str(tmp_path))

        log = get_logger("test-module")
        # 實際寫一筆 log — 若 sink 設定有誤會在此拋錯
        log.info("setup_logging colorized smoke test")

        # 應產生 app_*.log 檔案
        assert any(tmp_path.glob("app_*.log"))

    def test_setup_logging_json_sink(self, tmp_path):
        """json 格式 — 走 json_sink 路徑,設定與寫入皆不報錯"""
        from src.logging.logger import setup_logging, get_logger

        setup_logging(level="DEBUG", format_type="json", log_dir=str(tmp_path))

        log = get_logger("db")
        log.info("setup_logging json smoke test")

        assert any(tmp_path.glob("app_*.log"))

    def test_json_sink_serializes_record(self, capsys):
        """json_sink 直接餵一筆 loguru message,輸出為合法 JSON"""
        import json
        from src.logging.logger import json_sink, logger, clear_request_context

        clear_request_context()
        # 用臨時 sink 攔截 message 物件再交給 json_sink
        captured = {}

        def _intercept(message):
            captured["msg"] = message

        sink_id = logger.add(_intercept, level="INFO")
        try:
            logger.bind(module="unit").info("json sink direct test")
        finally:
            logger.remove(sink_id)

        assert "msg" in captured
        json_sink(captured["msg"])

        out = capsys.readouterr().err
        payload = json.loads(out.strip().splitlines()[-1])
        assert payload["message"] == "json sink direct test"
        assert payload["level"] == "INFO"


class TestGetLogger:
    """REQ-LOGGING-06: get_logger() 回傳綁定後的 logger"""

    def test_get_logger_returns_bound_logger(self):
        """帶 name 時回傳綁定 module 的 logger,可正常呼叫 log 方法"""
        from src.logging.logger import get_logger

        log = get_logger("my-module")

        assert log is not None
        # loguru bound logger 具備標準 log 方法
        assert callable(getattr(log, "info", None))
        assert callable(getattr(log, "error", None))
        # bind 綁定的 module 存於 logger 的 options extra(最後一個元素)
        assert log._options[-1].get("module") == "my-module"

    def test_get_logger_without_name_returns_base_logger(self):
        """未帶 name 時回傳基礎 logger 物件"""
        from src.logging.logger import get_logger, logger

        log = get_logger()
        assert log is logger
