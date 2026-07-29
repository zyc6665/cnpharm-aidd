# backend/app/websocket/manager.py
"""WebSocket 连接管理器"""

import asyncio
from typing import Dict, Set, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from fastapi import WebSocket
from enum import Enum

import logging
from app.common.time import utcnow

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """WebSocket 消息类型"""
    # 任务相关
    TASK_STATUS = "task_status"
    TASK_PROGRESS = "task_progress"
    TASK_LOG = "task_log"
    TASK_COMPLETE = "task_complete"
    TASK_ERROR = "task_error"

    # 系统相关
    SYSTEM_NOTIFICATION = "system_notification"
    HEARTBEAT = "heartbeat"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class Connection:
    """WebSocket 连接信息"""
    websocket: WebSocket
    user_id: Optional[str] = None
    connected_at: datetime = field(default_factory=datetime.utcnow)
    subscriptions: Set[str] = field(default_factory=set)


class WebSocketManager:
    """
    WebSocket 连接管理器

    功能：
    - 管理所有 WebSocket 连接
    - 支持按用户、任务订阅消息
    - 广播消息到指定连接组
    - 心跳检测
    """

    def __init__(self):
        # 所有活跃连接: connection_id -> Connection
        self._connections: Dict[str, Connection] = {}
        # 用户连接映射: user_id -> Set[connection_id]
        self._user_connections: Dict[str, Set[str]] = {}
        # 任务订阅映射: task_id -> Set[connection_id]
        self._task_subscriptions: Dict[str, Set[str]] = {}
        # 连接计数器
        self._connection_counter = 0
        # 锁
        self._lock = asyncio.Lock()

    def _generate_connection_id(self) -> str:
        """生成连接 ID"""
        self._connection_counter += 1
        return f"conn_{self._connection_counter}_{utcnow().timestamp()}"

    async def connect(
        self,
        websocket: WebSocket,
        user_id: Optional[str] = None
    ) -> str:
        """
        接受新的 WebSocket 连接

        Args:
            websocket: WebSocket 连接对象
            user_id: 用户 ID（可选）

        Returns:
            连接 ID
        """
        await websocket.accept()

        async with self._lock:
            connection_id = self._generate_connection_id()
            connection = Connection(
                websocket=websocket,
                user_id=user_id
            )
            self._connections[connection_id] = connection

            # 建立用户映射
            if user_id:
                if user_id not in self._user_connections:
                    self._user_connections[user_id] = set()
                self._user_connections[user_id].add(connection_id)

            logger.info(f"WebSocket 连接建立: {connection_id}, 用户: {user_id}")

        # 发送连接成功消息
        await self.send_personal(connection_id, {
            "type": MessageType.CONNECTED.value,
            "connection_id": connection_id,
            "timestamp": utcnow().isoformat()
        })

        return connection_id

    async def disconnect(self, connection_id: str):
        """
        断开 WebSocket 连接

        Args:
            connection_id: 连接 ID
        """
        async with self._lock:
            if connection_id not in self._connections:
                return

            connection = self._connections[connection_id]

            # 移除用户映射
            if connection.user_id and connection.user_id in self._user_connections:
                self._user_connections[connection.user_id].discard(connection_id)
                if not self._user_connections[connection.user_id]:
                    del self._user_connections[connection.user_id]

            # 移除任务订阅
            for task_id in list(connection.subscriptions):
                if task_id in self._task_subscriptions:
                    self._task_subscriptions[task_id].discard(connection_id)
                    if not self._task_subscriptions[task_id]:
                        del self._task_subscriptions[task_id]

            # 移除连接
            del self._connections[connection_id]

            logger.info(f"WebSocket 连接断开: {connection_id}")

    async def subscribe_task(self, connection_id: str, task_id: str):
        """
        订阅任务更新

        Args:
            connection_id: 连接 ID
            task_id: 任务 ID
        """
        async with self._lock:
            if connection_id not in self._connections:
                return

            # 添加到连接的订阅列表
            self._connections[connection_id].subscriptions.add(task_id)

            # 添加到任务订阅映射
            if task_id not in self._task_subscriptions:
                self._task_subscriptions[task_id] = set()
            self._task_subscriptions[task_id].add(connection_id)

            logger.debug(f"连接 {connection_id} 订阅任务 {task_id}")

    async def unsubscribe_task(self, connection_id: str, task_id: str):
        """
        取消订阅任务更新

        Args:
            connection_id: 连接 ID
            task_id: 任务 ID
        """
        async with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id].subscriptions.discard(task_id)

            if task_id in self._task_subscriptions:
                self._task_subscriptions[task_id].discard(connection_id)
                if not self._task_subscriptions[task_id]:
                    del self._task_subscriptions[task_id]

    async def send_personal(self, connection_id: str, message: Dict[str, Any]):
        """
        发送消息到指定连接

        Args:
            connection_id: 连接 ID
            message: 消息内容
        """
        if connection_id not in self._connections:
            return

        try:
            websocket = self._connections[connection_id].websocket
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"发送消息失败: {connection_id}, 错误: {e}")
            await self.disconnect(connection_id)

    async def send_to_user(self, user_id: str, message: Dict[str, Any]):
        """
        发送消息到指定用户的所有连接

        Args:
            user_id: 用户 ID
            message: 消息内容
        """
        if user_id not in self._user_connections:
            return

        for connection_id in list(self._user_connections[user_id]):
            await self.send_personal(connection_id, message)

    async def broadcast_to_task(self, task_id: str, message: Dict[str, Any]):
        """
        广播消息到订阅指定任务的所有连接

        Args:
            task_id: 任务 ID
            message: 消息内容
        """
        if task_id not in self._task_subscriptions:
            return

        message["task_id"] = task_id
        message["timestamp"] = utcnow().isoformat()

        for connection_id in list(self._task_subscriptions[task_id]):
            await self.send_personal(connection_id, message)

    async def broadcast_all(self, message: Dict[str, Any]):
        """
        广播消息到所有连接

        Args:
            message: 消息内容
        """
        message["timestamp"] = utcnow().isoformat()

        for connection_id in list(self._connections.keys()):
            await self.send_personal(connection_id, message)

    # ==================== 任务相关便捷方法 ====================

    async def send_task_status(
        self,
        task_id: str,
        status: str,
        message: Optional[str] = None
    ):
        """发送任务状态更新"""
        await self.broadcast_to_task(task_id, {
            "type": MessageType.TASK_STATUS.value,
            "status": status,
            "message": message
        })

    async def send_task_progress(
        self,
        task_id: str,
        progress: float,
        message: Optional[str] = None
    ):
        """
        发送任务进度更新

        Args:
            task_id: 任务 ID
            progress: 进度 (0.0 - 1.0)
            message: 进度消息
        """
        await self.broadcast_to_task(task_id, {
            "type": MessageType.TASK_PROGRESS.value,
            "progress": progress,
            "progress_percent": int(progress * 100),
            "message": message
        })

    async def send_task_log(
        self,
        task_id: str,
        level: str,
        log_message: str
    ):
        """发送任务日志"""
        await self.broadcast_to_task(task_id, {
            "type": MessageType.TASK_LOG.value,
            "level": level,
            "log": log_message
        })

    async def send_task_complete(
        self,
        task_id: str,
        result: Optional[Dict[str, Any]] = None
    ):
        """发送任务完成通知"""
        await self.broadcast_to_task(task_id, {
            "type": MessageType.TASK_COMPLETE.value,
            "result": result
        })

    async def send_task_error(
        self,
        task_id: str,
        error: str
    ):
        """发送任务错误通知"""
        await self.broadcast_to_task(task_id, {
            "type": MessageType.TASK_ERROR.value,
            "error": error
        })

    # ==================== 统计信息 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        return {
            "total_connections": len(self._connections),
            "total_users": len(self._user_connections),
            "total_task_subscriptions": len(self._task_subscriptions),
            "connections_by_user": {
                user_id: len(conns)
                for user_id, conns in self._user_connections.items()
            }
        }

    def get_connection_count(self) -> int:
        """获取当前连接数"""
        return len(self._connections)


# 全局 WebSocket 管理器实例
ws_manager = WebSocketManager()
