# backend/app/cache/__init__.py
"""缓存适配层 - 支持内存缓存和 Redis"""

from app.cache.base import CacheBackend
from app.cache.factory import get_cache_backend, cache

__all__ = ["CacheBackend", "get_cache_backend", "cache"]


def get_cache() -> CacheBackend:
    """获取缓存实例（便捷函数）"""
    return get_cache_backend()
