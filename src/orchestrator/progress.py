"""長時間操作的進度登錄簿(process 內、thread-safe)

部署 / 啟動 / 停止 / 載入 image 都是數十秒到數分鐘的操作,而 HTTP 回應要等
整件事做完才回。若前端只看到一顆轉圈,使用者分不出「還在下載套件」和「已經卡死」。

設計:
  - 操作方(orchestrator / routes)在每個階段呼叫 stage(key, name),做完 end(key)。
  - 讀取方(GET /auth/managed/progress)拿 snapshot(),前端輪詢後把階段翻成文字。
  - key 慣例:process:<process_id>(啟停部署)、catalog:<catalog_id>(載入 image)。
  - 純記憶體:MCP Center 是單一 process(Nuitka onefile),不需要跨節點;
    重啟後進度自然消失,與 container 實際狀態由 DB 對齊,無一致性問題。
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional


class ProgressRegistry:
    """thread-safe 的進度表。所有方法皆可在任意 thread 呼叫。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: Dict[str, dict] = {}

    def begin(self, key: str, kind: str, stage: str = "queued") -> None:
        now = time.time()
        with self._lock:
            self._items[key] = {
                "key": key,
                "kind": kind,
                "stage": stage,
                "detail": None,
                "started_at": now,
                "updated_at": now,
            }

    def stage(self, key: str, stage: str, detail: Optional[str] = None) -> None:
        """更新階段。key 尚未 begin 時視為 begin(kind 由 key 前綴推得),
        讓 orchestrator 不必知道自己是被誰呼叫的。"""
        now = time.time()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                kind = key.split(":", 1)[0] if ":" in key else "unknown"
                item = {"key": key, "kind": kind, "started_at": now}
                self._items[key] = item
            item["stage"] = stage
            item["detail"] = detail
            item["updated_at"] = now

    def end(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            item = self._items.get(key)
            return dict(item) if item else None

    def snapshot(self) -> List[dict]:
        with self._lock:
            return sorted((dict(v) for v in self._items.values()), key=lambda i: i["started_at"])

    @contextmanager
    def track(self, key: str, kind: str, stage: str = "queued") -> Iterator[None]:
        """with 區塊:進入即 begin,離開(含例外)必 end —— 失敗的操作不會留下殭屍進度。"""
        self.begin(key, kind, stage)
        try:
            yield
        finally:
            self.end(key)


_registry = ProgressRegistry()


def get_progress_registry() -> ProgressRegistry:
    return _registry


def process_key(process_id: str) -> str:
    return f"process:{process_id}"


def catalog_key(catalog_id: str) -> str:
    return f"catalog:{catalog_id}"
