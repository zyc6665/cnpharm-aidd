# backend/app/schemas/tasks.py
"""任务相关Schema"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import TimestampMixin


class TaskInputSchema(BaseModel):
    """任务输入Schema"""
    params: Dict[str, Any] = Field(default_factory=dict, description="参数")
    file_ids: List[str] = Field(default_factory=list, description="文件ID列表")
    input_bindings: Dict[str, str] = Field(
        default_factory=dict,
        description="标准 ArtifactVersion 输入绑定，按 Tool Package v2 input name 索引",
    )
    standard_input_uploads: Dict[str, str] = Field(
        default_factory=dict,
        description="标准 Artifact 输入槽的直接上传文件绑定，按 input name 索引",
    )


class TaskOutputSchema(BaseModel):
    """任务输出Schema"""
    result: Optional[Dict[str, Any]] = Field(None, description="结果数据")
    file_ids: List[str] = Field(default_factory=list, description="输出文件ID列表")
    output_type: str = Field(default="json", description="输出类型")


class TaskCreate(BaseModel):
    """创建任务"""
    name: Optional[str] = Field(None, description="任务名称")
    project_id: Optional[str] = Field(None, min_length=1, max_length=36, description="关联研究项目ID")
    tool_id: str = Field(..., description="工具ID")
    tool_version_id: Optional[str] = Field(None, description="工具版本ID(可选，默认使用当前版本)")
    params: Dict[str, Any] = Field(default_factory=dict, description="参数")
    file_ids: List[str] = Field(default_factory=list, description="输入文件ID列表")
    input_bindings: Dict[str, str] = Field(
        default_factory=dict,
        description="标准 ArtifactVersion 输入绑定，按 Tool Package v2 input name 索引",
    )
    standard_input_uploads: Dict[str, str] = Field(
        default_factory=dict,
        description="标准 Artifact 输入槽的直接上传文件绑定，按 input name 索引",
    )
    priority: str = Field(default="normal", description="优先级")


class TaskResponse(TimestampMixin):
    """任务响应"""
    id: str
    name: Optional[str] = None
    project_id: Optional[str] = Field(None, min_length=1, max_length=36)
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
    input_bindings: Dict[str, str] = Field(default_factory=dict)
    binding_decisions: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    inputs: Optional[TaskInputSchema] = None
    outputs: Optional[TaskOutputSchema] = None

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    """任务列表响应"""
    id: str
    name: Optional[str] = None
    project_id: Optional[str] = Field(None, min_length=1, max_length=36)
    tool_id: str
    tool_name: Optional[str] = None
    tool_slug: Optional[str] = None
    status: str
    progress: float
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class TaskLogResponse(BaseModel):
    """任务日志响应"""
    id: str
    task_id: str
    timestamp: datetime
    level: str
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict, validation_alias="log_data")

    model_config = ConfigDict(from_attributes=True)


class TaskRetry(BaseModel):
    """任务重试"""
    task_id: str = Field(..., description="任务ID")
