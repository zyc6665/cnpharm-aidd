# backend/app/models/statistics.py
"""统计数据模型 - 符合第三范式"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database.base import Base


class UserStatistics(Base):
    """用户统计表 - 从users表分离出来的统计数据"""
    __tablename__ = "user_statistics"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    total_tasks = Column(Integer, default=0, nullable=False)
    total_success_tasks = Column(Integer, default=0, nullable=False)
    total_failed_tasks = Column(Integer, default=0, nullable=False)
    total_credits_used = Column(Float, default=0.0, nullable=False)
    last_task_at = Column(DateTime, nullable=True)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 关系
    user = relationship("User", back_populates="statistics")

    def __repr__(self):
        return f"<UserStatistics(user_id={self.user_id}, total_tasks={self.total_tasks})>"


class ToolStatistics(Base):
    """工具统计表 - 从tools表分离出来的统计数据"""
    __tablename__ = "tool_statistics"

    tool_id = Column(String(36), ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True)
    usage_count = Column(Integer, default=0, nullable=False)
    favorite_count = Column(Integer, default=0, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    success_rate = Column(Float, default=0.0, nullable=False)
    avg_execution_time = Column(Float, default=0.0, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 关系
    tool = relationship("Tool", back_populates="statistics")

    def __repr__(self):
        return f"<ToolStatistics(tool_id={self.tool_id}, usage_count={self.usage_count})>"


class FileStatistics(Base):
    """文件统计表 - 从files表分离出来的统计数据"""
    __tablename__ = "file_statistics"

    file_id = Column(String(36), ForeignKey("files.id", ondelete="CASCADE"), primary_key=True)
    download_count = Column(Integer, default=0, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    last_download_at = Column(DateTime, nullable=True)
    last_view_at = Column(DateTime, nullable=True)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 关系
    file = relationship("File", back_populates="statistics")

    def __repr__(self):
        return f"<FileStatistics(file_id={self.file_id}, download_count={self.download_count})>"
