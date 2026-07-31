# backend/app/schemas/statistics.py
"""统计数据Schema"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class UserStatisticsResponse(BaseModel):
    """用户统计响应"""
    user_id: str = Field(..., description="用户ID")
    total_tasks: int = Field(default=0, description="总任务数")
    total_success_tasks: int = Field(default=0, description="成功任务数")
    total_failed_tasks: int = Field(default=0, description="失败任务数")
    last_task_at: Optional[datetime] = Field(None, description="最后任务时间")
    last_updated_at: datetime = Field(..., description="最后更新时间")

    model_config = ConfigDict(from_attributes=True)


class ToolStatisticsResponse(BaseModel):
    """工具统计响应"""
    tool_id: str = Field(..., description="工具ID")
    usage_count: int = Field(default=0, description="使用次数")
    favorite_count: int = Field(default=0, description="收藏次数")
    view_count: int = Field(default=0, description="浏览次数")
    success_rate: float = Field(default=0.0, description="成功率")
    avg_execution_time: float = Field(default=0.0, description="平均执行时间(秒)")
    last_used_at: Optional[datetime] = Field(None, description="最后使用时间")
    last_updated_at: datetime = Field(..., description="最后更新时间")

    model_config = ConfigDict(from_attributes=True)


class FileStatisticsResponse(BaseModel):
    """文件统计响应"""
    file_id: str = Field(..., description="文件ID")
    download_count: int = Field(default=0, description="下载次数")
    view_count: int = Field(default=0, description="浏览次数")
    last_download_at: Optional[datetime] = Field(None, description="最后下载时间")
    last_view_at: Optional[datetime] = Field(None, description="最后浏览时间")
    last_updated_at: datetime = Field(..., description="最后更新时间")

    model_config = ConfigDict(from_attributes=True)
