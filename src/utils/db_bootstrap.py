"""DB Bootstrap — 確保目標 DB 存在(在 Alembic migration 之前跑)

雞生蛋問題:`CREATE DATABASE` 不能在自己內部執行,必須先連到 PostgreSQL
預設的 `postgres` 系統 DB 才能下指令;且 CREATE DATABASE 不能在 transaction
內,故用 AUTOCOMMIT。

流程:
  1. 解析 DATABASE_URL,取出目標 dbname 並驗證
  2. 用 SQLAlchemy engine 連 `postgres` 系統 DB(AUTOCOMMIT)
  3. 查 pg_database;不存在則 CREATE DATABASE

設計考量:
  - PostgreSQL 才需要;SQLite 只確保目錄存在。
  - 冪等:跑幾次都安全;並發下若被別人先建好,吞掉 duplicate 錯誤。
  - 一律走 SQLAlchemy(與專案其餘 DB 存取一致);identifier 以 SQL 標準跳脫
    (雙引號括住 + 內嵌 " 加倍),dbname 另先過 _validate_dbname 白名單。
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.exc import ProgrammingError

# Postgres 識別字上限 63 bytes (NAMEDATALEN-1)。超過會被**靜默截斷**,於是
# CREATE DATABASE 建出來的名字和後續連線用的名字不一致,產生很難查的錯誤。
_MAX_IDENTIFIER_BYTES = 63

# dbname 白名單。用於在來源端 fail-fast:
#   1. 讓 config → SQL 這條路徑上有明確的 sanitizer。
#   2. 擋掉打錯的 DATABASE_URL(整段 URL 被誤當成 dbname、超長被截斷等)。
_DBNAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$-]*")


def _validate_dbname(dbname: str) -> str:
    """驗證從 DATABASE_URL 解析出來的 dbname,不合法就 raise ValueError。

    呼叫端(main.py)已把 bootstrap 包在 try/except 裡並 sys.exit(1),所以設定
    錯誤會在開機時明確失敗,而不是帶著怪名字繼續跑。
    """
    if not _DBNAME_RE.fullmatch(dbname):
        raise ValueError(
            f"DATABASE_URL 的資料庫名稱不合法: {dbname!r}。"
            f"只允許字母/數字/底線/連字號/$,且須以字母或底線開頭"
        )
    if len(dbname.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise ValueError(
            f"DATABASE_URL 的資料庫名稱超過 Postgres 上限 "
            f"{_MAX_IDENTIFIER_BYTES} bytes(會被靜默截斷): {dbname!r}"
        )
    return dbname


def _parse_db_url(url: str) -> dict:
    parsed = urlparse(url)
    # urlparse 不解百分比編碼,但 SQLAlchemy make_url(引擎端)會 —— 帳密含特殊
    # 字元(如 p%40ss = p@ss)時需一致。手動 unquote 帳號/密碼,與 make_url 對齊。
    return {
        "scheme": parsed.scheme,
        "user": unquote(parsed.username) if parsed.username else parsed.username,
        "password": unquote(parsed.password) if parsed.password else parsed.password,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/"),
    }


def ensure_database_ready(db_url: str, logger) -> None:
    """確保目標 DB 存在(冪等)

    呼叫時機:必須在 alembic migration / 任何 ORM 操作之前。

    Args:
        db_url: SQLAlchemy DB URL,例如 postgresql://user:pwd@host/dbname
        logger: 主程式 logger 實例

    Raises:
        sqlalchemy.exc.OperationalError: 連 postgres 系統 DB 都失敗(密碼錯/服務沒起)
        sqlalchemy.exc.ProgrammingError: 無 CREATEDB 權限等
    """
    params = _parse_db_url(db_url)

    # 非 PostgreSQL(例如 SQLite)不需要 bootstrap — SQLite 第一次 open 就建檔
    if not params["scheme"].startswith("postgres"):
        # SQLite:確保資料夾存在即可,第一次 open 就會建檔
        if params["scheme"].startswith("sqlite"):
            from db.database import _ensure_sqlite_dir
            _ensure_sqlite_dir(db_url)
        logger.debug(f"DB scheme '{params['scheme']}' is not postgres, skipping bootstrap")
        return

    target_dbname = params["dbname"]
    if not target_dbname:
        logger.warning("⚠️ No database name in DATABASE_URL, skipping bootstrap")
        return

    # 在任何連線 / SQL 之前驗證 dbname(見 _validate_dbname 的說明)
    target_dbname = _validate_dbname(target_dbname)

    logger.info(f"Bootstrapping database '{target_dbname}'...")

    # 連 postgres 系統 DB 才能 CREATE DATABASE。make_url 安全處理帳密特殊字元,
    # 並把目標 dbname 換成 postgres;AUTOCOMMIT 因 CREATE DATABASE 不能在
    # transaction 內執行。
    admin_url = make_url(db_url).set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target_dbname},
            ).scalar()
            if exists:
                logger.info(f"Database '{target_dbname}' already exists")
                return

            logger.warning(f"Database '{target_dbname}' not found, creating...")
            # CREATE DATABASE 不能用 bind param 帶 identifier。以 SQL 標準跳脫:
            # 雙引號括住 identifier,內嵌的 " 加倍。dbname 另已過 _validate_dbname
            # 白名單(根本不含 "),此為 defense-in-depth。
            safe_name = target_dbname.replace('"', '""')
            conn.execute(text(f'CREATE DATABASE "{safe_name}"'))
            logger.info(f"Database '{target_dbname}' created successfully")
    except ProgrammingError as e:
        # 並發下另一個 process 先建好(duplicate_database)→ 視同成功
        if "already exists" in str(e).lower():
            logger.info(f"Database '{target_dbname}' was created concurrently (by another process)")
            return
        raise
    finally:
        admin_engine.dispose()
