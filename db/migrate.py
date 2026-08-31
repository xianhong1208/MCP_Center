"""Database Migration Manager

封裝 Alembic 操作,提供乾淨的 Python API 給 main.py 與 CLI 使用。

設計重點:
  - 使用 Alembic 高階 API(`command.*`),不用自己 parse migration 檔案
  - `auto_migrate()` 處理三種 DB 狀態:全新 / 舊有但無 alembic 紀錄 / 已在 alembic 管理下
  - 「schema 超前 alembic_version」的歷史包袱會自動修(stamp 到 head)

CLI 用法:
    python -m db.migrate                    # 預設 auto
    python -m db.migrate status             # 顯示狀態
    python -m db.migrate upgrade            # 升級到 head
    python -m db.migrate downgrade -r -1    # 退一版
    python -m db.migrate generate -m "..."  # 產生新 migration(autogenerate)
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from typing import Optional, Tuple

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from src.config import Config
from src.logging import get_logger
from src.utils.runtime_paths import resolve_external_dir


def _env_flag_enabled(name: str) -> bool:
    """Parse a boolean env var safely.

    bool("false") is True in Python (non-empty string),所以不能用 bool(os.environ.get).
    """
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")

# Dev 模式下的專案根:db/migrate.py → 上一層即 project root
_dev_project_root = Path(__file__).resolve().parent.parent

logger = get_logger("db.migrate")


def _resolve_alembic_dir() -> Path:
    """跨部署模式找 alembic/ 目錄

    解析順序(由 resolve_external_dir 提供):
      ① Nuitka onefile 真實 binary 旁邊
      ② /proc/self/exe 旁邊
      ③ sys.executable 旁邊
      ④ /app/alembic(Docker volume mount)
      ⑤ dev 模式 project_root / alembic
    """
    resolved = resolve_external_dir("alembic", dev_root=_dev_project_root)
    if resolved is None:
        raise FileNotFoundError(
            f"alembic/ directory not found. Looked in Nuitka binary dir, "
            f"/app/alembic, and {_dev_project_root / 'alembic'}"
        )
    return resolved


class DatabaseMigrator:
    """封裝 Alembic 操作的單一進入點

    每個 public method 都是冪等的(跑幾次都不會炸),適合 server 啟動流程。
    """

    # 「DB 已被應用初始化過」的判斷依據 — 出現任一張表就算
    APP_TABLE_MARKERS = ("services", "admin_users", "oauth_clients")

    def __init__(self):
        self.alembic_dir = _resolve_alembic_dir()
        self.project_root = self.alembic_dir.parent

        self.db_url = Config.get_database_config().url

        # 不使用 alembic.ini — 所有設定純 Python API 注入。alembic CLI 已不支援使用。
        self.alembic_cfg = AlembicConfig()
        self.alembic_cfg.set_main_option("script_location", str(self.alembic_dir))
        self.alembic_cfg.set_main_option("sqlalchemy.url", self.db_url)
        logger.debug(f"Alembic dir resolved to: {self.alembic_dir}")

    # ---- 內部工具 ----

    def _get_engine(self):
        """延遲取得 engine — 避免在 import 階段就連線"""
        from db.database import get_engine
        return get_engine()

    def _get_db_revision(self) -> Optional[str]:
        """讀 alembic_version 表的當前版本(若表不存在回 None)"""
        engine = self._get_engine()
        inspector = inspect(engine)
        if "alembic_version" not in inspector.get_table_names():
            return None
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            return row[0] if row else None

    def _get_head_revision(self) -> Optional[str]:
        """讀 migration 檔案的 head revision"""
        script = ScriptDirectory.from_config(self.alembic_cfg)
        return script.get_current_head()

    def _classify_db_state(self) -> str:
        """判斷 DB 處於哪種狀態,回傳:
        - "fresh"         全新空 DB(沒 alembic 也沒 app 表)
        - "legacy"        舊 DB 有 app 表但沒 alembic 紀錄
        - "managed"       已被 alembic 管理(有 alembic_version 表)
        """
        engine = self._get_engine()
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        has_alembic = "alembic_version" in tables
        has_app_tables = any(t in tables for t in self.APP_TABLE_MARKERS)

        if has_alembic:
            return "managed"
        if has_app_tables:
            return "legacy"
        return "fresh"

    # ---- Public API ----

    def auto_migrate(self) -> bool:
        """自動 migration — server 啟動預設呼叫這個

        分三種情況處理:
          fresh   → 從頭跑所有 migration
          legacy  → stamp 到 head(視為已套用完畢,但日後 migration 仍會 run)
          managed → 比對 db_rev 與 head_rev,需要才 upgrade

        關於 DuplicateTable / DuplicateColumn 自動修復:
          預設 **關閉**。若 upgrade 中途撞到 schema 已存在的衝突,直接 fail
          並要求人工介入 — 這類錯誤可能是:
            (a) 歷史包袱:舊 create_all() 殘留(可安全 stamp)
            (b) Partial migration 失敗:前一次 upgrade 跑到一半 crash
            (c) 多進程競態:另一個 server instance 同時跑 migration
          (b)(c) 情境下 stamp head 會把破損 DB 標記為「最新」,後續 autogenerate
          會悄悄丟東西。要啟用自動 stamp,設 `ALEMBIC_AUTO_STAMP_ON_CONFLICT=true`,
          並確認你的部署只會撞到 (a)。
        """
        try:
            state = self._classify_db_state()
            head_rev = self._get_head_revision()
            logger.info(f"DB state: {state}, head revision: {head_rev}")

            if state == "fresh":
                logger.info("Fresh database, running all migrations...")
                alembic_command.upgrade(self.alembic_cfg, "head")
                logger.info("All migrations applied")
                return True

            if state == "legacy":
                logger.info(f"Legacy database without alembic history, stamping to head ({head_rev})...")
                alembic_command.stamp(self.alembic_cfg, "head")
                logger.info("Stamped to head")
                return True

            # state == "managed"
            db_rev = self._get_db_revision()
            if db_rev == head_rev:
                logger.info(f"Database already at latest revision ({db_rev})")
                return True

            logger.info(f"Database at {db_rev}, upgrading to {head_rev}...")
            try:
                alembic_command.upgrade(self.alembic_cfg, "head")
                logger.info("Upgrade complete")
                return True
            except Exception as err:
                err_str = str(err)
                is_dup_conflict = any(
                    k in err_str for k in ("already exists", "DuplicateTable", "DuplicateColumn")
                )
                if not is_dup_conflict:
                    raise

                # 撞到 schema-already-exists 衝突 — 預設不自動 stamp
                auto_stamp = _env_flag_enabled("ALEMBIC_AUTO_STAMP_ON_CONFLICT")
                if not auto_stamp:
                    logger.error(
                        f"Migration conflict (schema ahead of version): {err}"
                    )
                    logger.error(
                        f"  DB at revision {db_rev}, head is {head_rev}"
                    )
                    logger.error(
                        "  This may be a historical artifact OR a partial migration failure."
                    )
                    logger.error(
                        "  Manual investigation required. If you confirm the schema is correct,"
                    )
                    logger.error(
                        "  run: ALEMBIC_AUTO_STAMP_ON_CONFLICT=true python -m db.migrate auto"
                    )
                    logger.error(
                        f"  OR explicitly: python -m db.migrate stamp -r {head_rev}"
                    )
                    self._rollback_dirty_transaction()
                    raise

                logger.warning(
                    f"ALEMBIC_AUTO_STAMP_ON_CONFLICT=true — auto-stamping to {head_rev} "
                    f"despite migration conflict: {err}"
                )
                self._rollback_dirty_transaction()
                alembic_command.stamp(self.alembic_cfg, "head")
                logger.info(f"Stamped to {head_rev} (auto-recovery via env var)")
                return True

        except Exception as e:
            logger.error(f"Auto migration failed: {e}")
            traceback.print_exc()
            return False

    def _rollback_dirty_transaction(self) -> None:
        """alembic upgrade 失敗時 transaction 可能殘留,主動清掉"""
        try:
            with self._get_engine().connect() as conn:
                conn.execute(text("ROLLBACK"))
        except Exception:
            pass

    def upgrade(self, revision: str = "head") -> bool:
        try:
            logger.info(f"Upgrading database to: {revision}")
            alembic_command.upgrade(self.alembic_cfg, revision)
            logger.info("Upgrade complete")
            return True
        except Exception as e:
            logger.error(f"Upgrade failed: {e}")
            return False

    def downgrade(self, revision: str = "-1") -> bool:
        try:
            logger.warning(f"Downgrading database to: {revision}")
            alembic_command.downgrade(self.alembic_cfg, revision)
            logger.info("Downgrade complete")
            return True
        except Exception as e:
            logger.error(f"Downgrade failed: {e}")
            return False

    def stamp(self, revision: str = "head") -> bool:
        try:
            logger.info(f"Stamping database at: {revision}")
            alembic_command.stamp(self.alembic_cfg, revision)
            return True
        except Exception as e:
            logger.error(f"Stamp failed: {e}")
            return False

    def status(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """回傳 (is_up_to_date, current_rev, head_rev) — 並印出可讀報告"""
        db_rev = self._get_db_revision()
        head_rev = self._get_head_revision()
        is_up_to_date = (db_rev == head_rev and db_rev is not None)

        print("=" * 50)
        print("DATABASE MIGRATION STATUS")
        print("=" * 50)
        print(f"Current revision: {db_rev or '(none)'}")
        print(f"Head revision:    {head_rev or '(none)'}")
        print(f"DB state:         {self._classify_db_state()}")
        print(f"Up to date:       {is_up_to_date}")
        print("=" * 50)

        return is_up_to_date, db_rev, head_rev

    def current(self) -> bool:
        rev = self._get_db_revision()
        print(rev if rev else "(no revision - database not initialized)")
        return True

    def heads(self) -> bool:
        rev = self._get_head_revision()
        print(rev if rev else "(no head revision)")
        return True

    def history(self) -> bool:
        alembic_command.history(self.alembic_cfg)
        return True

    def create_migration(self, message: str) -> bool:
        try:
            logger.info(f"Creating migration: {message}")
            alembic_command.revision(self.alembic_cfg, message=message, autogenerate=True)
            logger.info("Migration created")
            return True
        except Exception as e:
            logger.error(f"Create migration failed: {e}")
            return False


def run_migration_command(action: str, message: Optional[str] = None,
                          revision: str = "-1") -> bool:
    """Dispatch migration action — 給 main.py 與 CLI 共用

    Actions:
        auto       自動套用所有未套用的 migrations(預設)
        status     顯示狀態
        upgrade    升級到指定 revision(--revision,預設 head)
        downgrade  降級到指定 revision
        rollback   等同 downgrade
        stamp      標記版本但不執行
        current    顯示當前版本
        heads      顯示 head 版本
        history    顯示歷史
        generate   產生新 migration(需要 --message)
    """
    try:
        m = DatabaseMigrator()
    except Exception as e:
        logger.error(f"Failed to init migrator: {e}")
        return False

    actions = {
        "auto":      lambda: m.auto_migrate(),
        "status":    lambda: (m.status(), True)[1],
        "upgrade":   lambda: m.upgrade(revision if revision != "-1" else "head"),
        "downgrade": lambda: m.downgrade(revision),
        "rollback":  lambda: m.downgrade(revision),
        "stamp":     lambda: m.stamp(revision if revision != "-1" else "head"),
        "current":   lambda: m.current(),
        "heads":     lambda: m.heads(),
        "history":   lambda: m.history(),
    }

    if action == "generate":
        if not message:
            logger.error("Migration message required for generate (use -m)")
            return False
        return m.create_migration(message)

    handler = actions.get(action)
    if handler is None:
        valid = ", ".join(sorted(list(actions.keys()) + ["generate"]))
        logger.error(f"Unknown migration action: '{action}'. Valid: {valid}")
        return False

    return handler()


def main():
    """CLI entry point: python -m db.migrate [action]"""
    import argparse
    import os

    # CLI 走獨立進入點,必須自己載 .env + config(server 模式由 main.py 處理)
    from dotenv import load_dotenv
    load_dotenv(_dev_project_root / ".env")

    parser = argparse.ArgumentParser(
        description="MCP Center Database Migration Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m db.migrate                       # auto migrate
    python -m db.migrate status                # show status
    python -m db.migrate upgrade               # upgrade to head
    python -m db.migrate downgrade -r -1       # rollback one
    python -m db.migrate generate -m "add X"   # autogenerate migration
        """,
    )
    parser.add_argument("action", nargs="?", default="auto",
                       choices=["auto", "status", "upgrade", "downgrade", "rollback",
                                "stamp", "current", "heads", "history", "generate"])
    parser.add_argument("-m", "--message", help="Migration message (for generate)")
    parser.add_argument("-r", "--revision", default="-1",
                       help="Target revision for upgrade/downgrade/stamp")
    parser.add_argument("--config", default=os.environ.get("TOKEN_SERVER_CONFIG", "config/config.yaml"),
                       help="Path to config.yaml")
    args = parser.parse_args()

    Config.set_config(args.config)

    # 連 DB 前先確保 DB 存在(generate 不需要 DB,例外)
    if args.action != "generate":
        import logging
        cli_logger = logging.getLogger("db.migrate")
        if not cli_logger.handlers:
            logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
        from src.utils.db_bootstrap import ensure_database_ready
        ensure_database_ready(Config.get_database_config().url, cli_logger)

    success = run_migration_command(args.action, args.message, args.revision)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
