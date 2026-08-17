"""Stage diagnostics for remote tool self-registration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


RemoteToolStageStatus = Literal["success", "failure", "warning"]


class RemoteToolStageDiagnostic(BaseModel):
    """A single self-registration diagnostic stage."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: RemoteToolStageStatus
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)

