# backend/app/schemas/tasks.py
"""任务相关Schema"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.common import TimestampMixin


class TaskInputSchema(BaseModel):
    """任务输入Schema"""
    params: Dict[str, Any] = Field(default_factory=dict, description="参数")
    file_ids: List[str] = Field(default_factory=list, description="文件ID列表")


class TaskOutputSchema(BaseModel):
    """任务输出Schema"""
    result: Optional[Dict[str, Any]] = Field(None, description="结果数据")
    file_ids: List[str] = Field(default_factory=list, description="输出文件ID列表")
    output_type: str = Field(default="json", description="输出类型")


class TaskCreate(BaseModel):
    """创建任务"""
    tool_id: str = Field(..., description="工具ID")
    tool_version_id: Optional[str] = Field(None, description="工具版本ID(可选，默认使用当前版本)")
    params: Dict[str, Any] = Field(default_factory=dict, description="参数")
    file_ids: List[str] = Field(default_factory=list, description="输入文件ID列表")
    priority: str = Field(default="normal", description="优先级")


class TaskResponse(TimestampMixin):
    """任务响应"""
    id: str
    user_id: Optional[str]
    tool_id: str
    tool_version_id: str
    status: str
    priority: str
    progress: float
    progress_message: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    execution_time_sec: Optional[int]
    retry_count: int
    # 工具信息
    tool_name: Optional[str] = None
    tool_slug: Optional[str] = None
    # 输入输出
    inputs: Optional[TaskInputSchema] = None
    outputs: Optional[TaskOutputSchema] = None

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """任务列表响应"""
    id: str
    tool_id: str
    tool_name: Optional[str] = None
    tool_slug: Optional[str] = None
    status: str
    progress: float
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


class TaskLogResponse(BaseModel):
    """任务日志响应"""
    id: str
    task_id: str
    timestamp: datetime
    level: str
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class TaskRetry(BaseModel):
    """任务重试"""
    task_id: str = Field(..., description="任务ID")
