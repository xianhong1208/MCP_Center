"""WebSocket 連線管理

功能：
- 管理 WebSocket 連線
- 廣播健康狀態變更
- 廣播服務新增/移除事件
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Set, Optional, Any, Dict

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WSMessageType(str, Enum):
    """WebSocket 訊息類型"""
    HEALTH_UPDATE = "health_update"
    SERVICE_ADDED = "service_added"
    SERVICE_REMOVED = "service_removed"
    SERVICE_UPDATED = "service_updated"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"


@dataclass
class WSMessage:
    """WebSocket 訊息"""
    type: WSMessageType
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_json(self) -> str:
        """轉換為 JSON 字串"""
        d = asdict(self)
        d["type"] = self.type.value
        return json.dumps(d)


class WSManager:
    """WebSocket 連線管理器

    管理所有 WebSocket 連線，提供廣播功能。
    """

    def __init__(self):
        """初始化 WebSocket 管理器"""
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def connection_count(self) -> int:
        """取得連線數量"""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """接受新的 WebSocket 連線

        Args:
            websocket: WebSocket 連線
        """
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {self.connection_count}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """移除 WebSocket 連線

        Args:
            websocket: WebSocket 連線
        """
        async with self._lock:
            self._connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {self.connection_count}")

    async def broadcast(self, message: WSMessage) -> int:
        """廣播訊息到所有連線

        Args:
            message: WSMessage 訊息

        Returns:
            成功發送的連線數
        """
        if not self._connections:
            return 0

        message_json = message.to_json()
        sent_count = 0
        failed_connections = []

        async with self._lock:
            connections = list(self._connections)

        for websocket in connections:
            try:
                await websocket.send_text(message_json)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send message to WebSocket: {e}")
                failed_connections.append(websocket)

        # 移除失敗的連線
        if failed_connections:
            async with self._lock:
                for ws in failed_connections:
                    self._connections.discard(ws)

        return sent_count

    async def broadcast_health_update(
        self,
        service_id: str,
        service_name: str,
        health: Dict[str, Any]
    ) -> int:
        """廣播健康狀態更新

        Args:
            service_id: 服務 ID
            service_name: 服務名稱
            health: 健康狀態資料

        Returns:
            成功發送的連線數
        """
        message = WSMessage(
            type=WSMessageType.HEALTH_UPDATE,
            service_id=service_id,
            service_name=service_name,
            data=health
        )
        return await self.broadcast(message)

    async def broadcast_service_added(
        self,
        service_id: str,
        service_name: str,
        service_data: Optional[Dict[str, Any]] = None
    ) -> int:
        """廣播服務新增事件

        Args:
            service_id: 服務 ID
            service_name: 服務名稱
            service_data: 服務資料 (可選)

        Returns:
            成功發送的連線數
        """
        message = WSMessage(
            type=WSMessageType.SERVICE_ADDED,
            service_id=service_id,
            service_name=service_name,
            data=service_data
        )
        return await self.broadcast(message)

    async def broadcast_service_removed(
        self,
        service_id: str,
        service_name: str
    ) -> int:
        """廣播服務移除事件

        Args:
            service_id: 服務 ID
            service_name: 服務名稱

        Returns:
            成功發送的連線數
        """
        message = WSMessage(
            type=WSMessageType.SERVICE_REMOVED,
            service_id=service_id,
            service_name=service_name
        )
        return await self.broadcast(message)

    async def broadcast_service_updated(
        self,
        service_id: str,
        service_name: str,
        service_data: Optional[Dict[str, Any]] = None
    ) -> int:
        """廣播服務更新事件

        Args:
            service_id: 服務 ID
            service_name: 服務名稱
            service_data: 更新後的服務資料 (可選)

        Returns:
            成功發送的連線數
        """
        message = WSMessage(
            type=WSMessageType.SERVICE_UPDATED,
            service_id=service_id,
            service_name=service_name,
            data=service_data
        )
        return await self.broadcast(message)

    async def send_to(self, websocket: WebSocket, message: WSMessage) -> bool:
        """發送訊息到特定連線

        Args:
            websocket: 目標 WebSocket 連線
            message: WSMessage 訊息

        Returns:
            是否發送成功
        """
        try:
            await websocket.send_text(message.to_json())
            return True
        except Exception as e:
            logger.warning(f"Failed to send message: {e}")
            return False

    async def handle_connection(self, websocket: WebSocket) -> None:
        """處理 WebSocket 連線的完整生命週期

        這是一個便捷方法，處理連線、接收訊息、斷線等。

        Args:
            websocket: WebSocket 連線
        """
        await self.connect(websocket)
        try:
            while True:
                # 接收訊息
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    msg_type = msg.get("type")

                    # 處理 ping
                    if msg_type == "ping":
                        await self.send_to(
                            websocket,
                            WSMessage(type=WSMessageType.PONG)
                        )
                except json.JSONDecodeError:
                    await self.send_to(
                        websocket,
                        WSMessage(
                            type=WSMessageType.ERROR,
                            data={"message": "Invalid JSON"}
                        )
                    )

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            await self.disconnect(websocket)


# 全域 WebSocket manager instance
_ws_manager: Optional[WSManager] = None


def get_ws_manager() -> WSManager:
    """取得 WSManager singleton instance"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WSManager()
    return _ws_manager
