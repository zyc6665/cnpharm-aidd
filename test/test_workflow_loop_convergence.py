"""Workflow loop convergence tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.workflow_loop_convergence import (  # noqa: E402
    evaluate_loop_convergence,
    resolve_loop_value,
)


def test_evaluate_loop_convergence_reads_body_node_output() -> None:
    converged = evaluate_loop_convergence(
        {"op": "<", "left": "node:scoring:delta", "right": 0.01},
        body_states={"scoring": {"result": {"delta": 0.005}}},
    )

    assert converged is True


def test_evaluate_loop_convergence_treats_type_mismatch_as_not_converged() -> None:
    converged = evaluate_loop_convergence(
        {"op": ">", "left": "node:scoring:delta", "right": 0.01},
        body_states={"scoring": {"result": {"delta": "not-a-number"}}},
    )

    assert converged is False


def test_resolve_loop_value_returns_none_for_missing_output() -> None:
    assert resolve_loop_value(
        "node:scoring:missing",
        {"scoring": {"result": {"delta": 0.1}}},
    ) is None
