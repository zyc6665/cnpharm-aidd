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


class ToolProviderType(str, enum.Enum):
    """工具提供者类型"""
    PLATFORM = "platform"  # 平台官方工具
    USER = "user"          # 用户贡献工具


class ToolReviewStatus(str, enum.Enum):
    """工具审核状态"""
    NOT_REQUIRED = "not_required"  # 无需审核（平台官方工具）
    PENDING = "pending"            # 待审核
    APPROVED = "approved"          # 已通过
    REJECTED = "rejected"          # 已拒绝


# 工具-标签关联表
tool_tag_association = Table(
    "tool_tag_map",
    Base.metadata,
    Column("tool_id", String(36), ForeignKey("tools.id"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id"), primary_key=True),
)


class ToolCategory(Base, UUIDMixin, TimestampMixin):
    """工具分类表"""
    __tablename__ = "tool_categories"

    name = Column(String(100), unique=True, nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False, index=True)

    tools = relationship("Tool", back_populates="tool_category")


class Tool(Base, UUIDMixin, TimestampMixin):
    """工具表"""
    __tablename__ = "tools"

    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    icon = Column(String(100), nullable=True)  # 工具图标（emoji或图标名）
    icon_url = Column(String(500), nullable=True)  # 工具图标URL
    category = Column(String(50), nullable=True, index=True)  # 工具分类
    category_id = Column(String(36), ForeignKey("tool_categories.id"), nullable=True, index=True)

    # 状态
    status = Column(String(20), default=ToolStatus.DRAFT.value, nullable=False)
    is_public = Column(Boolean, default=True)

    # === 新增字段：工具提供者和审核相关 ===
    provider_type = Column(String(20), default=ToolProviderType.USER.value, nullable=False, index=True)
    review_status = Column(String(20), default=ToolReviewStatus.PENDING.value, nullable=False, index=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reject_reason = Column(Text, nullable=True)
    # === 新增字段结束 ===

    # 版本管理
    current_version_id = Column(String(36), nullable=True)

    # 配置
    gpu_required = Column(Boolean, default=False)
    gpu_memory_mb = Column(Integer, default=0)
    timeout_sec = Column(Integer, default=600)

    # 关系
    owner = relationship("User", back_populates="tools", foreign_keys=[owner_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    tool_category = relationship("ToolCategory", back_populates="tools")
    versions = relationship("ToolVersion", back_populates="tool", cascade="all, delete-orphan")
    current_version = relationship("ToolVersion", foreign_keys=[current_version_id], primaryjoin="Tool.current_version_id==ToolVersion.id", uselist=False, post_update=True)
    tags = relationship("Tag", secondary=tool_tag_association, back_populates="tools")
    tasks = relationship("Task", back_populates="tool")
    statistics = relationship("ToolStatistics", back_populates="tool", uselist=False)


class ToolVersion(Base, UUIDMixin, TimestampMixin):
    """工具版本表"""
    __tablename__ = "tool_versions"

    tool_id = Column(String(36), ForeignKey("tools.id"), nullable=False, index=True)
    version = Column(String(50), nullable=False)
    changelog = Column(Text, nullable=True)  # 版本更新日志
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
    tool = relationship("Tool", back_populates="versions", foreign_keys=[tool_id])
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
