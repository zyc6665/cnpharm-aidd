import pytest

from app.middleware.auth_middleware import RateLimitMiddleware


class FailingCache:
    async def get(self, key: str):
        raise RuntimeError(f"cache unavailable for {key}")


class CountCache:
    def __init__(self, count):
        self.count = count

    async def get(self, key: str):
        return self.count


async def dummy_app(scope, receive, send):
    return None


@pytest.mark.asyncio
async def test_rate_limit_read_failure_is_observable(caplog):
    """限流缓存读取失败时应告警并安全放行。"""
    middleware = RateLimitMiddleware(
        dummy_app,
        cache_client=FailingCache(),
        requests_per_minute=60,
    )

    with caplog.at_level("WARNING", logger="app.middleware.auth_middleware"):
        assert await middleware._is_rate_limited("rate_limit:ip:127.0.0.1") is False

    assert any(
        "Failed to read rate limit counter" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_rate_limit_detects_over_limit_counter():
    """限流缓存计数达到阈值时应判定为超限。"""
    middleware = RateLimitMiddleware(
        dummy_app,
        cache_client=CountCache("60"),
        requests_per_minute=60,
    )

    assert await middleware._is_rate_limited("rate_limit:ip:127.0.0.1") is True
