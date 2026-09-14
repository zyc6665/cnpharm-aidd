"""Workflow run retry state helper tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.workflow_run_retry import prepare_workflow_node_retry  # noqa: E402


def test_prepare_workflow_node_retry_resets_failed_node_and_lineage():
    definition = {
        "nodes": [
            {"id": "prepare", "kind": "tool", "tool_slug": "protein-prep", "params": {"ph": 7.4}},
            {"id": "dock", "kind": "tool", "tool_slug": "docking"},
        ],
        "edges": [{"source": "prepare", "target": "dock"}],
    }
    run = SimpleNamespace(
        status="failure",
        error_message="temporary failure",
        finished_at="2026-09-14T00:00:00Z",
        definition=definition,
        execution_order=["prepare", "dock"],
        node_states={
            "prepare": {"status": "failure", "task_id": "old-task", "error_message": "temporary failure"},
            "dock": {"status": "pending"},
        },
        artifact_lineage={"prepare": {"protein_pdb": {"file_id": "old-file"}}},
    )

    prepare_workflow_node_retry(run, node_id="prepare")

    retried_state = run.node_states["prepare"]
    assert run.status == "pending"
    assert run.error_message is None
    assert run.finished_at is None
    assert retried_state == {
        "status": "pending",
        "tool_slug": "protein-prep",
        "tool_id": None,
        "tool_version_id": None,
        "tool_version": None,
        "semantic_inputs": {},
        "artifact_inputs": {},
        "artifact_input_slots": [],
        "artifact_outputs": [],
        "params": {"ph": 7.4},
    }
    assert run.node_states["dock"] == {"status": "pending"}
    assert run.artifact_lineage == {}
