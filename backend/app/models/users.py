# backend/app/models/users.py
"""用户相关模型"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Enum, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
import enum

from app.database.base import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    """用户角色"""
    GUEST = "guest"
    USER = "user"
    VIP = "vip"
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
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    tools = relationship("Tool", back_populates="owner", foreign_keys="Tool.owner_id")
    tasks = relationship("Task", back_populates="user")
    files = relationship("File", back_populates="owner")
    statistics = relationship("UserStatistics", back_populates="user", uselist=False)


class UserSession(Base, UUIDMixin, TimestampMixin):
    """用户会话表"""
    __tablename__ = "user_sessions"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    session_token = Column(String(255), unique=True, nullable=False, index=True)
    is_guest = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    session_data = Column(JSON, default=dict)  # 原 metadata，避免保留字冲突

    # 游客使用统计
    tasks_today = Column(Integer, default=0)
    last_task_date = Column(DateTime, nullable=True)

    # 关系
    user = relationship("User", back_populates="sessions")
