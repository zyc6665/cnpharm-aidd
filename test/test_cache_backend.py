"""缓存原子操作测试。"""

import asyncio

import pytest

from app.cache.memory import MemoryCacheBackend
from app.cache.redis_backend import RedisCacheBackend


class _LoopBoundRedisClient:
    """模拟 redis-py 连接池：首次命令绑定当前事件循环，换循环即报错。"""

    def __init__(self) -> None:
        self._loop = None

    def _ensure_current_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError("Event loop is closed")

    async def set(self, *args, **kwargs) -> bool:
        self._ensure_current_loop()
        return True

    async def close(self) -> None:
        return None

    async def aclose(self) -> None:
        return None


def test_redis_cache_backend_works_across_sequential_event_loops(monkeypatch):
    created_clients = []

    def _from_url(*args, **kwargs):
        client = _LoopBoundRedisClient()
        created_clients.append(client)
        return client

    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(redis_asyncio, "from_url", _from_url)

    cache = RedisCacheBackend(url="redis://localhost:6379/0")

    async def _write_once() -> None:
        assert await cache.set("loop-key", "value") is True

    asyncio.run(_write_once())
    asyncio.run(_write_once())

    assert len(created_clients) == 2


@pytest.mark.asyncio
async def test_memory_cache_supports_atomic_lock_operations():
    cache = MemoryCacheBackend()

    assert await cache.set("gpu:alloc:lock", "owner-a", nx=True, ex=10) is True
    assert await cache.set("gpu:alloc:lock", "owner-b", nx=True, ex=10) is False
    assert await cache.delete_if_value("gpu:alloc:lock", "owner-b") is False
    assert await cache.delete_if_value("gpu:alloc:lock", "owner-a") is True
    assert await cache.exists("gpu:alloc:lock") is False


@pytest.mark.asyncio
async def test_memory_cache_expire_if_value():
    cache = MemoryCacheBackend()
    await cache.set("lock", "owner-a", nx=True, ex=10)
    assert await cache.expire_if_value("lock", "owner-b", 20) is False
    assert await cache.expire_if_value("lock", "owner-a", 20) is True
