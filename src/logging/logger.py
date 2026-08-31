"""Structured Logger Configuration

Provides JSON-formatted logging for production and colorized output for development.
Includes request context tracking via context variables.
"""

import sys
import json
import uuid
from typing import Optional
from contextvars import ContextVar

from loguru import logger

# Context variable for request tracking
_request_context: ContextVar[dict] = ContextVar("request_context", default={})


class LogContext:
    """Context manager for adding context to log messages"""

    def __init__(self, **kwargs):
        self.context = kwargs
        self.token = None

    def __enter__(self):
        current = _request_context.get().copy()
        current.update(self.context)
        self.token = _request_context.set(current)
        return self

    def __exit__(self, *args):
        if self.token:
            _request_context.reset(self.token)


def request_context(**kwargs) -> LogContext:
    """Create a log context with request information

    Usage:
        with request_context(request_id="abc", user="admin"):
            logger.info("Processing request")
    """
    return LogContext(**kwargs)


def set_request_context(**kwargs):
    """Set request context without context manager"""
    current = _request_context.get().copy()
    current.update(kwargs)
    _request_context.set(current)


def get_request_context() -> dict:
    """Get current request context"""
    return _request_context.get().copy()


def clear_request_context():
    """Clear request context"""
    _request_context.set({})


def generate_request_id() -> str:
    """Generate a unique request ID"""
    return str(uuid.uuid4())[:8]


def json_sink(message):
    """Sink function for JSON output"""
    record = message.record
    context = _request_context.get()

    log_entry = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
    }

    # Add request context
    if context:
        log_entry["context"] = context

    # Add extra fields from record
    if record.get("extra"):
        for key, value in record["extra"].items():
            if key not in ("request_id",):  # Skip internal keys
                log_entry[key] = value

    # Add exception info if present
    if record["exception"]:
        log_entry["exception"] = {
            "type": record["exception"].type.__name__ if record["exception"].type else None,
            "value": str(record["exception"].value) if record["exception"].value else None,
        }

    sys.stderr.write(json.dumps(log_entry, default=str, ensure_ascii=False) + "\n")


def colorized_format(record: dict) -> str:
    """Format string for colorized output"""
    context = _request_context.get()

    # Build context string
    ctx_str = ""
    if context:
        ctx_parts = [f"{k}={v}" for k, v in context.items()]
        ctx_str = f" <yellow>[{', '.join(ctx_parts)}]</yellow>"

    # Format template
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
        + ctx_str +
        " - <level>{message}</level>\n"
    )

    if record["exception"]:
        fmt += "{exception}\n"

    return fmt


# 分類規則:module 名稱(來自 get_logger(name))對應到哪些檔案
# 排序由窄到寬(更具體的規則放前面),但實際上每個 record 會經過所有 sink
# (每個 sink 自己判斷是否要寫),所以一筆 log 可能同時寫到 app.log + http.log + error.log
LOG_CATEGORIES = {
    # category_name → (filter_fn, level_override or None)
    "http":  (lambda m: m == "http", None),
    "auth":  (lambda m: m.startswith("auth") or m == "security", None),
    "db":    (lambda m: m.startswith("db"), None),
}

_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{extra[module]}:{function}:{line} - {message}"
)


def _make_module_filter(predicate):
    """Build a loguru filter that matches by extra['module']"""
    def filter_fn(record):
        module = record["extra"].get("module", "")
        return predicate(module)
    return filter_fn


def setup_logging(
    level: str = "INFO",
    format_type: str = "colorized",
    log_dir: str = "logs",
    rotation: str = "00:00",
    rotation_max_size: str = "50 MB",
    retention: str = "60 days",
    compression: str = "zip",
):
    """Setup logging configuration with category-based file splits.

    產出檔案(假設 log_dir="logs"):
        logs/app_YYYY-MM-DD.log     全部 INFO+
        logs/http_YYYY-MM-DD.log    HTTP 請求
        logs/auth_YYYY-MM-DD.log    認證/權限/安全
        logs/db_YYYY-MM-DD.log      資料庫操作
        logs/error_YYYY-MM-DD.log   所有 ERROR+(跨模組安全網)

    輪替:每日 00:00;保留 retention;舊檔自動壓縮。

    Args:
        level: 預設層級(DEBUG/INFO/WARNING/ERROR/CRITICAL)
        format_type: console 格式 — "json" 或 "colorized"
        log_dir: 分類 log 的目錄
        rotation: loguru 輪替條件,例如 "00:00" / "1 day" / "100 MB"
        rotation_max_size: 預留接口(時間+大小組合 rotation,目前未啟用)
        retention: 保留期,例如 "60 days"
        compression: 舊檔壓縮 — "zip" / "gz" / "bz2" / None
    """
    # Remove default handler
    logger.remove()

    # 全域 extra 預設值 — 避免有人直接 `from loguru import logger` 用,
    # 沒 bind module 結果踩 `{extra[module]}` 的 KeyError
    logger.configure(extra={"module": "unknown"})

    # ---- Console sink ----
    if format_type == "json":
        logger.add(json_sink, level=level, colorize=False)
    else:
        logger.add(sys.stderr, format=colorized_format, level=level, colorize=True)

    # ---- File sinks ----
    from pathlib import Path
    dir_path = Path(log_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    # 輪替策略:每日 00:00 換檔(rotation_max_size 預留接口,目前 loguru
    # 公開 API 不支援「時間 OR 大小」組合條件,要組合得用 callable + 私有 API,
    # 太脆弱,先單純時間輪替即可。單日爆量極罕見;真要防可降到 "12:00" 半日)
    del rotation_max_size  # 顯式標示未用,避免 lint 抱怨

    # 「全部」彙整檔
    logger.add(
        str(dir_path / "app_{time:YYYY-MM-DD}.log"),
        format=_FILE_FORMAT,
        level=level,
        rotation=rotation,
        retention=retention,
        compression=compression,
        enqueue=True,  # 非阻塞 — 多 sink 寫入時必開,避免 IO 卡住主線程
    )

    # 分類檔案
    for cat_name, (filter_pred, level_override) in LOG_CATEGORIES.items():
        logger.add(
            str(dir_path / f"{cat_name}_{{time:YYYY-MM-DD}}.log"),
            format=_FILE_FORMAT,
            level=level_override or level,
            filter=_make_module_filter(filter_pred),
            rotation=rotation,
            retention=retention,
            compression=compression,
            enqueue=True,
        )

    # 跨模組的 ERROR 安全網 — 不論哪個 module 出 ERROR 都寫這
    logger.add(
        str(dir_path / "error_{time:YYYY-MM-DD}.log"),
        format=_FILE_FORMAT,
        level="ERROR",
        rotation=rotation,
        retention=retention,
        compression=compression,
        enqueue=True,
        backtrace=True,
        diagnose=True,  # ERROR 多附 variable 值,debug 快很多
    )

    logger.bind(module="logger").info(
        f"Logging configured: level={level}, format={format_type}, "
        f"log_dir={log_dir}, rotation={rotation}, retention={retention}"
    )


def get_logger(name: Optional[str] = None):
    """Get a logger instance

    Args:
        name: Optional module name for the logger

    Returns:
        Logger instance bound with the module name
    """
    if name:
        return logger.bind(module=name)
    return logger


# Convenience exports
log = logger
