"""Workflow dependency readiness helpers."""

from __future__ import annotations

from typing import Any

from app.services.workflow_validation import (
    is_condition_node,
    is_tool_node,
    nodes_by_id,
    workflow_dependency_map,
    workflow_edges,
)


def dependency_tool_node_ids(definition: dict[str, Any], node_id: str) -> set[str]:
    indexed_nodes = nodes_by_id(definition)
    dependencies = workflow_dependency_map(definition)
    return {
        source
        for source in dependencies.get(node_id, set())
        if is_tool_node(indexed_nodes.get(source))
    }


def dependencies_satisfied(
    *,
    definition: dict[str, Any],
    node_states: dict[str, Any],
    node_id: str,
) -> bool:
    indexed_nodes = nodes_by_id(definition)

    for dependency_id in dependency_tool_node_ids(definition, node_id):
        if (node_states.get(dependency_id) or {}).get("status") != "success":
            return False

    for edge in workflow_edges(definition):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if target != node_id:
            continue
        branch = edge.get("branch")
        if not branch or not is_condition_node(indexed_nodes.get(source)):
            continue
        source_state = node_states.get(source) or {}
        if source_state.get("status") != "success":
            return False
        active_branch = source_state.get("active_branch")
        if active_branch and branch != active_branch:
            return False

    return True
