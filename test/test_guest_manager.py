import json
import importlib
from datetime import datetime

import pytest

from app.auth.guest_manager import GuestManager, GuestSessionData, GuestSessionError


class InvalidJsonCache:
    async def get(self, key: str):
        return "{not-json"


class CapturingCache:
    def __init__(self):
        self.writes = []

    async def set(self, key: str, value: str, ttl: int):
        self.writes.append({"key": key, "value": value, "ttl": ttl})


def test_guest_manager_uses_cache_backend_factory(monkeypatch):
    """游客会话管理器应使用真实缓存工厂函数初始化缓存。"""
    cache = object()

    monkeypatch.setattr(
        "app.cache.factory.get_cache_backend",
        lambda: cache,
    )

    manager = GuestManager()

    assert manager.cache is cache


def test_guest_manager_logs_cache_factory_failure_once(monkeypatch, caplog):
    """缓存初始化失败时应一次性告警，而不是静默降级。"""
    def raise_cache_error():
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr("app.cache.factory.get_cache_backend", raise_cache_error)
    manager = GuestManager()

    with caplog.at_level("WARNING", logger="app.auth.guest_manager"):
        assert manager.cache is None
        assert manager.cache is None

    warnings = [
        record
        for record in caplog.records
        if "Guest session cache is unavailable" in record.message
    ]
    assert len(warnings) == 1


@pytest.mark.asyncio
async def test_invalid_cached_guest_session_is_observable(caplog):
    """游客会话缓存损坏时应记录告警，而不是静默吞掉。"""
    manager = GuestManager(cache=InvalidJsonCache())

    with caplog.at_level("WARNING", logger="app.auth.guest_manager"):
        with pytest.raises(GuestSessionError):
            await manager.validate_guest_session("guest-session-id")

    assert any(
        "Invalid cached guest session payload" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_guest_quota_daily_reset_uses_project_utcnow(monkeypatch):
    """游客每日配额重置应使用项目统一时间工具。"""
    cache = CapturingCache()
    manager = GuestManager(cache=cache)
    session_data = GuestSessionData(
        session_id="guest-session-id",
        created_at="2026-07-07T23:59:00",
        limitations={"daily_task_limit": 5},
        usage={
            "tasks_today": 3,
            "files_uploaded_today": 2,
            "usage_date": "2026-07-07",
        },
        expires_at="2026-07-09T00:00:00",
    )

    async def fake_validate_guest_session(session_id, db=None):
        assert session_id == "guest-session-id"
        return session_data

    guest_manager_module = importlib.import_module("app.auth.guest_manager")
    monkeypatch.setattr(
        guest_manager_module,
        "utcnow",
        lambda: datetime(2026, 7, 8, 0, 1, 0),
    )
    monkeypatch.setattr(manager, "validate_guest_session", fake_validate_guest_session)

    assert await manager.check_guest_quota("guest-session-id", "task") is True

    assert session_data.usage["tasks_today"] == 0
    assert session_data.usage["files_uploaded_today"] == 0
    assert session_data.usage["usage_date"] == "2026-07-08"
    assert len(cache.writes) == 1
    cached_payload = json.loads(cache.writes[0]["value"])
    assert cached_payload["usage"]["usage_date"] == "2026-07-08"
