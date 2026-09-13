"""Workflow condition expression evaluation."""

from __future__ import annotations

from typing import Any, Callable

from app.common.exceptions import ValidationException
from app.services.semantic_types import normalize_semantic_type


_CONDITION_OPERATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: _compare(a, b, lambda x, y: x > y),
    "<": lambda a, b: _compare(a, b, lambda x, y: x < y),
    ">=": lambda a, b: _compare(a, b, lambda x, y: x >= y),
    "<=": lambda a, b: _compare(a, b, lambda x, y: x <= y),
    "in": lambda a, b: a in b if isinstance(b, (list, tuple, str, set, dict)) else False,
    "contains": lambda a, b: b in a if isinstance(a, (list, tuple, str, set, dict)) else False,
}


def evaluate_condition_expression(
    expression: dict[str, Any],
    *,
    run: Any,
    node_states: dict[str, Any],
) -> bool:
    """Evaluate a workflow condition expression against run inputs and node state."""
    op = expression.get("op")
    if op not in _CONDITION_OPERATORS:
        raise ValidationException(f"Unsupported condition operator: {op}")

    left_value = _resolve_value(expression.get("left"), run=run, node_states=node_states)
    right_value = _resolve_value(expression.get("right"), run=run, node_states=node_states)

    try:
        return bool(_CONDITION_OPERATORS[op](left_value, right_value))
    except Exception as exc:
        raise ValidationException(
            f"Condition evaluation failed: {op}({left_value!r}, {right_value!r}): {exc}"
        ) from exc


def _compare(left: Any, right: Any, op: Callable[[Any, Any], bool]) -> bool:
    try:
        return op(left, right)
    except TypeError as exc:
        raise ValidationException(
            f"Cannot compare values of types {type(left).__name__} and {type(right).__name__}"
        ) from exc


def _resolve_value(
    ref: Any,
    *,
    run: Any,
    node_states: dict[str, Any],
) -> Any:
    if not isinstance(ref, str):
        return ref

    if ref.startswith("workflow_input:"):
        semantic_key = ref.split(":", 1)[1]
        return (getattr(run, "input_files", None) or {}).get(semantic_key)

    if ref.startswith("node:"):
        parts = ref.split(":", 2)
        if len(parts) != 3:
            raise ValidationException(f"Invalid node reference: {ref}")
        source_node_id = parts[1]
        source_semantic_type = normalize_semantic_type(parts[2])
        source_state = node_states.get(source_node_id) or {}
        source_output = (source_state.get("semantic_outputs") or {}).get(source_semantic_type)
        if not source_output:
            return None
        return source_output.get("value", source_output.get("file_id"))

    return ref
