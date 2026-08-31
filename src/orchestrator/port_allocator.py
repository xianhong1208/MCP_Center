"""Port allocator for Managed MCP bridges

分配一個可用的 TCP port 給 supergateway bridge subprocess。規則:
  1. 掃預設範圍 (3457 開頭的 500 個 port),跳過 DB 中已被其他 Managed
     Process 佔用的 port,跳過當下 host 系統中已 listen 的 port
  2. 找到第一個雙重檢查通過的 port 就分配
  3. 若整個範圍都沒空位,raise PortAllocationError

設計考量:
  - 不支援手動指定 port(MVP 階段;未來要加廠商自訂只需擴充 allocate()
    accept 一個 preferred_port 參數)
  - 雙重檢查(DB + socket bind)是為了避免 race condition:單靠 DB 可能
    分到正在被別的 process 使用但還沒寫進 DB 的 port;單靠 bind test 可
    能分到 DB 中已預留但容器還沒起的 port
"""

from __future__ import annotations

import socket
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from db.models import ManagedMcpProcess


class PortAllocationError(Exception):
    """找不到可用 port"""


class PortAllocator:
    """範圍內分配 TCP port

    預設範圍 3457 開始、共 500 個 port(即 3457-3956)— 對單一廠商環境
    遠遠足夠。若日後要擴展,改 __init__ 參數即可。
    """

    def __init__(self, start_port: int = 3457, range_size: int = 500):
        if start_port < 1024:
            raise ValueError("start_port must be >= 1024")
        if range_size <= 0:
            raise ValueError("range_size must be positive")
        self.start_port = start_port
        self.range_size = range_size

    def _port_range(self) -> Iterable[int]:
        return range(self.start_port, self.start_port + self.range_size)

    @staticmethod
    def _is_port_listening(port: int) -> bool:
        """檢查 127.0.0.1:<port> 是否已被其他 process listen"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return False
            except OSError:
                return True

    @staticmethod
    def _db_used_ports(db: Session) -> set:
        """DB 中已分配(非 NULL port)的 Managed Process ports"""
        rows = db.query(ManagedMcpProcess.port).filter(
            ManagedMcpProcess.port.isnot(None)
        ).all()
        return {r[0] for r in rows if r[0] is not None}

    def allocate(self, db: Session, exclude_process_id: Optional[str] = None) -> int:
        """回傳一個可用 port

        Args:
            db: SQLAlchemy session
            exclude_process_id: 若重新分配給某個既有 process,把它既有的
                port 視為可用(才能「保留原 port 重新啟動」)
        """
        used = self._db_used_ports(db)
        if exclude_process_id:
            own = db.query(ManagedMcpProcess.port).filter(
                ManagedMcpProcess.id == exclude_process_id
            ).first()
            if own and own[0] is not None:
                used.discard(own[0])

        for port in self._port_range():
            if port in used:
                continue
            if self._is_port_listening(port):
                continue
            return port

        raise PortAllocationError(
            f"No free port in range {self.start_port}-"
            f"{self.start_port + self.range_size - 1}"
        )
