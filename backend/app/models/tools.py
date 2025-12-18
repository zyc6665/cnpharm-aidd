# backend/app/models/tools.py
"""工具相关模型"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Table
from sqlalchemy.orm import relationship
import enum

from app.database.base import Base, TimestampMixin, UUIDMixin


class ToolStatus(str, enum.Enum):
    """工具状态"""
    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class ToolType(str, enum.Enum):
    """工具类型"""
    REMOTE_API = "remote_api"
    DOCKER_IMAGE = "docker_image"
    PYTHON_SCRIPT = "python_script"


# 工具-标签关联表
tool_tag_association = Table(
    "tool_tag_map",
    Base.metadata,
    Column("tool_id", String(36), ForeignKey("tools.id"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id"), primary_key=True),
)


class Tool(Base, UUIDMixin, TimestampMixin):
    """工具表"""
    __tablename__ = "tools"

    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    icon_url = Column(String(500), nullable=True)

    # 状态
    status = Column(String(20), default=ToolStatus.DRAFT.value, nullable=False)
    is_public = Column(Boolean, default=True)

    # 版本管理
    current_version_id = Column(String(36), nullable=True)

    # 统计
    usage_count = Column(Integer, default=0)
    favorite_count = Column(Integer, default=0)

    # 配置
    gpu_required = Column(Boolean, default=False)
    gpu_memory_mb = Column(Integer, default=0)
    timeout_sec = Column(Integer, default=600)

    # 关系
    owner = relationship("User", back_populates="tools")
    versions = relationship("ToolVersion", back_populates="tool", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=tool_tag_association, back_populates="tools")
    tasks = relationship("Task", back_populates="tool")


class ToolVersion(Base, UUIDMixin, TimestampMixin):
    """工具版本表"""
    __tablename__ = "tool_versions"

    tool_id = Column(String(36), ForeignKey("tools.id"), nullable=False, index=True)
    version = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)

    # 配置
    config = Column(JSON, nullable=False)
    # config结构:
    # {
    #     "type": "remote_api|docker_image|python_script",
    #     "endpoint": "http://...",  # remote_api
    #     "method": "POST",          # remote_api
    #     "headers": {},             # remote_api
    #     "image": "...",            # docker_image
    #     "command": [...],          # docker_image
    #     "input_schema": {...},     # JSON Schema
    #     "output_schema": {...},    # JSON Schema
    # }

    # 状态
    is_active = Column(Boolean, default=True)
    deprecated = Column(Boolean, default=False)
    deprecated_at = Column(DateTime, nullable=True)

    # 关系
    tool = relationship("Tool", back_populates="versions")
    tasks = relationship("Task", back_populates="tool_version")


class Tag(Base, UUIDMixin, TimestampMixin):
    """标签表"""
    __tablename__ = "tags"

    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String(200), nullable=True)
    color = Column(String(20), default="#1890ff")
    icon = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0)

    # 关系
    tools = relationship("Tool", secondary=tool_tag_association, back_populates="tags")


class ToolFavorite(Base, UUIDMixin, TimestampMixin):
    """工具收藏表"""
    __tablename__ = "tool_favorites"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    tool_id = Column(String(36), ForeignKey("tools.id"), nullable=False, index=True)
