# backend/app/cache/base.py
"""缓存后端抽象基类"""

from abc import ABC, abstractmethod
from typing import Optional, Any, List
import json


class CacheBackend(ABC):
    """缓存后端抽象基类"""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在返回 None
        """
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None,
        *,
        nx: bool = False,
        ex: Optional[int] = None,
    ) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            expire: 过期时间（秒）

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def delete_if_value(self, key: str, value: Any) -> bool:
        """仅当缓存值匹配时删除键。"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        删除缓存

        Args:
            key: 缓存键

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        检查缓存是否存在

        Args:
            key: 缓存键

        Returns:
            是否存在
        """
        pass

    @abstractmethod
    async def expire(self, key: str, seconds: int) -> bool:
        """
        设置过期时间

        Args:
            key: 缓存键
            seconds: 过期秒数

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def ttl(self, key: str) -> int:
        """
        获取剩余过期时间

        Args:
            key: 缓存键

        Returns:
            剩余秒数，-1 表示永不过期，-2 表示不存在
        """
        pass

    @abstractmethod
    async def incr(self, key: str, amount: int = 1) -> int:
        """
        自增

        Args:
            key: 缓存键
            amount: 增量

        Returns:
            增后的值
        """
        pass

    @abstractmethod
    async def decr(self, key: str, amount: int = 1) -> int:
        """
        自减

        Args:
            key: 缓存键
            amount: 减量

        Returns:
            减后的值
        """
        pass

    @abstractmethod
    async def keys(self, pattern: str = "*") -> List[str]:
        """
        获取匹配的键列表

        Args:
            pattern: 匹配模式

        Returns:
            键列表
        """
        pass

    @abstractmethod
    async def clear(self) -> bool:
        """
        清空所有缓存

        Returns:
            是否成功
        """
        pass

    # ========== 便捷方法 ==========

    async def get_json(self, key: str) -> Optional[Any]:
        """获取 JSON 缓存"""
        value = await self.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return value

    async def set_json(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None
    ) -> bool:
        """设置 JSON 缓存"""
        json_str = json.dumps(value, ensure_ascii=False)
        return await self.set(key, json_str, expire)

    async def get_or_set(
        self,
        key: str,
        default_factory,
        expire: Optional[int] = None
    ) -> Any:
        """
        获取缓存，不存在则设置默认值

        Args:
            key: 缓存键
            default_factory: 默认值工厂函数
            expire: 过期时间

        Returns:
            缓存值
        """
        value = await self.get(key)
        if value is None:
            value = default_factory() if callable(default_factory) else default_factory
            await self.set(key, value, expire)
        return value
