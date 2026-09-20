"""Compatibility accessors for task execution context."""

from __future__ import annotations

from typing import Any


PROJECT_ID_KEY = "project_id"


def task_extra_data(task: Any) -> dict[str, Any]:
    """Return task metadata as a defensive dictionary."""
    data = getattr(task, "extra_data", None)
    return dict(data) if isinstance(data, dict) else {}


def task_project_id(task: Any) -> str | None:
    """Read the legacy project context from a task without leaking JSON details."""
    value = task_extra_data(task).get(PROJECT_ID_KEY)
    return str(value) if value else None


def set_task_project_id(
    extra_data: dict[str, Any] | None,
    project_id: str | None,
) -> dict[str, Any]:
    """Return task metadata with the compatibility project context applied."""
    data = dict(extra_data or {})
    if project_id:
        data[PROJECT_ID_KEY] = str(project_id)
    else:
        data.pop(PROJECT_ID_KEY, None)
    return data
