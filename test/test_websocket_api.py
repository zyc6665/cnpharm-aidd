import logging

import pytest
from fastapi import WebSocketDisconnect

from app.api.v1 import websocket as websocket_api
from app.models.users import User
from app.websocket.manager import WebSocketManager


class FakeWebSocket:
    def __init__(self):
        self.receive_count = 0
        self.closed = []

    async def close(self, *, code=None, reason=None):
        self.closed.append((code, reason))

    async def receive_text(self):
        self.receive_count += 1
        if self.receive_count == 1:
            return "{bad-json"
        raise WebSocketDisconnect()


class MessageWebSocket(FakeWebSocket):
    def __init__(self, message):
        super().__init__()
        self.message = message

    async def receive_text(self):
        self.receive_count += 1
        if self.receive_count == 1:
            return self.message
        raise WebSocketDisconnect()


class HeaderWebSocket(FakeWebSocket):
    def __init__(self, protocol_header):
        super().__init__()
        self.headers = {"sec-websocket-protocol": protocol_header}


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

    async def load_user(db, token):
        return User(id="user-1", role="user", status="active")

    async def allow_task(db, *, task_id, current_user):
        assert task_id == "task-1"
        assert current_user.id == "user-1"

    monkeypatch.setattr(websocket_api, "_load_authenticated_user", load_user)
    monkeypatch.setattr(websocket_api, "load_task_for_read_access", allow_task)

    await websocket_api.task_websocket_endpoint(
        websocket=FakeWebSocket(),
        task_id="task-1",
        token="access-token",
        db=object(),
    )

    assert manager.subscriptions == [("connection-1", "task-1")]
    assert manager.sent_messages == [
        ("connection-1", {"type": "error", "message": "无效的 JSON 格式"})
    ]
    assert manager.disconnected == ["connection-1"]


@pytest.mark.asyncio
async def test_task_websocket_rejects_anonymous_connection(monkeypatch):
    manager = FakeWebSocketManager()
    monkeypatch.setattr(websocket_api, "ws_manager", manager)
    websocket = FakeWebSocket()

    await websocket_api.task_websocket_endpoint(
        websocket=websocket,
        task_id="task-1",
        token=None,
        db=object(),
    )

    assert websocket.closed == [(1008, "需要有效的登录凭证")]
    assert manager.subscriptions == []


def test_websocket_auth_token_can_be_carried_in_subprotocol_header():
    websocket = HeaderWebSocket("scitool-access-token, access-token")

    assert websocket_api._resolve_ws_token(websocket, None) == "access-token"


@pytest.mark.asyncio
async def test_general_websocket_rejects_task_without_read_access(monkeypatch):
    manager = FakeWebSocketManager()
    monkeypatch.setattr(websocket_api, "ws_manager", manager)
    websocket = MessageWebSocket('{"action":"subscribe_task","task_id":"task-1"}')

    async def load_user(db, token):
        return User(id="user-1", role="user", status="active")

    async def deny_task(db, *, task_id, current_user):
        raise websocket_api.AppException("denied", code=403)

    monkeypatch.setattr(websocket_api, "_load_authenticated_user", load_user)
    monkeypatch.setattr(websocket_api, "load_task_for_read_access", deny_task)

    await websocket_api.websocket_endpoint(
        websocket=websocket,
        token="access-token",
        db=object(),
    )

    assert websocket.closed == [(1008, "无权订阅此任务")]
    assert manager.subscriptions == []
    assert manager.disconnected == ["connection-1"]


@pytest.mark.asyncio
async def test_task_progress_websocket_normalizes_percent_values(monkeypatch):
    """任务进度 WebSocket 应兼容状态机的 0-100 百分比。"""
    manager = WebSocketManager()
    sent_messages = []

    async def fake_broadcast(task_id, message):
        sent_messages.append((task_id, message))

    monkeypatch.setattr(manager, "broadcast_to_task", fake_broadcast)

    await manager.send_task_progress("task-1", 35.0, "远端运行中")

    assert sent_messages == [
        (
            "task-1",
            {
                "type": "task_progress",
                "progress": 0.35,
                "progress_percent": 35,
                "message": "远端运行中",
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_user_from_token_logs_decode_failure(monkeypatch, caplog):
    """WebSocket access token 解析失败时应拒绝并留下排障日志。"""

    def fail_verify(token, token_type):
        raise RuntimeError("bad token")

    monkeypatch.setattr(websocket_api, "verify_token", fail_verify)

    with caplog.at_level(logging.DEBUG, logger="app.api.v1.websocket"):
        assert await websocket_api.get_user_from_token("invalid-token") is None

    assert "Failed to decode WebSocket token: bad token" in caplog.text
