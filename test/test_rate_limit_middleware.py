import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.cache.memory import MemoryCacheBackend
from app.main import app
from app.middleware.rate_limit import RateLimitMiddleware


class FailingCache:
    async def get(self, key: str):
        raise RuntimeError(f"cache unavailable for {key}")

    async def incr(self, key: str):
        raise RuntimeError(f"cache unavailable for {key}")

    async def expire(self, key: str, seconds: int):
        raise RuntimeError(f"cache unavailable for {key}")


class RedisLikeCounter:
    """模拟 Redis 中共享的计数器语义（get/incr/expire）。"""

    def __init__(self):
        self.counters = {}
        self.expirations = {}

    async def get(self, key: str):
        return self.counters.get(key)

    async def incr(self, key: str):
        self.counters[key] = int(self.counters.get(key, 0)) + 1
        return self.counters[key]

    async def expire(self, key: str, seconds: int):
        self.expirations[key] = seconds
        return True


def _limited_app(middleware_kwargs) -> FastAPI:
    rate_limited_app = FastAPI()
    rate_limited_app.add_middleware(RateLimitMiddleware, **middleware_kwargs)

    @rate_limited_app.get("/resource")
    async def resource():
        return {"ok": True}

    return rate_limited_app


def test_main_application_registers_rate_limit_middleware():
    """主应用必须启用全局限流，不能只保留未接入的实现。"""
    assert any(middleware.cls is RateLimitMiddleware for middleware in app.user_middleware)


@pytest.mark.asyncio
async def test_rate_limit_returns_429_after_configured_threshold():
    """同一客户端超过阈值时应收到标准 429 响应。"""
    rate_limited_app = _limited_app(
        {
            "cache_client": MemoryCacheBackend(),
            "requests_per_minute": 2,
        }
    )

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
async def test_redis_like_backend_counts_across_middleware_instances():
    """Redis 计数后端被多个中间件实例共享时，阈值应全局生效。"""
    shared_redis = RedisLikeCounter()

    first_app = _limited_app(
        {
            "cache_client": MemoryCacheBackend(),
            "requests_per_minute": 2,
            "backend": "redis",
            "redis_cache_client": shared_redis,
        }
    )
    second_app = _limited_app(
        {
            "cache_client": MemoryCacheBackend(),
            "requests_per_minute": 2,
            "backend": "redis",
            "redis_cache_client": shared_redis,
        }
    )

    async with AsyncClient(
        transport=ASGITransport(app=first_app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/resource")).status_code == 200
        assert (await client.get("/resource")).status_code == 200

    async with AsyncClient(
        transport=ASGITransport(app=second_app), base_url="http://testserver"
    ) as client:
        limited = await client.get("/resource")

    assert limited.status_code == 429
    assert shared_redis.expirations


@pytest.mark.asyncio
async def test_rate_limit_backend_failure_is_fail_closed_by_default():
    """生产口径：计数后端不可用时拒绝请求（503），不能静默放行。"""
    rate_limited_app = _limited_app(
        {
            "cache_client": FailingCache(),
            "requests_per_minute": 60,
            "fail_mode": "closed",
        }
    )

    async with AsyncClient(
        transport=ASGITransport(app=rate_limited_app), base_url="http://testserver"
    ) as client:
        response = await client.get("/resource")

    assert response.status_code == 503
    assert response.json()["code"] == 50301


@pytest.mark.asyncio
async def test_rate_limit_backend_failure_can_fail_open_in_development(caplog):
    """开发环境显式配置后可 fail-open，但仍必须留下告警。"""
    rate_limited_app = _limited_app(
        {
            "cache_client": FailingCache(),
            "requests_per_minute": 60,
            "fail_mode": "open",
        }
    )

    with caplog.at_level("WARNING", logger="app.middleware.rate_limit"):
        async with AsyncClient(
            transport=ASGITransport(app=rate_limited_app), base_url="http://testserver"
        ) as client:
            response = await client.get("/resource")

    assert response.status_code == 200
    assert any(
        "failing open" in record.message for record in caplog.records
    )


@pytest.mark.asyncio
async def test_health_paths_remain_exempt_from_rate_limiting():
    """P1-4 口径：探针健康检查路径不被限流误伤。"""
    rate_limited_app = _limited_app(
        {
            "cache_client": FailingCache(),
            "requests_per_minute": 0,
            "fail_mode": "closed",
        }
    )

    @rate_limited_app.get("/health")
    async def health():
        return {"status": "healthy"}

    async with AsyncClient(
        transport=ASGITransport(app=rate_limited_app), base_url="http://testserver"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
