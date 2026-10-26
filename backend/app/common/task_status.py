"""Canonical mappings between task, API, and execution statuses."""

from __future__ import annotations

from typing import Any


_TASK_STATUS_TO_API = {
    "PENDING": "pending",
    "QUEUED": "queued",
    "RUNNING": "running",
    "SUCCESS": "success",
    "FAILURE": "failure",
    "TIMEOUT": "timeout",
    "CANCELED": "canceled",
}

# 任务状态 -> 执行器中性状态。
# 注意：PENDING 表示「已创建但尚未入队」，因此映射为 created 而不是 queued；
# queued 专指已进入调度队列（含资源不足重新排队）的 QUEUED 状态。
_TASK_STATUS_TO_EXECUTION = {
    "PENDING": "created",
    "QUEUED": "queued",
    "RUNNING": "running",
    "SUCCESS": "succeeded",
    "FAILURE": "failed",
    "TIMEOUT": "timeout",
    "CANCELED": "cancelled",
}

_EXECUTION_STATUS_TO_TASK = {
    execution_status: task_status
    for task_status, execution_status in _TASK_STATUS_TO_EXECUTION.items()
}
# 执行器/外部系统使用的同义写法，逐条显式补齐（不做大小写猜测）。
_EXECUTION_STATUS_TO_TASK["canceled"] = "CANCELED"
# created/queued/timeout 的反查同样显式声明，避免「PENDING 与 QUEUED 共用 queued」的历史歧义。
_EXECUTION_STATUS_TO_TASK["created"] = "PENDING"
_EXECUTION_STATUS_TO_TASK["queued"] = "QUEUED"
_EXECUTION_STATUS_TO_TASK["timeout"] = "TIMEOUT"
_EXECUTION_STATUS_TO_TASK["timed_out"] = "TIMEOUT"


def _task_status_key(value: Any) -> str:
    return str(getattr(value, "value", value) or "").upper()


def task_status_to_api(value: Any) -> str | None:
    """Map a persisted TaskStatus to the existing API vocabulary."""
    if value is None:
        return None
    key = _task_status_key(value)
    return _TASK_STATUS_TO_API.get(key, str(value).lower())


def task_status_to_execution_state(value: Any) -> str | None:
    """Map a persisted TaskStatus to the executor-neutral vocabulary."""
    if value is None:
        return None
    key = _task_status_key(value)
    return _TASK_STATUS_TO_EXECUTION.get(key)


def execution_state_to_task_status(value: Any) -> str | None:
    """Map an execution state back to the persisted TaskStatus vocabulary."""
    if value is None:
        return None
    key = str(getattr(value, "value", value) or "").lower()
    return _EXECUTION_STATUS_TO_TASK.get(key)
