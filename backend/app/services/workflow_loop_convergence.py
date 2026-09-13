"""Workflow loop convergence evaluation."""

from __future__ import annotations

from typing import Any, Callable


_LOOP_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
    "<": lambda left, right: left < right,
    ">": lambda left, right: left > right,
    "<=": lambda left, right: left <= right,
    ">=": lambda left, right: left >= right,
    "in": lambda left, right: left in right,
    "contains": lambda left, right: right in left,
}


def evaluate_loop_convergence(
    condition: dict[str, Any] | None,
    *,
    body_states: dict[str, Any],
    previous_iteration_outputs: dict[str, Any] | None = None,
) -> bool:
    """Evaluate whether a loop node should stop after the current iteration."""
    if not condition:
        if previous_iteration_outputs and body_states:
            return body_states == previous_iteration_outputs
        return False

    op = str(condition.get("op") or "")
    compare = _LOOP_OPERATORS.get(op)
    if compare is None:
        return False

    left = resolve_loop_value(condition.get("left"), body_states)
    right = resolve_loop_value(condition.get("right"), body_states)
    try:
        return bool(compare(left, right))
    except TypeError:
        return False


def resolve_loop_value(raw: Any, body_states: dict[str, Any]) -> Any:
    """Resolve a loop convergence literal or ``node:<body_node_id>:<output_key>`` reference."""
    if isinstance(raw, str) and raw.startswith("node:"):
        parts = raw.split(":", 2)
        if len(parts) != 3:
            return raw
        node_ref = parts[1]
        output_key = parts[2]
        node_state = body_states.get(node_ref, {})
        outputs = node_state.get("outputs") or node_state.get("result") or {}
        if isinstance(outputs, dict):
            return outputs.get(output_key)
        return None
    return raw
