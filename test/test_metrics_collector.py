import pytest

from app.monitoring.metrics_collector import MetricsCollector


class FakeScalarResult:
    def __init__(self, value: int):
        self.value = value

    def scalar(self) -> int:
        return self.value


class FakeDbSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        return FakeScalarResult(3)


class FakeMetrics:
    def __init__(self):
        self.active_users = None

    def set_active_users(self, registered: int, guest: int) -> None:
        self.active_users = {"registered": registered, "guest": guest}


class FailingCache:
    async def keys(self, pattern: str):
        raise RuntimeError(f"cache unavailable for {pattern}")


class CapturingCache:
    def __init__(self):
        self.pattern = None

    async def keys(self, pattern: str):
        self.pattern = pattern
        return ["guest:one", "guest:two"]


def make_db_session():
    return FakeDbSession()


@pytest.mark.asyncio
async def test_user_metrics_logs_guest_cache_failures(caplog):
    metrics = FakeMetrics()
    collector = MetricsCollector(
        metrics=metrics,
        db_session_factory=make_db_session,
        cache_client=FailingCache(),
    )

    with caplog.at_level("WARNING", logger="app.monitoring.metrics_collector"):
        result = await collector._collect_user_metrics()

    assert result == {"active_registered": 3, "active_guests": 0}
    assert metrics.active_users == {"registered": 3, "guest": 0}
    assert any("Guest session metrics collection failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_user_metrics_counts_current_guest_cache_prefix():
    cache = CapturingCache()
    metrics = FakeMetrics()
    collector = MetricsCollector(
        metrics=metrics,
        db_session_factory=make_db_session,
        cache_client=cache,
    )

    result = await collector._collect_user_metrics()

    assert cache.pattern == "guest:*"
    assert result == {"active_registered": 3, "active_guests": 2}
    assert metrics.active_users == {"registered": 3, "guest": 2}
