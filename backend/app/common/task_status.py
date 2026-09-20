"""Canonical mappings between task, API, and execution statuses."""

from __future__ import annotations

from typing import Any


_TASK_STATUS_TO_API = {
    "PENDING": "pending",
    "RUNNING": "running",
    "SUCCESS": "success",
    "FAILURE": "failure",
    "CANCELED": "canceled",
}

_TASK_STATUS_TO_EXECUTION = {
    "PENDING": "queued",
    "RUNNING": "running",
    "SUCCESS": "succeeded",
    "FAILURE": "failed",
    "CANCELED": "cancelled",
}

_EXECUTION_STATUS_TO_TASK = {
    execution_status: task_status
    for task_status, execution_status in _TASK_STATUS_TO_EXECUTION.items()
}
_EXECUTION_STATUS_TO_TASK["canceled"] = "CANCELED"


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
