# backend/app/cache/__init__.py
"""缓存适配层 - 支持内存缓存和 Redis"""

from app.cache.base import CacheBackend
from app.cache.factory import get_cache_backend

__all__ = ["CacheBackend", "get_cache_backend"]
