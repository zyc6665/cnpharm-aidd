# backend/app/services/verification/service.py
"""验证码核心服务"""

import random
import string
import logging
from datetime import timedelta
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.config import settings, is_development
from app.services.verification.storage import (
    VerificationStorageBase,
    DatabaseStorage,
    CacheStorage,
)
from app.services.email.sender import get_email_service
from app.cache import get_cache

logger = logging.getLogger(__name__)


class VerificationError(Exception):
    """验证码相关错误"""
    pass


class RateLimitError(VerificationError):
    """发送频率限制错误"""
    pass


class DailyLimitError(VerificationError):
    """每日发送上限错误"""
    pass


class InvalidCodeError(VerificationError):
    """验证码无效错误"""
    pass


class VerificationService:
    """
    验证码服务

    提供验证码的生成、发送、验证功能。
    支持频率限制和每日发送上限。
    """

    def __init__(
        self,
        storage: VerificationStorageBase,
        code_length: int = None,
        expire_minutes: int = None,
        rate_limit_seconds: int = None,
        daily_limit: int = None
    ):
        """
        初始化验证码服务

        Args:
            storage: 存储后端实例
            code_length: 验证码长度
            expire_minutes: 有效期（分钟）
            rate_limit_seconds: 发送频率限制（秒）
            daily_limit: 每日发送上限
        """
        self.storage = storage
        self.code_length = code_length or settings.VERIFICATION_CODE_LENGTH
        self.expire_minutes = expire_minutes or settings.VERIFICATION_CODE_EXPIRE_MINUTES
        self.rate_limit_seconds = rate_limit_seconds or settings.VERIFICATION_CODE_RATE_LIMIT_SECONDS
        self.daily_limit = daily_limit or settings.VERIFICATION_CODE_DAILY_LIMIT
        self.email_service = get_email_service()

    def _generate_code(self) -> str:
        """生成随机验证码（纯数字）"""
        return ''.join(random.choices(string.digits, k=self.code_length))

    async def _check_rate_limit(self, email: str, purpose: str) -> None:
        """
        检查发送频率限制

        Args:
            email: 邮箱
            purpose: 用途

        Raises:
            RateLimitError: 超过发送频率限制
        """
        last_send_time = await self.storage.get_last_send_time(email, purpose)
        if last_send_time:
            elapsed = (utcnow() - last_send_time).total_seconds()
            if elapsed < self.rate_limit_seconds:
                remaining = int(self.rate_limit_seconds - elapsed)
                raise RateLimitError(f"发送过于频繁，请 {remaining} 秒后重试")

    async def _check_daily_limit(self, email: str) -> None:
        """
        检查每日发送上限

        Args:
            email: 邮箱

        Raises:
            DailyLimitError: 超过每日发送上限
        """
        daily_count = await self.storage.get_daily_count(email)
        if daily_count >= self.daily_limit:
            raise DailyLimitError(f"今日发送次数已达上限（{self.daily_limit}次）")

    async def send_code(
        self,
        email: str,
        purpose: str,
        ip_address: Optional[str] = None
    ) -> Tuple[bool, int]:
        """
        发送验证码

        Args:
            email: 邮箱地址
            purpose: 用途 (register/reset_password)
            ip_address: 请求 IP 地址（可选）

        Returns:
            (是否成功, 验证码有效期秒数)

        Raises:
            RateLimitError: 发送频率过高
            DailyLimitError: 超过每日上限
        """
        # 检查频率限制
        await self._check_rate_limit(email, purpose)

        # 检查每日上限
        await self._check_daily_limit(email)

        # 生成验证码
        code = self._generate_code()
        expires_at = utcnow() + timedelta(minutes=self.expire_minutes)

        # 保存验证码
        await self.storage.save_code(
            email=email,
            code=code,
            purpose=purpose,
            expires_at=expires_at,
            ip_address=ip_address
        )

        # 增加每日计数
        await self.storage.increment_daily_count(email)

        # 发送邮件
        success = await self.email_service.send_verification_code(
            email=email,
            code=code,
            purpose=purpose
        )

        if not success:
            logger.error(f"验证码邮件发送失败: {email}")
            # 即使邮件发送失败，验证码已保存，返回成功
            # 在开发环境中，SMTP 未配置时会记录到日志

        expires_in = self.expire_minutes * 60
        logger.info(f"验证码已生成: email={email}, purpose={purpose}")

        return True, expires_in

    async def verify_code(
        self,
        email: str,
        code: str,
        purpose: str,
        mark_used: bool = True
    ) -> bool:
        """
        验证验证码

        Args:
            email: 邮箱地址
            code: 用户输入的验证码
            purpose: 用途
            mark_used: 验证成功后是否标记为已使用

        Returns:
            验证是否成功

        Raises:
            InvalidCodeError: 验证码无效或已过期
        """
        stored = await self.storage.get_code(email, purpose)

        if not stored:
            raise InvalidCodeError("验证码不存在或已过期")

        stored_code, expires_at = stored

        if utcnow() > expires_at:
            raise InvalidCodeError("验证码已过期")

        if stored_code != code:
            raise InvalidCodeError("验证码错误")

        # 标记为已使用
        if mark_used:
            await self.storage.mark_used(email, purpose)

        logger.info(f"验证码验证成功: email={email}, purpose={purpose}")
        return True


async def get_verification_service(db: AsyncSession) -> VerificationService:
    """
    获取验证码服务实例

    根据环境自动选择存储后端。

    Args:
        db: 数据库会话

    Returns:
        VerificationService 实例
    """
    if is_development():
        storage = DatabaseStorage(db)
    else:
        cache = get_cache()
        storage = CacheStorage(cache)

    return VerificationService(storage)
