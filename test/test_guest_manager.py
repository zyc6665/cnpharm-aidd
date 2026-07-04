import pytest

from app.auth.guest_manager import GuestManager, GuestSessionError


class InvalidJsonCache:
    async def get(self, key: str):
        return "{not-json"


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
