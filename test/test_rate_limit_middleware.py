import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.cache.memory import MemoryCacheBackend
from app.main import app
from app.middleware.rate_limit import RateLimitMiddleware


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


def test_main_application_registers_rate_limit_middleware():
    """主应用必须启用全局限流，不能只保留未接入的实现。"""
    assert any(middleware.cls is RateLimitMiddleware for middleware in app.user_middleware)


@pytest.mark.asyncio
async def test_rate_limit_returns_429_after_configured_threshold():
    """同一客户端超过阈值时应收到标准 429 响应。"""
    rate_limited_app = FastAPI()
    rate_limited_app.add_middleware(
        RateLimitMiddleware,
        cache_client=MemoryCacheBackend(),
        requests_per_minute=2,
    )

    @rate_limited_app.get("/resource")
    async def resource():
        return {"ok": True}

    transport = ASGITransport(app=rate_limited_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.get("/resource")
        second = await client.get("/resource")
        limited = await client.get("/resource")

    assert first.status_code == 200
    assert second.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["X-RateLimit-Limit"] == "2"


@pytest.mark.asyncio
async def test_rate_limit_read_failure_is_observable(caplog):
    """限流缓存读取失败时应告警并安全放行。"""
    middleware = RateLimitMiddleware(
        dummy_app,
        cache_client=FailingCache(),
        requests_per_minute=60,
    )

    with caplog.at_level("WARNING", logger="app.middleware.rate_limit"):
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
