"""Workflow node state initialization helpers."""

from __future__ import annotations

from typing import Any

from app.services.workflow_validation import nodes_by_id


def initial_node_states(definition: dict[str, Any], execution_order: list[str]) -> dict[str, Any]:
    indexed_nodes = nodes_by_id(definition)
    return {
        current_node_id: {
            "status": "pending",
            "tool_slug": indexed_nodes[current_node_id].get("tool_slug"),
            "tool_id": indexed_nodes[current_node_id].get("tool_id"),
            "tool_version_id": (
                indexed_nodes[current_node_id].get("tool_version") or {}
            ).get("id"),
            "tool_version": indexed_nodes[current_node_id].get("tool_version"),
            "semantic_inputs": dict(indexed_nodes[current_node_id].get("semantic_inputs") or {}),
            "artifact_inputs": dict(indexed_nodes[current_node_id].get("artifact_inputs") or {}),
            "artifact_input_slots": list(
                indexed_nodes[current_node_id].get("artifact_input_slots") or []
            ),
            "artifact_outputs": list(indexed_nodes[current_node_id].get("artifact_outputs") or []),
            "params": dict(indexed_nodes[current_node_id].get("params") or {}),
        }
        for current_node_id in execution_order
    }
