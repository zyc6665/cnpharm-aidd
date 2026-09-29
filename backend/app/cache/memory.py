# backend/app/cache/memory.py
"""内存缓存后端"""

import asyncio
import fnmatch
from typing import Optional, Any, List, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.common.time import utcnow
from app.cache.base import CacheBackend


@dataclass
class CacheEntry:
    """缓存条目"""
    value: Any
    expires_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return utcnow() > self.expires_at


class MemoryCacheBackend(CacheBackend):
    """
    内存缓存后端

    适用于开发环境和单实例部署。
    注意：进程重启后缓存丢失，多实例部署时缓存不共享。
    """

    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def _cleanup_expired(self):
        """清理过期缓存"""
        now = utcnow()
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.expires_at and entry.expires_at < now
        ]
        for key in expired_keys:
            del self._cache[key]

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._cache[key]
                return None
            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None,
        *,
        nx: bool = False,
        ex: Optional[int] = None,
    ) -> bool:
        """设置缓存值"""
        async with self._lock:
            existing = self._cache.get(key)
            if existing is not None and existing.is_expired():
                del self._cache[key]
                existing = None
            if nx and existing is not None:
                return False

            expires_at = None
            ttl = ex if ex is not None else expire
            if ttl:
                expires_at = utcnow() + timedelta(seconds=ttl)

            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

            # 定期清理过期缓存
            if len(self._cache) % 100 == 0:
                await self._cleanup_expired()

            return True

    async def delete_if_value(self, key: str, value: Any) -> bool:
        """仅当缓存值匹配时删除键。"""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                return False
            if entry.value != value:
                return False
            del self._cache[key]
            return True

    async def set_if_exists(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None,
    ) -> bool:
        """仅当键仍存在时更新值和过期时间。"""
        async with self._lock:
            existing = self._cache.get(key)
            if existing is None or existing.is_expired():
                if existing is not None:
                    del self._cache[key]
                return False
            expires_at = None
            if expire:
                expires_at = utcnow() + timedelta(seconds=expire)
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
            return True

    async def expire_if_value(self, key: str, value: Any, seconds: int) -> bool:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None or entry.is_expired() or entry.value != value:
                return False
            entry.expires_at = utcnow() + timedelta(seconds=max(int(seconds), 1))
            return True

    async def delete(self, key: str) -> bool:
        """删除缓存"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                return False
            return True

    async def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间"""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            entry.expires_at = utcnow() + timedelta(seconds=seconds)
            return True

    async def ttl(self, key: str) -> int:
        """获取剩余过期时间"""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return -2
            if entry.expires_at is None:
                return -1
            remaining = (entry.expires_at - utcnow()).total_seconds()
            return max(0, int(remaining))

    async def incr(self, key: str, amount: int = 1) -> int:
        """自增"""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._cache[key] = CacheEntry(value=amount)
                return amount
            if entry.is_expired():
                self._cache[key] = CacheEntry(value=amount)
                return amount
            entry.value = int(entry.value) + amount
            return entry.value

    async def decr(self, key: str, amount: int = 1) -> int:
        """自减"""
        return await self.incr(key, -amount)

    async def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配的键列表"""
        async with self._lock:
            await self._cleanup_expired()
            return [
                key for key in self._cache.keys()
                if fnmatch.fnmatch(key, pattern)
            ]

    async def clear(self) -> bool:
        """清空所有缓存"""
        async with self._lock:
            self._cache.clear()
            return True
