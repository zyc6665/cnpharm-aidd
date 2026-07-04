import pytest

from app.auth.guest_manager import GuestManager, GuestSessionError


class InvalidJsonCache:
    async def get(self, key: str):
        return "{not-json"


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
