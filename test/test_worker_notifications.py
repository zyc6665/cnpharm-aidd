import pytest

from app.worker import tasks as worker_tasks


class FakeWebSocketManager:
    def __init__(self):
        self.calls = []

    async def send_task_status(self, task_id, status, message):
        self.calls.append(("status", task_id, status, message))

    async def send_task_error(self, task_id, error):
        raise RuntimeError(f"failed: {task_id}:{error}")


@pytest.mark.asyncio
async def test_worker_websocket_notification_delegates(monkeypatch):
    manager = FakeWebSocketManager()
    monkeypatch.setattr("app.websocket.ws_manager", manager)

    await worker_tasks.notify_task_status("task-1", "running", "started")

    assert manager.calls == [("status", "task-1", "running", "started")]


@pytest.mark.asyncio
async def test_worker_websocket_notification_failure_is_non_blocking(monkeypatch):
    manager = FakeWebSocketManager()
    monkeypatch.setattr("app.websocket.ws_manager", manager)

    await worker_tasks.notify_task_error("task-1", "boom")
