"""Workflow run failure state helper tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.workflow_run_failures import mark_workflow_node_failed  # noqa: E402


def test_mark_workflow_node_failed_updates_state_and_run():
    run = SimpleNamespace(status="waiting_task", error_message=None, finished_at=None)
    state = {"status": "waiting_task"}
    node_states = {"score": state}
    missing_outputs = [{"semantic_type": "pocket_pdb"}]

    updated_state = mark_workflow_node_failed(
        run,
        node_states=node_states,
        node_id="score",
        state=state,
        error_message="missing output",
        missing_outputs=missing_outputs,
    )

    assert updated_state is state
    assert state["status"] == "failure"
    assert state["error_message"] == "missing output"
    assert state["missing_outputs"] == missing_outputs
    assert "finished_at" in state
    assert node_states["score"] is state
    assert run.status == "failure"
    assert run.error_message == "missing output"
    assert run.finished_at is not None
