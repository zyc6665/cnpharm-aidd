"""Workflow run definition materialization tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import workflow_run_materialization as materialization_mod  # noqa: E402
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


@pytest.mark.asyncio
async def test_materialize_snapshots_tool_version_for_loop_body(monkeypatch):
    """loop body 的 tool 节点也要在建 run 时记录 tool_version 快照。"""
    tool = SimpleNamespace(
        id="tool-1",
        slug="score",
        current_version_id="version-1",
        current_version=SimpleNamespace(version="1.0.0"),
    )

    async def fake_load(db, *, node):
        return tool

    monkeypatch.setattr(materialization_mod, "load_available_workflow_tool", fake_load)

    definition = {
        "nodes": [
            {
                "id": "loop",
                "kind": "loop",
                "body": [{"id": "score", "kind": "tool", "tool_slug": "score"}],
            }
        ],
        "edges": [],
    }

    materialized = await materialize_workflow_run_definition(None, definition=definition)

    assert materialized["nodes"][0]["body"][0]["tool_version"] == {
        "id": "version-1",
        "version": "1.0.0",
    }
    # 快照只写进物化副本，不回写调用方的原始定义。
    assert "tool_version" not in definition["nodes"][0]["body"][0]
