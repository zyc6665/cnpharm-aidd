"""Executor-neutral request and response contracts."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExecutionState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionInput(BaseModel):
    artifact_version_id: str
    name: str
    uri: str
    sha256: str

    model_config = ConfigDict(extra="forbid")


class ExecutionRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    project_id: str
    requested_by: str
    tool_package_version_id: str
    variant: str = Field(min_length=1, max_length=100)
    executor_type: Literal["container", "cli", "remote_job", "ssh"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    inputs: list[ExecutionInput] = Field(default_factory=list)
    resources: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ExecutionHandle(BaseModel):
    execution_id: str
    state: ExecutionState
    external_id: str | None = None


class LogChunk(BaseModel):
    content: str
    next_cursor: str | None = None
    complete: bool = False


class ProducedArtifact(BaseModel):
    filename: str
    path: str
    content_type: str | None = None
    sha256: str | None = None
    artifact_type: str | None = None
