"""Workflow condition scheduling tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.exceptions import ValidationException  # noqa: E402
from app.models.workflows import WorkflowRun  # noqa: E402
from app.services.workflow_condition_scheduler import schedule_condition_node  # noqa: E402


@pytest.mark.asyncio
async def test_condition_scheduler_marks_inactive_branch_descendants_skipped():
    definition = {
        "nodes": [
            {"id": "cond", "kind": "condition", "expression": {"op": "==", "left": "x", "right": "x"}},
            {"id": "active_tool", "kind": "tool", "tool_slug": "active"},
            {"id": "inactive_tool", "kind": "tool", "tool_slug": "inactive"},
            {"id": "inactive_child", "kind": "tool", "tool_slug": "child"},
        ],
        "edges": [
            {"source": "cond", "target": "active_tool", "branch": "true"},
            {"source": "cond", "target": "inactive_tool", "branch": "false"},
            {"source": "inactive_tool", "target": "inactive_child"},
        ],
    }
    run = WorkflowRun(definition=definition, input_files={})
    node_states = {
        "cond": {"status": "pending"},
        "active_tool": {"status": "pending"},
        "inactive_tool": {"status": "pending"},
        "inactive_child": {"status": "pending"},
    }

    scheduled = await schedule_condition_node(
        run=run,
        node_id="cond",
        node={"id": "cond", "kind": "condition", "expression": {"op": "==", "left": "x", "right": "x"}},
        node_states=node_states,
    )

    assert scheduled is True
    assert node_states["cond"]["status"] == "success"
    assert node_states["cond"]["active_branch"] == "true"
    assert node_states["active_tool"]["status"] == "pending"
    assert node_states["inactive_tool"]["status"] == "skipped"
    assert node_states["inactive_child"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_condition_scheduler_rejects_missing_expression():
    run = WorkflowRun(definition={"nodes": [], "edges": []}, input_files={})
    node_states = {"cond": {"status": "pending"}}

    with pytest.raises(ValidationException, match="missing expression"):
        await schedule_condition_node(
            run=run,
            node_id="cond",
            node={"id": "cond", "kind": "condition"},
            node_states=node_states,
        )
