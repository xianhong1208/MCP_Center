"""db_bootstrap 的 dbname 驗證測試

背景:SAST 對 db_bootstrap.py 的 CREATE DATABASE 報 Second-Order SQL
Injection。該 SQL 本身是安全的(psycopg2 `sql.Identifier`,dbname 全程是
Identifier 物件,無字串串接),但我們仍在來源端加白名單:

  1. 讓 config → SQL 這條路徑上有明確的 sanitizer。
  2. 擋掉打錯的 DATABASE_URL —— 尤其超長名字會被 Postgres 靜默截斷成 63
     bytes,導致「建出來的 DB 名」和「後續連線用的名」不一致。
"""
import pytest

from src.utils.db_bootstrap import (
    _MAX_IDENTIFIER_BYTES,
    _parse_db_url,
    _validate_dbname,
)


@pytest.mark.parametrize(
    "dbname",
    ["mcp_center", "postgres", "mcp-center", "db$1", "_internal", "a"],
)
def test_valid_dbnames_accepted(dbname):
    assert _validate_dbname(dbname) == dbname


@pytest.mark.parametrize(
    "dbname",
    [
        pytest.param('mydb"; DROP DATABASE postgres; --', id="quote-escape"),
        pytest.param('a" WITH OWNER "evil', id="owner-injection"),
        pytest.param("mydb; DROP TABLE x", id="statement-separator"),
        pytest.param("has space", id="space"),
        pytest.param("1startswithdigit", id="leading-digit"),
        pytest.param("postgresql://u:p@h/db", id="whole-url-as-dbname"),
        pytest.param("db\n", id="trailing-newline"),
        pytest.param("", id="empty"),
    ],
)
def test_invalid_dbnames_rejected(dbname):
    with pytest.raises(ValueError):
        _validate_dbname(dbname)


def test_oversized_dbname_rejected():
    """超過 63 bytes 會被 Postgres 靜默截斷 — 必須先擋住"""
    assert _validate_dbname("a" * _MAX_IDENTIFIER_BYTES)
    with pytest.raises(ValueError, match="超過"):
        _validate_dbname("a" * (_MAX_IDENTIFIER_BYTES + 1))


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:password@localhost:5432/mcp_center",
        "postgresql://mcp_center:pwd@localhost:5432/mcp_center",
        "postgresql://user:password@db:5432/mcp_center",
    ],
)
def test_readme_urls_parse_and_validate(url):
    """README / docs 裡的所有 DATABASE_URL 範例都必須通過"""
    dbname = _parse_db_url(url)["dbname"]
    assert _validate_dbname(dbname) == "mcp_center"
