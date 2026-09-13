"""Workflow condition node scheduling."""

from __future__ import annotations

from typing import Any

from app.common.exceptions import ValidationException
from app.common.time import utcnow_iso
from app.models.workflows import WorkflowRun
from app.services.workflow_conditions import evaluate_condition_expression
from app.services.workflow_skip import mark_unreachable_nodes_skipped
from app.services.workflow_validation import workflow_edges


async def schedule_condition_node(
    *,
    run: WorkflowRun,
    node_id: str,
    node: dict[str, Any],
    node_states: dict[str, Any],
) -> bool:
    """Evaluate a condition node and skip inactive branch descendants."""
    expression = node.get("expression")
    if not expression:
        raise ValidationException(f"Condition node {node_id} missing expression")

    try:
        result = evaluate_condition_expression(
            expression,
            run=run,
            node_states=node_states,
        )
    except ValidationException:
        raise
    except Exception as exc:
        state = dict(node_states.get(node_id) or {})
        state.update({
            "status": "failure",
            "error_message": f"Condition evaluation error: {exc}",
            "finished_at": utcnow_iso(),
        })
        node_states[node_id] = state
        return False

    active_branch = "true" if result else "false"
    definition = dict(run.definition or {})

    for edge in workflow_edges(definition):
        if str(edge.get("source") or "") != node_id:
            continue
        branch = edge.get("branch")
        if not branch:
            continue
        target = str(edge.get("target") or "")
        if branch != active_branch:
            mark_unreachable_nodes_skipped(
                node_states,
                target,
                f"Branch '{branch}' not active",
                definition=definition,
            )

    state = dict(node_states.get(node_id) or {})
    state.update({
        "status": "success",
        "active_branch": active_branch,
        "result": result,
        "finished_at": utcnow_iso(),
    })
    node_states[node_id] = state
    return True
