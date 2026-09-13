"""Workflow loop scheduling module tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.workflows import WorkflowRun  # noqa: E402
from app.services.workflow_loop_scheduler import (  # noqa: E402
    reconcile_loop_body,
    schedule_loop_node,
)


@pytest.mark.asyncio
async def test_schedule_loop_node_marks_empty_body_failure():
    node_states = {"loop": {"status": "pending"}}

    scheduled = await schedule_loop_node(
        None,
        current_user=None,
        run=WorkflowRun(),
        node_id="loop",
        node={"id": "loop", "kind": "loop", "body": []},
        node_states=node_states,
        schedule_task_fn=None,
    )

    assert scheduled is False
    assert node_states["loop"]["status"] == "failure"
    assert node_states["loop"]["error_message"] == "Loop node has no body nodes"


@pytest.mark.asyncio
async def test_reconcile_loop_body_returns_false_without_body_states():
    state = {"status": "waiting_task"}
    node_states = {"loop": state}

    changed = await reconcile_loop_body(
        None,
        node_id="loop",
        node={"id": "loop", "kind": "loop", "body": []},
        state=state,
        node_states=node_states,
        run=WorkflowRun(),
    )

    assert changed is False
    assert node_states["loop"] == {"status": "waiting_task"}
