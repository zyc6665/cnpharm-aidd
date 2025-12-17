# backend/app/models/files.py
"""文件相关模型"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
import enum

from app.database.base import Base, TimestampMixin, UUIDMixin


class FileSourceType(str, enum.Enum):
    """文件来源类型"""
    USER_INPUT = "user_input"
    TOOL_OUTPUT = "tool_output"
    SYSTEM = "system"


class File(Base, UUIDMixin, TimestampMixin):
    """文件表"""
    __tablename__ = "files"

    owner_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String(36), nullable=True, index=True)  # 游客session

    # 文件信息
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=True)
    size = Column(Integer, nullable=False)  # 文件大小（字节）
    sha256 = Column(String(64), nullable=False, index=True)

    # 存储信息
    storage_backend = Column(String(20), default="local")  # local, minio
    storage_path = Column(String(500), nullable=False)

    # 来源
    source_type = Column(String(20), default=FileSourceType.USER_INPUT.value)

    # 状态
    is_public = Column(Boolean, default=False)
    is_corrupted = Column(Boolean, default=False)
    is_permanent = Column(Boolean, default=False)

    # 生命周期
    expires_at = Column(DateTime, nullable=True)
    download_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)  # 软删除时间

    # 去重相关
    reference_count = Column(Integer, default=1)  # 引用计数

    # 元数据
    file_meta = Column(JSON, default=dict)  # 原 metadata，避免保留字冲突

    # 关系
    owner = relationship("User", back_populates="files")
    access_logs = relationship("FileAccessLog", back_populates="file", cascade="all, delete-orphan")


class FileAccessLog(Base, UUIDMixin):
    """文件访问日志表"""
    __tablename__ = "file_access_logs"

    file_id = Column(String(36), ForeignKey("files.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String(36), nullable=True)  # 游客session

    # 访问信息
    action = Column(String(50), nullable=False)  # upload, download, reference, delete
    accessed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # 关系
    file = relationship("File", back_populates="access_logs")
