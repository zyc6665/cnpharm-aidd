# backend/app/services/verification/storage.py
"""
验证码存储服务 - 策略模式实现

开发环境：使用数据库存储（便于调试）
生产环境：使用缓存存储（Redis/内存）
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Tuple
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete

from app.common.time import utcnow
from app.config import settings, is_development
from app.models.verification import VerificationCode, VerificationDailyCount


class VerificationStorageBase(ABC):
    """验证码存储抽象基类"""

    @abstractmethod
    async def save_code(
        self,
        email: str,
        code: str,
        purpose: str,
        expires_at: datetime,
        ip_address: Optional[str] = None
    ) -> bool:
        """保存验证码"""
        pass

    @abstractmethod
    async def get_code(
        self,
        email: str,
        purpose: str
    ) -> Optional[Tuple[str, datetime]]:
        """获取有效验证码，返回 (code, expires_at)"""
        pass

    @abstractmethod
    async def mark_used(self, email: str, purpose: str) -> bool:
        """标记验证码已使用"""
        pass

    @abstractmethod
    async def get_last_send_time(self, email: str, purpose: str) -> Optional[datetime]:
        """获取上次发送时间（用于频率限制）"""
        pass

    @abstractmethod
    async def get_daily_count(self, email: str) -> int:
        """获取今日发送次数"""
        pass

    @abstractmethod
    async def increment_daily_count(self, email: str) -> int:
        """增加今日发送次数"""
        pass


class DatabaseStorage(VerificationStorageBase):
    """
    数据库存储实现

    适用于开发环境，便于调试和查看验证码记录。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_code(
        self,
        email: str,
        code: str,
        purpose: str,
        expires_at: datetime,
        ip_address: Optional[str] = None
    ) -> bool:
        """保存验证码到数据库"""
        # 先将该邮箱+用途的旧验证码标记为已使用
        await self.db.execute(
            delete(VerificationCode).where(
                and_(
                    VerificationCode.email == email,
                    VerificationCode.purpose == purpose,
                    VerificationCode.is_used == False
                )
            )
        )

        # 创建新验证码记录
        verification = VerificationCode(
            email=email,
            code=code,
            purpose=purpose,
            expires_at=expires_at,
            ip_address=ip_address,
            is_used=False
        )
        self.db.add(verification)
        await self.db.commit()
        return True

    async def get_code(
        self,
        email: str,
        purpose: str
    ) -> Optional[Tuple[str, datetime]]:
        """获取有效验证码"""
        result = await self.db.execute(
            select(VerificationCode).where(
                and_(
                    VerificationCode.email == email,
                    VerificationCode.purpose == purpose,
                    VerificationCode.is_used == False,
                    VerificationCode.expires_at > utcnow()
                )
            ).order_by(VerificationCode.created_at.desc())
        )
        record = result.scalar_one_or_none()
        if record:
            return (record.code, record.expires_at)
        return None

    async def mark_used(self, email: str, purpose: str) -> bool:
        """标记验证码已使用"""
        result = await self.db.execute(
            select(VerificationCode).where(
                and_(
                    VerificationCode.email == email,
                    VerificationCode.purpose == purpose,
                    VerificationCode.is_used == False
                )
            )
        )
        record = result.scalar_one_or_none()
        if record:
            record.is_used = True
            await self.db.commit()
            return True
        return False

    async def get_last_send_time(self, email: str, purpose: str) -> Optional[datetime]:
        """获取上次发送时间"""
        result = await self.db.execute(
            select(VerificationCode.created_at).where(
                and_(
                    VerificationCode.email == email,
                    VerificationCode.purpose == purpose
                )
            ).order_by(VerificationCode.created_at.desc()).limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    async def get_daily_count(self, email: str) -> int:
        """获取今日发送次数"""
        today = utcnow().strftime("%Y-%m-%d")
        result = await self.db.execute(
            select(VerificationDailyCount.count).where(
                and_(
                    VerificationDailyCount.email == email,
                    VerificationDailyCount.date == today
                )
            )
        )
        count = result.scalar_one_or_none()
        return count or 0

    async def increment_daily_count(self, email: str) -> int:
        """增加今日发送次数"""
        today = utcnow().strftime("%Y-%m-%d")
        result = await self.db.execute(
            select(VerificationDailyCount).where(
                and_(
                    VerificationDailyCount.email == email,
                    VerificationDailyCount.date == today
                )
            )
        )
        record = result.scalar_one_or_none()

        if record:
            record.count += 1
            await self.db.commit()
            return record.count
        else:
            new_record = VerificationDailyCount(
                email=email,
                date=today,
                count=1
            )
            self.db.add(new_record)
            await self.db.commit()
            return 1


class CacheStorage(VerificationStorageBase):
    """
    缓存存储实现

    适用于生产环境，使用 Redis 或内存缓存。
    """

    def __init__(self, cache):
        """
        Args:
            cache: CacheBackend 实例（Redis 或内存缓存）
        """
        self.cache = cache
        self.prefix = "verification:"

    def _code_key(self, email: str, purpose: str) -> str:
        """生成验证码缓存键"""
        return f"{self.prefix}code:{email}:{purpose}"

    def _send_time_key(self, email: str, purpose: str) -> str:
        """生成发送时间缓存键"""
        return f"{self.prefix}send_time:{email}:{purpose}"

    def _daily_count_key(self, email: str) -> str:
        """生成每日计数缓存键"""
        today = utcnow().strftime("%Y-%m-%d")
        return f"{self.prefix}daily:{email}:{today}"

    async def save_code(
        self,
        email: str,
        code: str,
        purpose: str,
        expires_at: datetime,
        ip_address: Optional[str] = None
    ) -> bool:
        """保存验证码到缓存"""
        ttl = int((expires_at - utcnow()).total_seconds())
        if ttl <= 0:
            return False

        data = {
            "code": code,
            "expires_at": expires_at.isoformat(),
            "ip_address": ip_address
        }

        # 保存验证码
        await self.cache.set(
            self._code_key(email, purpose),
            data,
            expire=ttl
        )

        # 记录发送时间
        await self.cache.set(
            self._send_time_key(email, purpose),
            utcnow().isoformat(),
            expire=settings.VERIFICATION_CODE_RATE_LIMIT_SECONDS
        )

        return True

    async def get_code(
        self,
        email: str,
        purpose: str
    ) -> Optional[Tuple[str, datetime]]:
        """获取有效验证码"""
        data = await self.cache.get(self._code_key(email, purpose))
        if not data:
            return None

        expires_at = datetime.fromisoformat(data["expires_at"])
        if expires_at <= utcnow():
            return None

        return (data["code"], expires_at)

    async def mark_used(self, email: str, purpose: str) -> bool:
        """标记验证码已使用（直接删除）"""
        return await self.cache.delete(self._code_key(email, purpose))

    async def get_last_send_time(self, email: str, purpose: str) -> Optional[datetime]:
        """获取上次发送时间"""
        time_str = await self.cache.get(self._send_time_key(email, purpose))
        if time_str:
            return datetime.fromisoformat(time_str)
        return None

    async def get_daily_count(self, email: str) -> int:
        """获取今日发送次数"""
        count = await self.cache.get(self._daily_count_key(email))
        return int(count) if count else 0

    async def increment_daily_count(self, email: str) -> int:
        """增加今日发送次数"""
        key = self._daily_count_key(email)
        count = await self.cache.get(key)

        if count:
            new_count = int(count) + 1
        else:
            new_count = 1

        # 设置过期时间为当天剩余秒数
        now = utcnow()
        end_of_day = now.replace(hour=23, minute=59, second=59)
        ttl = int((end_of_day - now).total_seconds()) + 1

        await self.cache.set(key, new_count, expire=ttl)
        return new_count


def get_verification_storage(db: AsyncSession = None, cache=None) -> VerificationStorageBase:
    """
    获取验证码存储实例（工厂函数）

    根据环境自动选择：
    - 开发环境：使用数据库存储
    - 生产环境：使用缓存存储

    Args:
        db: 数据库会话（开发环境需要）
        cache: 缓存实例（生产环境需要）

    Returns:
        VerificationStorageBase 实例
    """
    if is_development():
        if db is None:
            raise ValueError("开发环境需要提供数据库会话")
        return DatabaseStorage(db)
    else:
        if cache is None:
            raise ValueError("生产环境需要提供缓存实例")
        return CacheStorage(cache)
