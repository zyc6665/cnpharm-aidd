# backend/app/models/users.py
"""用户相关模型"""

from sqlalchemy import Column, String, Integer
from sqlalchemy.orm import relationship
import enum

from app.database.base import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    """用户角色"""
    USER = "user"
    ADMIN = "admin"


class UserStatus(str, enum.Enum):
    """用户状态"""
    ACTIVE = "active"
    DISABLED = "disabled"
    PENDING = "pending"


class User(Base, UUIDMixin, TimestampMixin):
    """用户表"""
    __tablename__ = "users"

    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    role = Column(String(20), default=UserRole.USER.value, nullable=False)
    status = Column(String(20), default=UserStatus.ACTIVE.value, nullable=False)

    # 配额相关
    daily_task_limit = Column(Integer, default=50)
    max_file_size_mb = Column(Integer, default=100)

    # 关系
    tools = relationship("Tool", back_populates="owner", foreign_keys="Tool.owner_id")
    tasks = relationship("Task", back_populates="user")
    files = relationship("File", back_populates="owner")
    statistics = relationship("UserStatistics", back_populates="user", uselist=False)
