"""Task execution record lifecycle for package-backed external runs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
import logging
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.task_context import task_extra_data, task_project_id
from app.common.task_status import task_status_to_execution_state
from app.common.time import utcnow
from app.execution.executor_types import execution_type_for_tool_type
from app.models.executions import ExecutionRecord
from app.models.tasks import Task
from app.models.tool_packages import ToolPackage, ToolPackageVersion


logger = logging.getLogger(__name__)

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


def task_external_execution_id(task: Any) -> str | None:
    """Read an adapter-owned external run handle from task metadata."""
    data = task_extra_data(task)
    for key in ("external_id", "remote_run_id"):
        value = data.get(key)
        if value:
            return str(value)
    return None


async def task_execution_record_external_id(
    db: AsyncSession,
    *,
    task: Any,
) -> str | None:
    """Read the external handle already persisted for the current task attempt."""
    record_id = task_execution_record_id(task)
    if not record_id:
        return None

    record = await db.get(ExecutionRecord, record_id)
    value = getattr(record, "external_id", None) if record is not None else None
    normalized_value = str(value or "").strip()
    return normalized_value or None


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
    record.external_id = external_id or task_external_execution_id(task) or record.external_id
    record.error_message = error_message
    record.finished_at = utcnow()
    return record


async def finish_task_execution_record_best_effort(
    *,
    task: Any,
    status: str,
    external_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Persist terminal observability state without sharing the task transaction."""
    if not task_execution_record_id(task):
        return

    from app.database.session import async_session_factory

    try:
        async with async_session_factory() as session:
            try:
                await finish_task_execution_record(
                    session,
                    task=task,
                    status=status,
                    external_id=external_id,
                    error_message=error_message,
                )
                await session.commit()
            except Exception as exc:
                try:
                    await session.rollback()
                except Exception as rollback_exc:
                    logger.debug(
                        "执行记录会话回滚失败: %s",
                        rollback_exc,
                    )
                logger.warning(
                    "任务 %s 执行记录收尾失败，继续保留任务结果: %s",
                    getattr(task, "id", "<unknown>"),
                    exc,
                )
    except Exception as exc:
        logger.warning(
            "任务 %s 执行记录收尾失败，继续保留任务结果: %s",
            getattr(task, "id", "<unknown>"),
            exc,
        )


async def update_task_execution_record_external_id(
    db: AsyncSession,
    *,
    task: Any,
    external_id: str,
) -> ExecutionRecord | None:
    """Persist an adapter-owned external handle without changing record state."""
    record_id = task_execution_record_id(task)
    normalized_external_id = str(external_id or "").strip()
    if not record_id or not normalized_external_id:
        return None

    record = await db.get(ExecutionRecord, record_id)
    if record is None:
        return None
    record.external_id = normalized_external_id
    return record


async def touch_task_execution_record_best_effort(
    *,
    task: Any,
    now: datetime | None = None,
) -> None:
    """Refresh a running execution record heartbeat without sharing task state."""
    record_id = task_execution_record_id(task)
    if not record_id:
        return

    from app.database.session import async_session_factory

    try:
        async with async_session_factory() as session:
            record = await session.get(ExecutionRecord, record_id)
            if record is None or record.status != "running":
                return
            record.updated_at = now or utcnow()
            await session.commit()
    except Exception as exc:
        logger.warning(
            "任务 %s 执行记录心跳写入失败，继续保留主执行链: %s",
            getattr(task, "id", "<unknown>"),
            exc,
        )


async def reconcile_running_execution_records(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    stale_after: timedelta | None = timedelta(hours=24),
    batch_size: int = 100,
) -> int:
    """Converge running records after a worker or process interruption."""
    current_time = now or utcnow()
    cutoff = current_time - stale_after if stale_after is not None else None
    task_id_expression = ExecutionRecord.request_snapshot["task_id"].as_string()
    result = await db.execute(
        select(ExecutionRecord)
        .outerjoin(Task, Task.id == task_id_expression)
        .where(
            ExecutionRecord.status == "running",
            or_(Task.id.is_(None), Task.status != "RUNNING"),
        )
        .order_by(ExecutionRecord.started_at.asc())
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    )
    records = result.scalars().all()
    reconciled_count = 0

    for record in records:
        task_id = _record_task_id(record)
        if not task_id:
            _finish_reconciled_record(
                record,
                status="failed",
                error_message="执行记录缺少任务关联",
                finished_at=current_time,
            )
            reconciled_count += 1
            continue

        task = await db.get(Task, task_id)
        if task is None:
            _finish_reconciled_record(
                record,
                status="failed",
                error_message="关联任务不存在",
                finished_at=current_time,
            )
            reconciled_count += 1
            continue

        execution_status = task_status_to_execution_state(task.status)
        if execution_status in {"succeeded", "failed", "cancelled", "timeout"}:
            _finish_reconciled_record(
                record,
                status=execution_status,
                error_message=(
                    task.error_message
                    if execution_status in {"failed", "timeout"}
                    else None
                ),
                finished_at=task.finished_at or current_time,
            )
            reconciled_count += 1
            continue

        if str(getattr(task.status, "value", task.status)) == "RUNNING":
            # 没有心跳字段时不能仅凭年龄否定正常长任务。
            continue

        record_started_at = getattr(record, "started_at", None) or getattr(
            record,
            "created_at",
            None,
        )
        if cutoff is not None and record_started_at is not None and record_started_at <= cutoff:
            _finish_reconciled_record(
                record,
                status="failed",
                error_message="执行记录超过保留运行时间",
                finished_at=current_time,
            )
            reconciled_count += 1

    if reconciled_count:
        await db.flush()
    return reconciled_count


def _record_task_id(record: Any) -> str | None:
    snapshot = getattr(record, "request_snapshot", None)
    if not isinstance(snapshot, Mapping):
        return None
    value = snapshot.get("task_id")
    return str(value) if value else None


def _finish_reconciled_record(
    record: Any,
    *,
    status: str,
    error_message: str | None,
    finished_at: datetime,
) -> None:
    record.status = status
    record.error_message = error_message
    record.finished_at = finished_at


def _safe_parameters(tool_config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep request snapshots free of runtime credentials and connection data."""
    if not isinstance(tool_config, Mapping):
        return {}
    allowed = {"timeout_sec", "gpu_required", "gpu_memory_required_mb", "mode"}
    return {key: tool_config[key] for key in allowed if key in tool_config}
