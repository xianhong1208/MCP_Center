"""架構 fitness function:三層不變量

routes(src/api、main.py)→ adapters(src/adapters)→ db.crud。
只有 adapter 層可以 import db.crud;這條規則原本只寫在 src/adapters/__init__.py 的
文件裡、靠人工 grep 檢查,這裡把它釘進 CI —— 誰在 route 直接 import crud 就會紅。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CRUD_IMPORT = re.compile(r"^\s*(from\s+db\.crud\b|import\s+db\.crud\b)", re.M)


def _py_files(*dirs: str):
    for d in dirs:
        p = ROOT / d
        if p.is_file():
            yield p
        else:
            yield from p.rglob("*.py")


def test_only_adapters_import_db_crud():
    offenders = []
    for f in _py_files("main.py", "src"):
        rel = f.relative_to(ROOT).as_posix()
        if rel.startswith("src/adapters/"):
            continue
        if CRUD_IMPORT.search(f.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], f"這些檔案繞過 adapter 層直接 import db.crud:{offenders}"


def test_adapters_do_import_crud():
    """反向哨兵:若 adapter 層完全不 import crud,代表規則的前提已改變,測試也該重寫。"""
    assert any(
        CRUD_IMPORT.search(f.read_text(encoding="utf-8")) for f in _py_files("src/adapters")
    )


@pytest.mark.parametrize("layer", ["src/api", "src/orchestrator", "src/discovery"])
def test_no_direct_db_session_commit_outside_adapters(layer):
    """route / 服務層不應自己 db.commit():交易邊界屬於 adapter。

    scheduler 不在此列 —— 它自己 make_session(),交易由它自己負責。
    下面的允許清單是「已知技術債的盤點」,不是許可:數字只能往下走,
    收斂一個就從清單刪一個;新增檔案一律不得直接 commit。
    """
    allowed = {}
    offenders = []
    for f in _py_files(layer):
        rel = f.relative_to(ROOT).as_posix()
        n = len(re.findall(r"\bdb\.commit\(\)", f.read_text(encoding="utf-8")))
        if n > allowed.get(rel, 0):
            offenders.append(f"{rel} ({n} > allowed {allowed.get(rel, 0)})")
    assert offenders == [], f"{layer} 內直接 db.commit() 超出已盤點的技術債:{offenders}"
