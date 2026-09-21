# backend/app/cache/redis_backend.py
"""Redis 缓存后端"""

from typing import Optional, Any, List
import json

from app.cache.base import CacheBackend
from app.config import settings


class RedisCacheBackend(CacheBackend):
    """
    Redis 缓存后端

    适用于生产环境，支持多实例部署。
    """

    def __init__(
        self,
        url: Optional[str] = None,
        prefix: str = "scitool:"
    ):
        # 延迟导入，避免未安装 redis 时报错
        try:
            import redis.asyncio as redis
        except ImportError:
            raise ImportError("请安装 redis: pip install redis")

        self.url = url or settings.REDIS_URL
        self.prefix = prefix
        self._redis = redis.from_url(
            self.url,
            encoding="utf-8",
            decode_responses=True
        )

    def _make_key(self, key: str) -> str:
        """添加前缀"""
        return f"{self.prefix}{key}"

    def _strip_prefix(self, key: str) -> str:
        """移除前缀"""
        if key.startswith(self.prefix):
            return key[len(self.prefix):]
        return key

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        value = await self._redis.get(self._make_key(key))
        if value is None:
            return None
        # 尝试 JSON 解析
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

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
        # 自动 JSON 序列化
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)

        ttl = ex if ex is not None else expire
        result = await self._redis.set(
            self._make_key(key),
            value,
            ex=ttl if ttl else None,
            nx=nx,
        )
        return bool(result)

    async def delete_if_value(self, key: str, value: Any) -> bool:
        """仅当 Redis 中的缓存值匹配时原子删除。"""
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] "
            "then return redis.call('del', KEYS[1]) else return 0 end"
        )
        result = await self._redis.eval(
            script,
            1,
            self._make_key(key),
            str(value),
        )
        return result == 1

    async def delete(self, key: str) -> bool:
        """删除缓存"""
        result = await self._redis.delete(self._make_key(key))
        return result > 0

    async def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        result = await self._redis.exists(self._make_key(key))
        return result > 0

    async def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间"""
        result = await self._redis.expire(self._make_key(key), seconds)
        return result

    async def ttl(self, key: str) -> int:
        """获取剩余过期时间"""
        return await self._redis.ttl(self._make_key(key))

    async def incr(self, key: str, amount: int = 1) -> int:
        """自增"""
        return await self._redis.incrby(self._make_key(key), amount)

    async def decr(self, key: str, amount: int = 1) -> int:
        """自减"""
        return await self._redis.decrby(self._make_key(key), amount)

    async def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配的键列表"""
        full_pattern = self._make_key(pattern)
        keys = await self._redis.keys(full_pattern)
        return [self._strip_prefix(k) for k in keys]

    async def clear(self) -> bool:
        """清空所有缓存（仅清空带前缀的键）"""
        keys = await self._redis.keys(f"{self.prefix}*")
        if keys:
            await self._redis.delete(*keys)
        return True

    async def close(self):
        """关闭连接"""
        await self._redis.close()

    # ========== Redis 特有方法 ==========

    async def hset(self, name: str, key: str, value: Any) -> int:
        """哈希表设置"""
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        return await self._redis.hset(self._make_key(name), key, value)

    async def hget(self, name: str, key: str) -> Optional[Any]:
        """哈希表获取"""
        value = await self._redis.hget(self._make_key(name), key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def hgetall(self, name: str) -> dict:
        """获取整个哈希表"""
        result = await self._redis.hgetall(self._make_key(name))
        parsed = {}
        for k, v in result.items():
            try:
                parsed[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                parsed[k] = v
        return parsed

    async def lpush(self, key: str, *values) -> int:
        """列表左推入"""
        return await self._redis.lpush(self._make_key(key), *values)

    async def rpush(self, key: str, *values) -> int:
        """列表右推入"""
        return await self._redis.rpush(self._make_key(key), *values)

    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        """获取列表范围"""
        return await self._redis.lrange(self._make_key(key), start, end)

    async def publish(self, channel: str, message: Any) -> int:
        """发布消息"""
        if isinstance(message, (dict, list)):
            message = json.dumps(message, ensure_ascii=False)
        return await self._redis.publish(channel, message)
