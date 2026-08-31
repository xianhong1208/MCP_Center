"""Runtime path resolution for dev / Nuitka / Docker deployments.

為什麼這個檔案存在
----------------
`Path(__file__).parent / "xxx"` 在 dev 模式正確,但在 Nuitka onefile 模式下會壞:
- Nuitka onefile 啟動會把整個壓縮包解到 `/tmp/onefile_<pid>_<rnd>/` 臨時目錄
- `__file__` 指向 `/tmp/onefile_xxx/...`,不是真正 binary 旁邊
- 結果讀到的是「打包當下的舊 snapshot」而非使用者真正部署的檔案

提供 `resolve_external_dir(name, dev_root)` 統一處理:
  1. Nuitka onefile:用 `NUITKA_ONEFILE_PARENT` env var + `/proc/<pid>/exe` 找真實位置
  2. Nuitka standalone:用 `sys.executable` 或 `/proc/self/exe`
  3. Docker container:`/app/{name}` 慣例
  4. Dev 模式:呼叫端傳進來的 `dev_root`
  5. Fallback 到 onefile 解壓目錄的 bundled copy

`/app/{name}` 排在 dev_root 前面,讓 Docker volume mount 的真實內容贏過 bundled snapshot。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional


def resolve_external_dir(name: str, dev_root: Path) -> Optional[Path]:
    """跨部署模式定位外部資源目錄

    Args:
        name: 目錄名稱(例如 "alembic"、"config"、"catalog")
        dev_root: dev 模式下的專案根目錄

    Returns:
        第一個存在的候選目錄,全部找不到回 None
    """
    candidates: List[Path] = []

    # ① Nuitka onefile:NUITKA_ONEFILE_PARENT 指向啟動 binary 的父 process
    nuitka_parent = os.environ.get("NUITKA_ONEFILE_PARENT")
    if nuitka_parent:
        try:
            parent_exe = Path(f"/proc/{nuitka_parent}/exe").resolve()
            if parent_exe.exists():
                candidates.append(parent_exe.parent / name)
        except (OSError, ValueError):
            pass

    # ② Linux 通用:/proc/self/exe 永遠指向當前 process 真正執行的 binary
    # 拒絕 /tmp/onefile_* 假路徑(onefile 解壓目錄裡的 binary)
    if sys.platform.startswith("linux"):
        try:
            proc_exe = Path("/proc/self/exe").resolve()
            if not str(proc_exe).startswith("/tmp/onefile_"):
                candidates.append(proc_exe.parent / name)
        except (OSError, ValueError):
            pass

    # ③ Nuitka standalone(非 onefile):sys.executable 就是真實 binary
    try:
        exe_path = Path(sys.executable).resolve()
        if not str(exe_path).startswith("/tmp/onefile_"):
            candidates.append(exe_path.parent / name)
    except (OSError, ValueError):
        pass

    # ④ Docker container 慣例(刻意排在 dev_root 之前,
    # 讓 volume mount 贏過 onefile bundled copy)
    candidates.append(Path(f"/app/{name}"))

    # ⑤ Dev mode / onefile bundled fallback
    candidates.append(dev_root / name)

    for p in candidates:
        if p.is_dir():
            return p
    return None


def get_runtime_project_root() -> Path:
    """取得 runtime 的「外部資源根目錄」— 跟 main.py 那行邏輯一致

    用於需要相對路徑但不必通過 `resolve_external_dir()` 多目錄搜尋的場景。
    Dev / Nuitka 都正確;但無法處理「binary 在 A、resource 在 B」的部署模式,
    那種情況請改用 `resolve_external_dir()`。
    """
    return Path(os.path.abspath(sys.argv[0])).parent
