# backend/app/cache/factory.py
"""缓存后端工厂"""

from functools import lru_cache
from typing import Literal

from app.cache.base import CacheBackend
from app.config import settings


CacheType = Literal["memory", "redis"]


@lru_cache()
def get_cache_backend(backend_type: CacheType = None) -> CacheBackend:
    """
    获取缓存后端实例（单例）

    通过配置 CACHE_BACKEND 环境变量切换:
    - memory: 内存缓存（开发环境）
    - redis: Redis 缓存（生产环境）

    Args:
        backend_type: 缓存类型，默认从配置读取

    Returns:
        CacheBackend: 缓存后端实例
    """
    backend = backend_type or settings.CACHE_BACKEND

    if backend == "memory":
        from app.cache.memory import MemoryCacheBackend
        return MemoryCacheBackend()

    elif backend == "redis":
        from app.cache.redis_backend import RedisCacheBackend
        return RedisCacheBackend()

    else:
        raise ValueError(f"不支持的缓存后端: {backend}")


# 便捷访问
cache = get_cache_backend()
