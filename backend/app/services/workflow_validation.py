"""Workflow definition validation helpers."""

from __future__ import annotations

from typing import Any

from app.common.exceptions import ValidationException
from app.services.semantic_types import normalize_semantic_type


def workflow_nodes(definition: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = definition.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValidationException("Workflow definition must include nodes")
    return [node for node in nodes if isinstance(node, dict)]


def workflow_edges(definition: dict[str, Any]) -> list[dict[str, Any]]:
    edges = definition.get("edges", [])
    if not isinstance(edges, list):
        raise ValidationException("Workflow definition edges must be a list")
    return [edge for edge in edges if isinstance(edge, dict)]


def node_id(node: dict[str, Any]) -> str:
    return str(node.get("id") or "")


def nodes_by_id(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node_id(node): node for node in workflow_nodes(definition)}


def is_tool_node(node: dict[str, Any] | None) -> bool:
    if not node:
        return False
    node_kind = str(node.get("kind") or node.get("type") or "")
    return node_kind == "tool" or bool(node.get("tool_slug") or node.get("tool_id"))


def semantic_node_dependency_ids(
    node: dict[str, Any],
    *,
    node_id_set: set[str],
) -> set[str]:
    dependencies: set[str] = set()
    for source in (node.get("semantic_inputs") or {}).values():
        if not isinstance(source, str) or not source.startswith("node:"):
            continue
        parts = source.split(":", 2)
        if len(parts) != 3 or parts[1] not in node_id_set:
            raise ValidationException(f"Workflow semantic input references unknown node: {source}")
        dependencies.add(parts[1])
    return dependencies


def workflow_dependency_map(definition: dict[str, Any]) -> dict[str, set[str]]:
    nodes = workflow_nodes(definition)
    node_ids = [node_id(node) for node in nodes]
    node_id_set = set(node_ids)
    if any(not current_node_id for current_node_id in node_ids):
        raise ValidationException("Workflow node id is required")
    if len(node_ids) != len(set(node_ids)):
        raise ValidationException("Workflow node ids must be unique")

    dependencies = {current_node_id: set() for current_node_id in node_ids}

    for edge in workflow_edges(definition):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in node_id_set or target not in node_id_set:
            raise ValidationException("Workflow edge references unknown node")
        dependencies[target].add(source)

    for node in nodes:
        target = node_id(node)
        dependencies[target].update(
            semantic_node_dependency_ids(node, node_id_set=node_id_set)
        )

    return dependencies


def validate_workflow_definition(definition: dict[str, Any]) -> list[str]:
    nodes = workflow_nodes(definition)
    node_ids = [node_id(node) for node in nodes]
    dependencies = workflow_dependency_map(definition)
    adjacency = {current_node_id: [] for current_node_id in node_ids}
    indegree = {current_node_id: 0 for current_node_id in node_ids}

    for target, sources in dependencies.items():
        indegree[target] = len(sources)
        for source in sources:
            adjacency[source].append(target)

    ready = [current_node_id for current_node_id in node_ids if indegree[current_node_id] == 0]
    ordered: list[str] = []
    while ready:
        current_node_id = ready.pop(0)
        ordered.append(current_node_id)
        for target in adjacency[current_node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)

    if len(ordered) != len(node_ids):
        raise ValidationException("Workflow definition contains a cycle")

    indexed_nodes = {node_id(node): node for node in nodes}
    return [
        current_node_id
        for current_node_id in ordered
        if is_tool_node(indexed_nodes[current_node_id])
    ]


def required_workflow_inputs(definition: dict[str, Any]) -> set[str]:
    required_inputs: set[str] = set()
    for node in workflow_nodes(definition):
        for source in (node.get("semantic_inputs") or {}).values():
            if not isinstance(source, str) or not source.startswith("workflow_input:"):
                continue
            semantic_type = source.split(":", 1)[1]
            if semantic_type:
                required_inputs.add(normalize_semantic_type(semantic_type))
    return required_inputs
