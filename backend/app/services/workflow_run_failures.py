"""Workflow run failure state helpers."""

from __future__ import annotations

from typing import Any

from app.common.time import utcnow, utcnow_iso
from app.models.workflows import WorkflowRun


def mark_workflow_node_failed(
    run: WorkflowRun,
    *,
    node_states: dict[str, Any],
    node_id: str,
    state: dict[str, Any],
    error_message: str,
    missing_outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state["status"] = "failure"
    state["error_message"] = error_message
    if missing_outputs is not None:
        state["missing_outputs"] = missing_outputs
    state["finished_at"] = utcnow_iso()
    node_states[node_id] = state
    run.status = "failure"
    run.error_message = error_message
    run.finished_at = utcnow()
    return state
