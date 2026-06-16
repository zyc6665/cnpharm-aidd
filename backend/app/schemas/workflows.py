"""工作流定义 Schema"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


WorkflowDefinitionStatus = Literal["draft", "active", "archived"]


class WorkflowDefinitionBase(BaseModel):
    """工作流定义基础字段。"""

    name: str = Field(..., min_length=1, max_length=120, description="流程名称")
    description: Optional[str] = Field(None, description="流程描述")
    template_id: str = Field(..., min_length=1, max_length=120, description="模板 ID")
    nodes: list[dict[str, Any]] = Field(default_factory=list, description="节点定义")
    edges: list[dict[str, Any]] = Field(default_factory=list, description="连线定义")
    selected_tool_by_node: dict[str, str] = Field(default_factory=dict, description="节点工具选择")
    artifact_bindings_by_node: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="节点产物绑定",
    )
    status: WorkflowDefinitionStatus = Field(default="draft", description="状态")


class WorkflowDefinitionCreate(WorkflowDefinitionBase):
    """创建工作流定义。"""


class WorkflowDefinitionUpdate(BaseModel):
    """更新工作流定义。"""

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    template_id: Optional[str] = Field(None, min_length=1, max_length=120)
    nodes: Optional[list[dict[str, Any]]] = None
    edges: Optional[list[dict[str, Any]]] = None
    selected_tool_by_node: Optional[dict[str, str]] = None
    artifact_bindings_by_node: Optional[dict[str, dict[str, str]]] = None
    status: Optional[WorkflowDefinitionStatus] = None


class WorkflowDefinitionResponse(WorkflowDefinitionBase):
    """工作流定义响应。"""

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
