# backend/app/models/verification.py
"""验证码模型"""

from sqlalchemy import Column, String, Boolean, DateTime, Integer, Index
import enum

from app.database.base import Base, TimestampMixin, UUIDMixin


class VerificationPurpose(str, enum.Enum):
    """验证码用途"""
    REGISTER = "register"           # 注册
    RESET_PASSWORD = "reset_password"  # 重置密码


class VerificationCode(Base, UUIDMixin, TimestampMixin):
    """
    验证码表

    存储邮箱验证码，支持注册和找回密码场景。
    开发环境使用数据库存储，生产环境使用缓存存储。
    """
    __tablename__ = "verification_codes"

    email = Column(String(255), nullable=False, index=True)
    code = Column(String(10), nullable=False)
    purpose = Column(String(20), nullable=False)  # register, reset_password
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    ip_address = Column(String(50), nullable=True)

    # 复合索引：用于快速查询未使用的有效验证码
    __table_args__ = (
        Index('ix_verification_email_purpose', 'email', 'purpose'),
    )


class VerificationDailyCount(Base, UUIDMixin):
    """
    验证码每日发送计数表

    用于限制每个邮箱每日发送验证码的次数。
    """
    __tablename__ = "verification_daily_counts"

    email = Column(String(255), nullable=False, index=True)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD 格式
    count = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index('ix_daily_count_email_date', 'email', 'date', unique=True),
    )
