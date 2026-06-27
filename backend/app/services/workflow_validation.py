"""Workflow definition validation helpers."""

from __future__ import annotations

from typing import Any

from app.common.exceptions import ValidationException
from app.services.semantic_types import normalize_semantic_type


NODE_KIND_CONDITION = "condition"
NODE_KIND_MAP = "map"
NODE_KIND_LOOP = "loop"


_ALLOWED_CONDITION_OPERATORS = {"==", "!=", ">", "<", ">=", "<=", "in", "contains"}


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


def _node_kind(node: dict[str, Any] | None) -> str:
    if not node:
        return ""
    return str(node.get("kind") or node.get("type") or "")


def is_condition_node(node: dict[str, Any] | None) -> bool:
    return _node_kind(node) == NODE_KIND_CONDITION


def is_map_node(node: dict[str, Any] | None) -> bool:
    return _node_kind(node) == NODE_KIND_MAP


def is_loop_node(node: dict[str, Any] | None) -> bool:
    return _node_kind(node) == NODE_KIND_LOOP


def is_control_flow_node(node: dict[str, Any] | None) -> bool:
    return is_condition_node(node) or is_map_node(node) or is_loop_node(node)


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
    indexed_nodes = {node_id(node): node for node in nodes}

    for edge in workflow_edges(definition):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in node_id_set or target not in node_id_set:
            raise ValidationException("Workflow edge references unknown node")
        # condition 节点的 true/false 分支边不参与默认依赖，由 scheduler 动态处理
        branch = edge.get("branch")
        if branch and is_condition_node(indexed_nodes.get(source)):
            continue
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
    executable_node_order: list[str] = []
    for current_node_id in ordered:
        current_node = indexed_nodes[current_node_id]
        if is_tool_node(current_node) or is_control_flow_node(current_node):
            executable_node_order.append(current_node_id)
            if is_condition_node(current_node):
                validate_condition_node(current_node)
            elif is_map_node(current_node):
                validate_map_node(current_node)
            elif is_loop_node(current_node):
                validate_loop_node(current_node)
    return executable_node_order


def validate_condition_node(node: dict[str, Any]) -> None:
    """校验 condition 节点必须包含合法表达式。"""
    expression = node.get("expression")
    if not expression:
        raise ValidationException(f"Condition node {node_id(node)} requires an expression")
    if not isinstance(expression, dict):
        raise ValidationException(f"Condition node {node_id(node)} expression must be a dict")
    op = expression.get("op")
    if op not in _ALLOWED_CONDITION_OPERATORS:
        raise ValidationException(
            f"Condition node {node_id(node)} unsupported operator: {op}"
        )


def validate_map_node(node: dict[str, Any]) -> None:
    """校验 map 节点。"""
    over = node.get("over")
    if not over:
        raise ValidationException(f"Map node {node_id(node)} requires 'over' field")
    max_parallelism = node.get("max_parallelism", 10)
    if not isinstance(max_parallelism, int) or max_parallelism < 1:
        raise ValidationException(
            f"Map node {node_id(node)} max_parallelism must be a positive integer"
        )


def validate_loop_node(node: dict[str, Any]) -> None:
    """校验 loop 节点。"""
    body = node.get("body")
    if not body or not isinstance(body, list) or len(body) == 0:
        raise ValidationException(
            f"Loop node {node_id(node)} requires non-empty 'body' field (list of node dicts)"
        )
    for i, body_node in enumerate(body):
        if not isinstance(body_node, dict):
            raise ValidationException(
                f"Loop node {node_id(node)} body[{i}] must be a node dict"
            )
        body_node_id = body_node.get("id")
        if not body_node_id:
            raise ValidationException(
                f"Loop node {node_id(node)} body[{i}] requires an 'id'"
            )
        if not is_tool_node(body_node):
            raise ValidationException(
                f"Loop node {node_id(node)} body[{i}] ({body_node_id}) must be a tool node"
            )
    max_iterations = node.get("max_iterations", 10)
    if not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValidationException(
            f"Loop node {node_id(node)} max_iterations must be a positive integer"
        )
    if max_iterations > 100:
        raise ValidationException(
            f"Loop node {node_id(node)} max_iterations cannot exceed 100"
        )
    convergence_condition = node.get("convergence_condition")
    if convergence_condition is not None:
        if not isinstance(convergence_condition, dict):
            raise ValidationException(
                f"Loop node {node_id(node)} convergence_condition must be a dict"
            )
        op = convergence_condition.get("op")
        if op not in _ALLOWED_CONDITION_OPERATORS:
            raise ValidationException(
                f"Loop node {node_id(node)} convergence_condition has unsupported operator: {op}"
            )


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
