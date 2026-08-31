"""本機密鑰儲存:環境變數優先,否則自動產生並持久化到 data/secrets.json。

個人專案要能「clone 下來直接跑」,所以 SESSION_SECRET_KEY / ENCRYPTION_KEY 不再強制
要求人工設定。第一次啟動時自動產生、寫入 data/secrets.json(權限 0600),之後每次啟動
都讀同一份 —— 尤其 ENCRYPTION_KEY 一旦換掉,DB 內所有加密資料都解不開。
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Dict, Optional

_DEFAULT_PATH = Path("data") / "secrets.json"
_cache: Dict[str, str] = {}


def _store_path() -> Path:
    override = os.environ.get("MCP_CENTER_SECRETS_FILE")
    return Path(override) if override else _DEFAULT_PATH


def _load_file() -> Dict[str, str]:
    path = _store_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_file(data: Dict[str, str]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


def get_secret(name: str, *, env_var: Optional[str] = None, length: int = 32) -> str:
    """取得密鑰:env → cache → data/secrets.json → 自動產生並存檔。"""
    env_name = env_var or name
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    if name in _cache:
        return _cache[name]
    data = _load_file()
    if data.get(name):
        _cache[name] = data[name]
        return data[name]
    generated = secrets.token_urlsafe(length)
    data[name] = generated
    _save_file(data)
    _cache[name] = generated
    return generated


def reset_cache() -> None:
    _cache.clear()
