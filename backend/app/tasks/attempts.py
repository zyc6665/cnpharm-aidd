"""Execution attempt helpers shared by task dispatchers and workers."""

from __future__ import annotations

import inspect
from typing import Any
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.models.tasks import Task, TaskStatus


EXECUTION_ATTEMPT_KEY = "execution_attempt_id"
EXECUTION_CONTROL_KEY = "execution_control"
CANCELLATION_PENDING_STATES = frozenset({"cancel_requested", "cancel_timeout"})


def new_execution_attempt_id() -> str:
    return uuid4().hex


def get_execution_attempt_id(task: Any) -> str | None:
    extra_data = task.extra_data if isinstance(task.extra_data, dict) else {}
    value = extra_data.get(EXECUTION_ATTEMPT_KEY)
    return value if isinstance(value, str) and value else None


def set_execution_attempt_id(task: Any, attempt_id: str) -> None:
    extra_data = dict(task.extra_data) if isinstance(task.extra_data, dict) else {}
    extra_data[EXECUTION_ATTEMPT_KEY] = attempt_id
    task.extra_data = extra_data


def get_execution_control(task: Any) -> dict[str, Any]:
    extra_data = task.extra_data if isinstance(task.extra_data, dict) else {}
    control = extra_data.get(EXECUTION_CONTROL_KEY)
    return dict(control) if isinstance(control, dict) else {}


def mark_task_cancellation_requested(
    task: Any,
    *,
    attempt_id: str | None = None,
    reason: str = "user_requested",
) -> None:
    """Record that the current execution must stop before a retry is allowed."""
    current_attempt_id = attempt_id or get_execution_attempt_id(task)
    extra_data = dict(task.extra_data) if isinstance(task.extra_data, dict) else {}
    extra_data[EXECUTION_CONTROL_KEY] = {
        "state": "cancel_requested",
        "attempt_id": current_attempt_id,
        "requested_at": utcnow().isoformat(),
        "reason": reason,
    }
    task.extra_data = extra_data


def mark_task_cancellation_timed_out(
    task: Any,
    *,
    timed_out_at: str | None = None,
    reason: str = "worker_exit_not_confirmed",
) -> None:
    """Mark a canceled attempt as requiring manual intervention."""
    control = get_execution_control(task)
    if not control or control.get("state") != "cancel_requested":
        return
    extra_data = dict(task.extra_data) if isinstance(task.extra_data, dict) else {}
    extra_data[EXECUTION_CONTROL_KEY] = {
        **control,
        "state": "cancel_timeout",
        "timed_out_at": timed_out_at or utcnow().isoformat(),
        "timeout_reason": reason,
        "manual_intervention_required": True,
    }
    task.extra_data = extra_data


def mark_task_execution_released(
    task: Any,
    *,
    attempt_id: str | None = None,
    reason: str | None = None,
) -> None:
    """Mark the canceled attempt safe for a subsequent retry."""
    control = get_execution_control(task)
    if not control or control.get("state") not in CANCELLATION_PENDING_STATES:
        return
    controlled_attempt_id = control.get("attempt_id")
    if attempt_id and controlled_attempt_id and controlled_attempt_id != attempt_id:
        return
    extra_data = dict(task.extra_data) if isinstance(task.extra_data, dict) else {}
    extra_data[EXECUTION_CONTROL_KEY] = {
        **control,
        "state": "released",
        "released_at": utcnow().isoformat(),
        "release_reason": reason,
    }
    task.extra_data = extra_data


def is_task_cancellation_pending(task: Any) -> bool:
    return get_execution_control(task).get("state") in CANCELLATION_PENDING_STATES


def clear_task_execution_control(task: Any) -> None:
    extra_data = dict(task.extra_data) if isinstance(task.extra_data, dict) else {}
    if EXECUTION_CONTROL_KEY in extra_data:
        extra_data.pop(EXECUTION_CONTROL_KEY, None)
        task.extra_data = extra_data


async def commit_current_attempt(
    db: AsyncSession,
    *,
    task: Task,
    attempt_id: str | None,
    expected_status: TaskStatus | str,
) -> bool:
    """仅在当前执行 attempt 仍有效时提交任务变更。"""
    if attempt_id is None:
        await db.commit()
        return True

    expected_status_value = (
        expected_status.value
        if isinstance(expected_status, TaskStatus)
        else expected_status
    )
    task_values = {
        "status": task.status,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "execution_time_sec": task.execution_time_sec,
        "progress": task.progress,
        "progress_message": task.progress_message,
        "error_message": task.error_message,
        "retry_count": task.retry_count,
        "gpu_node_id": task.gpu_node_id,
        "gpu_index": task.gpu_index,
        "gpu_memory_allocated_mb": task.gpu_memory_allocated_mb,
        "extra_data": task.extra_data,
    }

    with db.no_autoflush:
        result = await db.execute(
            update(Task)
            .where(
                Task.id == task.id,
                Task.status == expected_status_value,
                Task.extra_data[EXECUTION_ATTEMPT_KEY].as_string() == attempt_id,
            )
            .values(**task_values)
            .execution_options(synchronize_session=False)
        )

    if result.rowcount != 1:
        await db.rollback()
        return False

    await db.commit()
    return True


def invoke_with_optional_attempt(callback: Any, *, attempt_id: str, **kwargs: Any) -> Any:
    """Call legacy two-argument dispatchers without forcing an API break."""
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        parameters = ()

    accepts_attempt = any(
        parameter.name == "attempt_id"
        or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )
    if accepts_attempt:
        kwargs["attempt_id"] = attempt_id
    return callback(**kwargs)
