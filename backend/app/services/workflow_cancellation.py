"""Workflow cancellation state helpers."""

from __future__ import annotations

from typing import Any

from app.common.time import utcnow
from app.models.workflows import WorkflowRun


WORKFLOW_RUN_ACTIVE_NODE_STATUSES = {"pending", "ready", "running", "waiting_task"}
# 已终结的节点状态：取消 run 时不得再改动它们（blocked 同样是终态，等待人工介入）。
WORKFLOW_TERMINAL_NODE_STATUSES = frozenset(
    {"success", "failure", "skipped", "blocked", "canceled"}
)


def is_active_workflow_node_status(status: Any) -> bool:
    normalized = str(status or "").lower()
    if normalized in WORKFLOW_TERMINAL_NODE_STATUSES:
        return False
    return normalized in WORKFLOW_RUN_ACTIVE_NODE_STATUSES


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


def mark_workflow_run_canceled(
    run: WorkflowRun,
    *,
    finished_at: str,
) -> list[str]:
    node_states = dict(run.node_states or {})
    task_ids: list[str] = []

    for node_id, raw_state in node_states.items():
        state = dict(raw_state or {})
        task_ids.extend(mark_active_workflow_state_canceled(state, finished_at=finished_at))
        node_states[node_id] = state

    run.status = "canceled"
    run.node_states = node_states
    run.finished_at = utcnow()
    run.error_message = None
    return task_ids
