"""Backward-compatible task context imports."""

from app.common.task_context import (
    PROJECT_ID_KEY,
    set_task_project_id,
    task_extra_data,
    task_project_id,
)

__all__ = [
    "PROJECT_ID_KEY",
    "set_task_project_id",
    "task_extra_data",
    "task_project_id",
]
