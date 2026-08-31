"""資料庫引擎與 session 工廠(全 lazy;SQLite / PostgreSQL 皆可)。

對外 API:
    Base            ORM 基底
    get_engine()    singleton engine
    make_session()  取得一個 Session(呼叫端負責 close)
    get_db()        FastAPI dependency
    reset_engine()  測試用:換 URL 後重建
"""

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, make_url
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.config import Config

Base = declarative_base()

_engine = None
_session_factory = None


def is_sqlite_url(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


def _ensure_sqlite_dir(url: str) -> None:
    db_path = make_url(url).database
    if db_path and db_path != ":memory:":
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def get_engine():
    global _engine
    if _engine is None:
        db_config = Config.get_database_config()
        url = db_config.url
        if is_sqlite_url(url):
            _ensure_sqlite_dir(url)
            _engine = create_engine(
                url,
                echo=db_config.echo,
                connect_args={"check_same_thread": False},
            )

            @event.listens_for(_engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _record):
                # 外鍵約束(ON DELETE CASCADE)與 WAL(讀寫並行)在 SQLite 預設是關的
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()
        else:
            _engine = create_engine(
                url,
                echo=db_config.echo,
                pool_size=db_config.pool_size,
                max_overflow=db_config.max_overflow,
                pool_pre_ping=True,
            )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _session_factory


def make_session() -> Session:
    return _get_session_factory()()


def get_db() -> Generator[Session, None, None]:
    db = make_session()
    try:
        yield db
    finally:
        db.close()


def reset_engine() -> None:
    """丟掉 singleton(測試切換 DB URL 時用)。"""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
