"""MCP Center 版本資訊

版本號的**唯一來源**是 `pyproject.toml` 的 `[project].version`。
本模組於載入時「抓」pyproject,避免多處手動同步。

解析順序(先檔案、後 metadata):
  1. 直接讀 pyproject.toml — source checkout / 開發時永遠即時(不受 editable
     安裝 metadata 過期影響)。
  2. importlib.metadata — 已 pip 安裝但找不到 pyproject 時(由 pyproject 帶入)。
  3. 退回 "0.0.0+unknown" — 避免 crash。

> 打包(Nuitka onefile)注意:pyproject.toml 不在 bundle 內時第 1 步會失敗。
> 請於 Build Center 打包時擇一:把 pyproject.toml 納入 data、含套件 metadata,
> 或如同 __build_time__/__build_commit__ 一樣在編譯時注入 __version__。
"""

from pathlib import Path


def _read_version() -> str:
    # 1) 直接讀 pyproject.toml(唯一來源,開發時永遠即時)
    try:
        import tomllib
        for parent in Path(__file__).resolve().parents:
            pyproject = parent / "pyproject.toml"
            if pyproject.is_file():
                with pyproject.open("rb") as f:
                    v = tomllib.load(f).get("project", {}).get("version")
                if v:
                    return v
    except Exception:
        pass

    # 2) 已安裝套件的 metadata(pip 由 pyproject 帶入)
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version("mcp-center")
        except PackageNotFoundError:
            pass
    except Exception:
        pass

    # 3) 最後退回,避免 crash
    return "0.0.0+unknown"


# 版本號 — 遵循 Semantic Versioning (MAJOR.MINOR.PATCH),來源 pyproject.toml
__version__ = _read_version()

# Build 資訊（由 CI/CD 或 Build Center 在編譯時寫入，預設為 dev）
__build_time__ = "dev"
__build_commit__ = "dev"
