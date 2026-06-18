"""Workflow API schemas."""

from __future__ import annotations

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


class WorkflowTemplateCreate(BaseModel):
    """Create a reusable workflow template."""

    name: str = Field(..., min_length=1, max_length=160)
    description: str | None = None
    definition: dict[str, Any] = Field(default_factory=dict)
    is_public: bool = False


class WorkflowTemplateUpdate(BaseModel):
    """Update a workflow template."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    definition: dict[str, Any] | None = None
    is_public: bool | None = None
    status: str | None = None


class WorkflowTemplateDuplicate(BaseModel):
    """Duplicate a workflow template."""

    name: str | None = Field(default=None, min_length=1, max_length=160)


class WorkflowRunCreate(BaseModel):
    """Create a workflow run from a template."""

    name: str | None = Field(default=None, max_length=160)
    input_files: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplateResponse(BaseModel):
    """Workflow template response."""

    id: str
    owner_id: str
    name: str
    description: str | None = None
    status: str
    definition: dict[str, Any]
    is_public: bool
    version: int
    created_at: datetime
    updated_at: datetime


class WorkflowRunResponse(BaseModel):
    """Workflow run response."""

    id: str
    owner_id: str
    template_id: str | None = None
    name: str
    status: str
    definition: dict[str, Any]
    input_files: dict[str, str]
    execution_order: list[str]
    node_states: dict[str, Any]
    artifact_lineage: dict[str, Any]
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
