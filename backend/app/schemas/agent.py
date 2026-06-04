"""AIDD agent schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AIDDRunCreate(BaseModel):
    """Create an AIDD agent run."""

    message: str = Field(..., min_length=1)
    input_file_id: str
    input_type: Optional[str] = None
    requested_outputs: list[str] = Field(default_factory=lambda: ["generated_ligand"])
    params: dict[str, Any] = Field(default_factory=dict)


class AIDDRunStepResponse(BaseModel):
    """AIDD agent run step response."""

    id: str
    step_key: str
    tool_slug: str
    tool_id: Optional[str] = None
    task_id: Optional[str] = None
    status: str
    sort_order: int
    depends_on_step_ids: list[str] = Field(default_factory=list)
    semantic_inputs: dict[str, Any] = Field(default_factory=dict)
    semantic_outputs: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    input_file_ids: list[str] = Field(default_factory=list)
    output_file_ids: list[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AIDDRunResponse(BaseModel):
    """AIDD agent run response."""

    id: str
    message: str
    intent: str
    status: str
    input_type: str
    input_file_id: Optional[str] = None
    requested_outputs: list[str]
    plan: dict[str, Any]
    summary: Optional[str] = None
    error_message: Optional[str] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    steps: list[AIDDRunStepResponse] = Field(default_factory=list)
