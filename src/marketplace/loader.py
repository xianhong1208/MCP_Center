"""Marketplace catalog loader

掃 catalog/*.yaml 全部載入並快取。所有 YAML 都經過 Pydantic 驗證。

錯誤處理策略:**跳過壞檔,不要拖垮整個 marketplace**。
單一 catalog YAML 驗證失敗時只記 logger.error 並略過該檔,錯誤留在
`errors` 供 debug;其餘 entry 照常提供。理由:MCP Center 的主要職責是
發 token,不該因為一個選配的 catalog 檔打錯字就讓 /auth/marketplace 回
500(甚至擋住開機)。main.py 在 startup 會主動呼叫 load_all(),所以問題
會出現在開機 log 裡,而不是等到管理者點進 marketplace 才發現。

已安裝但 catalog 變成無效的 process 會走 orchestrator 既有的錯誤路徑:
`_start_locked` 找不到 catalog entry 會 raise OrchestratorError,reconcile
把它標成 actual_state=failed 並寫入 last_error — 明確失敗,不會靜默。
"""
import logging
from pathlib import Path
from typing import Dict, Optional

import yaml

from src.marketplace.schema import CatalogEntry

logger = logging.getLogger(__name__)


class CatalogLoadError(Exception):
    """讀取或驗證 catalog YAML 失敗"""


class CatalogLoader:
    def __init__(self, catalog_dir: Path):
        self.catalog_dir = catalog_dir
        self._cache: Optional[Dict[str, CatalogEntry]] = None
        # filename → error message;每次 load 重建
        self._errors: Dict[str, str] = {}

    def load_all(self) -> Dict[str, CatalogEntry]:
        """讀所有 catalog YAML,回傳 id → CatalogEntry 的 dict。
        結果快取,只會在首次呼叫時真的讀檔。
        """
        if self._cache is not None:
            return self._cache

        if not self.catalog_dir.exists():
            # 允許 catalog 資料夾不存在(開發初期),回傳空 dict
            self._cache = {}
            self._errors = {}
            return self._cache

        entries: Dict[str, CatalogEntry] = {}
        errors: Dict[str, str] = {}
        for yaml_path in sorted(self.catalog_dir.glob("*.yaml")):
            try:
                with yaml_path.open("r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
                entry = CatalogEntry(**raw)
            except Exception as e:
                msg = f"{e}"
                logger.error(
                    f"Skipping invalid catalog entry {yaml_path.name}: {msg}"
                )
                errors[yaml_path.name] = msg
                continue

            if entry.id in entries:
                msg = f"Duplicate catalog id '{entry.id}'"
                logger.error(f"Skipping {yaml_path.name}: {msg}")
                errors[yaml_path.name] = msg
                continue

            entries[entry.id] = entry

        self._cache = entries
        self._errors = errors
        return entries

    @property
    def errors(self) -> Dict[str, str]:
        """上次 load 中被跳過的檔案 → 原因。load_all() 之後才有意義。"""
        return dict(self._errors)

    def get(self, catalog_id: str) -> Optional[CatalogEntry]:
        return self.load_all().get(catalog_id)

    @property
    def images_dir(self) -> Path:
        """離線 image tar 的存放目錄(catalog_dir/images)。"""
        return self.catalog_dir / "images"

    def image_tar_path(self, entry: CatalogEntry) -> Path:
        """某 catalog 項目的 image tar 完整路徑(檔案不一定存在)。"""
        return self.images_dir / entry.image_tar_name()

    def reload(self) -> Dict[str, CatalogEntry]:
        """清除快取並重新讀取;給熱重載或測試用"""
        self._cache = None
        self._errors = {}
        return self.load_all()


# -------- Singleton ----------

_default_loader: Optional[CatalogLoader] = None


def get_catalog_loader() -> CatalogLoader:
    """取得預設 catalog loader

    路徑優先順序:
      1. 環境變數 MCP_CATALOG_DIR(絕對路徑)
      2. project_root / catalog/  (跟 main.py 的邏輯一致:
         project_root = Path(sys.argv[0]).parent)
    """
    global _default_loader
    if _default_loader is None:
        import os
        import sys
        env = os.environ.get("MCP_CATALOG_DIR")
        if env:
            catalog_dir = Path(env)
        else:
            project_root = Path(os.path.abspath(sys.argv[0])).parent
            catalog_dir = project_root / "catalog"
        _default_loader = CatalogLoader(catalog_dir)
    return _default_loader
