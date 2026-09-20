"""Executor-neutral request and response contracts."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from app.common.task_status import task_status_to_execution_state


class ExecutionState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def from_task_status(cls, status: Any) -> "ExecutionState":
        """Build an execution state from a persisted task status."""
        mapped = task_status_to_execution_state(status)
        if mapped is None:
            raise ValueError(f"无法映射任务状态: {status}")
        return cls(mapped)


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

    @classmethod
    def from_tool_config(
        cls,
        *,
        idempotency_key: str,
        project_id: str,
        requested_by: str,
        tool_package_version_id: str,
        variant: str,
        tool_config: Mapping[str, Any],
        parameters: Mapping[str, Any] | None = None,
        inputs: list[ExecutionInput] | None = None,
        resources: Mapping[str, Any] | None = None,
    ) -> "ExecutionRequest":
        """Build an execution request from a persisted legacy tool config."""
        from app.execution.executor_types import execution_type_for_tool_type

        executor_type = execution_type_for_tool_type(str(tool_config.get("type") or ""))
        return cls(
            idempotency_key=idempotency_key,
            project_id=project_id,
            requested_by=requested_by,
            tool_package_version_id=tool_package_version_id,
            variant=variant,
            executor_type=executor_type,
            parameters=dict(parameters or {}),
            inputs=list(inputs or []),
            resources=dict(resources or {}),
        )


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
    file_id: str | None = None
    content_type: str | None = None
    sha256: str | None = None
    artifact_type: str | None = None
