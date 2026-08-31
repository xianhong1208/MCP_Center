"""SPA 靜態資源快取策略

背景(實際踩到):index.html 沒帶 Cache-Control → 瀏覽器啟發式快取 → 部署後
使用者拿舊 index 去載已被新 build 刪除的舊 bundle → 整頁空白,直到硬重新整理。

策略:
  - index.html(無 hash,每次 build 內容改變)→ no-cache(每次以 ETag 條件請求驗證)
  - /assets/*(檔名含內容 hash,永不變)→ immutable 長期快取

注意:pytest 下 main.STATIC_DIR 依啟動程式推導會指到錯的位置(共用 client fixture
沒有掛載前端),因此這裡自建 app 並把 STATIC_DIR 指向 repo 內真實的 static/web。
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REAL_STATIC = Path(__file__).resolve().parent.parent / "static" / "web"


@pytest.fixture
def spa_client(client, monkeypatch):
    """沿用 client fixture 完成的 DB/config 設定,另建一個有掛前端的 app。"""
    if not (REAL_STATIC / "index.html").exists():
        pytest.skip("前端尚未 build(static/web/index.html 不存在)")
    import main
    monkeypatch.setattr(main, "STATIC_DIR", REAL_STATIC)
    app = main.create_app()
    with TestClient(app) as c:
        yield c


class TestIndexHtmlCaching:
    @pytest.mark.parametrize("path", ["/", "/services", "/marketplace", "/tokens", "/consent"])
    def test_index_is_no_cache(self, spa_client, path):
        resp = spa_client.get(path)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert resp.headers.get("cache-control") == "no-cache"
        # 仍要有 ETag,讓 no-cache 走廉價的 304 條件請求
        assert resp.headers.get("etag")

    def test_index_revalidates_with_etag(self, spa_client):
        first = spa_client.get("/")
        etag = first.headers["etag"]
        again = spa_client.get("/", headers={"If-None-Match": etag})
        assert again.status_code == 304

    def test_api_prefix_is_not_swallowed_by_spa(self, spa_client):
        resp = spa_client.get("/api/definitely-not-a-route")
        assert resp.status_code in (401, 404)
        assert "text/html" not in resp.headers.get("content-type", "")


class TestHashedAssetsCaching:
    def test_hashed_asset_is_immutable(self, spa_client):
        js = sorted((REAL_STATIC / "assets").glob("index-*.js"))
        assert js, "build 產物應存在"
        resp = spa_client.get(f"/assets/{js[0].name}")
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "public, max-age=31536000, immutable"
