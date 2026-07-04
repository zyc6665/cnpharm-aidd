import pytest
from fastapi import WebSocketDisconnect

from app.api.v1 import websocket as websocket_api


class FakeWebSocket:
    def __init__(self):
        self.receive_count = 0

    async def receive_text(self):
        self.receive_count += 1
        if self.receive_count == 1:
            return "{bad-json"
        raise WebSocketDisconnect()


class FakeWebSocketManager:
    def __init__(self):
        self.subscriptions = []
        self.sent_messages = []
        self.disconnected = []

    async def connect(self, websocket, user_id):
        return "connection-1"

    async def subscribe_task(self, connection_id, task_id):
        self.subscriptions.append((connection_id, task_id))

    async def send_personal(self, connection_id, message):
        self.sent_messages.append((connection_id, message))

    async def disconnect(self, connection_id):
        self.disconnected.append(connection_id)


@pytest.mark.asyncio
async def test_task_websocket_reports_invalid_json(monkeypatch):
    """任务 WebSocket 收到非法 JSON 时应显式返回错误。"""
    manager = FakeWebSocketManager()
    monkeypatch.setattr(websocket_api, "ws_manager", manager)

    await websocket_api.task_websocket_endpoint(
        websocket=FakeWebSocket(),
        task_id="task-1",
        token=None,
    )

    assert manager.subscriptions == [("connection-1", "task-1")]
    assert manager.sent_messages == [
        ("connection-1", {"type": "error", "message": "无效的 JSON 格式"})
    ]
    assert manager.disconnected == ["connection-1"]
