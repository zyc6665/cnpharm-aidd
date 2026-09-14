"""Workflow run retry state helpers."""

from __future__ import annotations

from app.common.exceptions import NotFoundException, ValidationException
from app.models.workflows import WorkflowRun
from app.services.workflow_node_states import initial_node_states
from app.services.workflow_validation import nodes_by_id


def prepare_workflow_node_retry(run: WorkflowRun, *, node_id: str) -> None:
    if run.status == "canceled":
        raise ValidationException("Cannot retry a canceled workflow run")

    definition = dict(run.definition or {})
    indexed_nodes = nodes_by_id(definition)
    if node_id not in indexed_nodes:
        raise NotFoundException("Workflow node not found")

    node_states = dict(run.node_states or {})
    current_state = dict(node_states.get(node_id) or {})
    if current_state.get("status") != "failure":
        raise ValidationException("Only failed workflow nodes can be retried")

    initial_states = initial_node_states(definition, list(run.execution_order or []))
    node_states[node_id] = dict(initial_states.get(node_id) or {"status": "pending"})

    artifact_lineage = dict(run.artifact_lineage or {})
    artifact_lineage.pop(node_id, None)

    run.status = "pending"
    run.error_message = None
    run.finished_at = None
    run.node_states = node_states
    run.artifact_lineage = artifact_lineage
