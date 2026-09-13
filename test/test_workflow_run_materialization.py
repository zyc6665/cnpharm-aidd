"""Workflow run definition materialization tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.workflow_run_materialization import (  # noqa: E402
    materialize_workflow_run_definition,
    workflow_requires_standard_binding_project,
)


@pytest.mark.asyncio
async def test_materialize_workflow_run_definition_preserves_non_tool_nodes():
    definition = {
        "nodes": [
            {"id": "input", "kind": "input"},
            {"id": "cond", "kind": "condition", "expression": {"op": "==", "left": 1, "right": 1}},
        ],
        "edges": [{"source": "input", "target": "cond"}],
    }

    materialized = await materialize_workflow_run_definition(None, definition=definition)

    assert materialized == definition
    assert materialized is not definition
    assert materialized["nodes"] is not definition["nodes"]


@pytest.mark.asyncio
async def test_workflow_requires_standard_binding_project_false_without_tool_nodes():
    definition = {"nodes": [{"id": "input", "kind": "input"}], "edges": []}

    requires_project = await workflow_requires_standard_binding_project(None, definition)

    assert requires_project is False
