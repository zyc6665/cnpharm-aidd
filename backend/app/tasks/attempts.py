"""Execution attempt helpers shared by task dispatchers and workers."""

from __future__ import annotations

import inspect
from typing import Any
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tasks import Task, TaskStatus


EXECUTION_ATTEMPT_KEY = "execution_attempt_id"


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
