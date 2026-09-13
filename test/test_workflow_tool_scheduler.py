"""Workflow tool node scheduling module tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.workflows import WorkflowRun  # noqa: E402
from app.services.workflow_tool_scheduler import schedule_workflow_node  # noqa: E402


@pytest.mark.asyncio
async def test_schedule_workflow_node_keeps_existing_task_waiting():
    node_states = {"score": {"status": "pending", "task_id": "task-1"}}

    scheduled = await schedule_workflow_node(
        None,
        current_user=None,
        run=WorkflowRun(),
        node_id="score",
        node={"id": "score", "kind": "tool", "tool_slug": "score"},
        node_states=node_states,
        schedule_task_fn=None,
    )

    assert scheduled is False
    assert node_states["score"] == {"status": "waiting_task", "task_id": "task-1"}
