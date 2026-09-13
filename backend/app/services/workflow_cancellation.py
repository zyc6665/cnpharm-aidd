"""Workflow cancellation state helpers."""

from __future__ import annotations

from typing import Any


WORKFLOW_RUN_ACTIVE_NODE_STATUSES = {"pending", "ready", "running", "waiting_task"}


def is_active_workflow_node_status(status: Any) -> bool:
    return str(status or "").lower() in WORKFLOW_RUN_ACTIVE_NODE_STATUSES


def mark_active_workflow_state_canceled(
    state: dict[str, Any],
    *,
    finished_at: str,
) -> list[str]:
    task_ids: list[str] = []

    if is_active_workflow_node_status(state.get("status")):
        task_id = state.get("task_id")
        if task_id:
            task_ids.append(str(task_id))
        state["status"] = "canceled"
        state["finished_at"] = finished_at

    for nested_key in ("sub_tasks", "loop_body_states"):
        nested_states = {
            key: dict(value)
            for key, value in (state.get(nested_key) or {}).items()
            if isinstance(value, dict)
        }
        if not nested_states:
            continue
        for nested_id, nested_state in nested_states.items():
            if is_active_workflow_node_status(nested_state.get("status")):
                task_id = nested_state.get("task_id")
                if task_id:
                    task_ids.append(str(task_id))
                nested_state["status"] = "canceled"
                nested_state["finished_at"] = finished_at
            nested_states[nested_id] = nested_state
        state[nested_key] = nested_states

    return task_ids
