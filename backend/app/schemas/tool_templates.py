"""Tool template API schemas."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ToolTemplateSummaryResponse(BaseModel):
    """Static tool template summary for admin UI selection."""

    template_key: str
    slug: str
    name: str
    version: str
    description: str
    family: str
    executor_types: list[str]
    capability: str
    stage: str
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    implementation: dict[str, Any] = Field(default_factory=dict)
    resource_profile: dict[str, Any] = Field(default_factory=dict)


class ToolTemplateDraftCreate(BaseModel):
    """Request to create a Tool draft from a static template."""

    executor_type: Literal["remote_api", "docker_image", "python_script", "ssh_job", "k8s_job"]
    executor_config: dict[str, Any] = Field(default_factory=dict)
    category_id: Optional[str] = None
    publish: bool = False
