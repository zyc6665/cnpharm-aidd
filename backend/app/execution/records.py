"""Task execution record lifecycle for package-backed external runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.task_context import task_extra_data, task_project_id
from app.common.time import utcnow
from app.execution.executor_types import execution_type_for_tool_type
from app.models.executions import ExecutionRecord
from app.models.tool_packages import ToolPackage, ToolPackageVersion


EXECUTION_RECORD_ID_KEY = "execution_record_id"


def task_execution_record_id(task: Any) -> str | None:
    """Read the compatibility pointer stored on Task.extra_data."""
    value = task_extra_data(task).get(EXECUTION_RECORD_ID_KEY)
    return str(value) if value else None


def set_task_execution_record_id(task: Any, record_id: str | None) -> None:
    """Persist the execution record pointer in the task compatibility metadata."""
    data = task_extra_data(task)
    if record_id:
        data[EXECUTION_RECORD_ID_KEY] = str(record_id)
    else:
        data.pop(EXECUTION_RECORD_ID_KEY, None)
    task.extra_data = data


async def resolve_tool_package_version_id(
    db: AsyncSession,
    *,
    tool_slug: str,
    tool_version: str,
) -> str | None:
    """Resolve the immutable package version that matches a ToolVersion."""
    result = await db.execute(
        select(ToolPackageVersion.id)
        .join(ToolPackage, ToolPackage.id == ToolPackageVersion.package_id)
        .where(
            ToolPackage.slug == tool_slug,
            ToolPackageVersion.version == tool_version,
        )
    )
    return result.scalar_one_or_none()


async def start_task_execution_record(
    db: AsyncSession,
    *,
    task: Any,
    tool_slug: str,
    tool_version_id: str,
    tool_version: str,
    tool_type: str,
    attempt_id: str | None,
    tool_config: Mapping[str, Any] | None = None,
) -> ExecutionRecord | None:
    """Create one durable attempt record when the task is package-backed."""
    project_id = task_project_id(task)
    requested_by = getattr(task, "user_id", None)
    if not project_id or not requested_by:
        return None

    try:
        adapter_type = execution_type_for_tool_type(tool_type)
    except ValueError:
        return None

    package_version_id = await resolve_tool_package_version_id(
        db,
        tool_slug=tool_slug,
        tool_version=tool_version,
    )
    if not package_version_id:
        return None

    attempt_key = str(attempt_id or "initial")
    idempotency_key = f"task:{task.id}:attempt:{attempt_key}"
    existing = await db.scalar(
        select(ExecutionRecord).where(
            ExecutionRecord.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        set_task_execution_record_id(task, str(existing.id))
        return existing

    record = ExecutionRecord(
        project_id=str(project_id),
        requested_by=str(requested_by),
        tool_package_version_id=str(package_version_id),
        adapter_type=adapter_type,
        idempotency_key=idempotency_key,
        status="running",
        started_at=utcnow(),
        request_snapshot={
            "task_id": str(task.id),
            "tool_id": str(getattr(task, "tool_id", "")),
            "tool_version_id": str(tool_version_id),
            "tool_slug": tool_slug,
            "tool_version": tool_version,
            "attempt_id": attempt_id,
            "executor_type": tool_type,
            "adapter_type": adapter_type,
            "parameters": _safe_parameters(tool_config),
        },
    )
    db.add(record)
    await db.flush()
    set_task_execution_record_id(task, str(record.id))
    return record


async def finish_task_execution_record(
    db: AsyncSession,
    *,
    task: Any,
    status: str,
    external_id: str | None = None,
    error_message: str | None = None,
) -> ExecutionRecord | None:
    """Update the current attempt record without creating a second record."""
    record_id = task_execution_record_id(task)
    if not record_id:
        return None

    record = await db.get(ExecutionRecord, record_id)
    if record is None:
        return None
    record.status = status
    record.external_id = external_id or record.external_id
    record.error_message = error_message
    record.finished_at = utcnow()
    return record


def _safe_parameters(tool_config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep request snapshots free of runtime credentials and connection data."""
    if not isinstance(tool_config, Mapping):
        return {}
    allowed = {"timeout_sec", "gpu_required", "gpu_memory_required_mb", "mode"}
    return {key: tool_config[key] for key in allowed if key in tool_config}
