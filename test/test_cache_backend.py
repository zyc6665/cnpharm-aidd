"""缓存原子操作测试。"""

import pytest

from app.cache.memory import MemoryCacheBackend


@pytest.mark.asyncio
async def test_memory_cache_supports_atomic_lock_operations():
    cache = MemoryCacheBackend()

    assert await cache.set("gpu:alloc:lock", "owner-a", nx=True, ex=10) is True
    assert await cache.set("gpu:alloc:lock", "owner-b", nx=True, ex=10) is False
    assert await cache.delete_if_value("gpu:alloc:lock", "owner-b") is False
    assert await cache.delete_if_value("gpu:alloc:lock", "owner-a") is True
    assert await cache.exists("gpu:alloc:lock") is False
