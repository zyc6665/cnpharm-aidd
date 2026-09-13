"""Workflow map scheduling module tests."""

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
from app.services.workflow_map_scheduler import (  # noqa: E402
    reconcile_map_sub_tasks,
    schedule_map_node,
)


@pytest.mark.asyncio
async def test_schedule_map_node_rejects_missing_over():
    node_states = {"map": {"status": "pending"}}

    with pytest.raises(ValidationException, match="missing 'over'"):
        await schedule_map_node(
            None,
            current_user=None,
            run=WorkflowRun(),
            node_id="map",
            node={"id": "map", "kind": "map"},
            node_states=node_states,
            schedule_task_fn=None,
        )


@pytest.mark.asyncio
async def test_reconcile_map_sub_tasks_returns_false_without_sub_tasks():
    state = {"status": "waiting_task"}
    node_states = {"map": state}

    changed = await reconcile_map_sub_tasks(
        None,
        node_id="map",
        state=state,
        node_states=node_states,
        run=WorkflowRun(),
    )

    assert changed is False
    assert node_states["map"] == {"status": "waiting_task"}
