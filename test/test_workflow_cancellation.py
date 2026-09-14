"""Workflow cancellation state helper tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.workflow_cancellation import (  # noqa: E402
    mark_active_workflow_state_canceled,
    mark_workflow_run_canceled,
)


def test_mark_active_workflow_state_canceled_handles_nested_active_tasks():
    state = {
        "status": "running",
        "task_id": "task-main",
        "sub_tasks": {
            "map[0]": {"status": "waiting_task", "task_id": "task-map-0"},
            "map[1]": {"status": "success", "task_id": "task-map-1"},
            "ignored": "not-a-state",
        },
        "loop_body_states": {
            "step": {"status": "ready", "task_id": "task-loop-step"},
        },
    }

    task_ids = mark_active_workflow_state_canceled(
        state,
        finished_at="2026-09-13T00:00:00+00:00",
    )

    assert task_ids == ["task-main", "task-map-0", "task-loop-step"]
    assert state["status"] == "canceled"
    assert state["sub_tasks"]["map[0]"]["status"] == "canceled"
    assert state["sub_tasks"]["map[1]"]["status"] == "success"
    assert state["loop_body_states"]["step"]["status"] == "canceled"


def test_mark_workflow_run_canceled_updates_run_and_returns_task_ids():
    run = SimpleNamespace(
        status="waiting_task",
        node_states={
            "main": {"status": "waiting_task", "task_id": "task-main"},
            "done": {"status": "success", "task_id": "task-done"},
        },
        finished_at=None,
        error_message="previous error",
    )

    task_ids = mark_workflow_run_canceled(
        run,
        finished_at="2026-09-14T00:00:00+00:00",
    )

    assert task_ids == ["task-main"]
    assert run.status == "canceled"
    assert run.node_states["main"]["status"] == "canceled"
    assert run.node_states["main"]["finished_at"] == "2026-09-14T00:00:00+00:00"
    assert run.node_states["done"]["status"] == "success"
    assert run.error_message is None
    assert run.finished_at is not None
