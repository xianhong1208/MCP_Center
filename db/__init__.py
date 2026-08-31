"""資料庫模組

對外 API:
    Base            ORM 基底
    get_db          FastAPI dependency(取 session,自動 close)
    make_session    手動取得 session(必須自己 close)
    get_engine      取 SQLAlchemy engine
    seed_database   啟動時的種子資料(OAuth scope 註冊表、內建 client、擁有者帳號)
"""
from db.database import Base, get_db, make_session, get_engine, reset_engine
from db.models import AdminUser
from db.seed import seed_database

__all__ = [
    "Base", "get_db", "make_session", "get_engine", "reset_engine",
    "AdminUser", "seed_database",
]
