"""Workflow task output helper tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.workflow_task_outputs import (  # noqa: E402
    has_required_declared_standard_outputs,
    task_project_id,
    workflow_output_file_ids,
)


def test_task_project_id_reads_extra_data_project_id():
    assert task_project_id(SimpleNamespace(extra_data={"project_id": 123})) == "123"
    assert task_project_id(SimpleNamespace(extra_data={})) is None


def test_has_required_declared_standard_outputs_requires_named_required_output():
    assert has_required_declared_standard_outputs([
        {"name": "pocket", "required": True},
    ]) is True
    assert has_required_declared_standard_outputs([
        {"name": "optional", "required": False},
        {"type": "binding_pocket@1", "required": True},
    ]) is False


def test_workflow_output_file_ids_deduplicates_semantic_and_standard_artifact_files():
    semantic_outputs = {
        "pocket_pdb": {"source": "output_files", "file_id": "file-1"},
        "score": {"source": "output_data", "value": 0.42},
    }
    standard_artifacts = {
        "file_ids_by_artifact_ref": {
            "pocket": ["file-1", "file-2"],
            "pocket[1]": ["file-3"],
            "other": ["file-4"],
        },
    }
    declared_outputs = [{"name": "pocket"}]

    assert workflow_output_file_ids(
        semantic_outputs=semantic_outputs,
        standard_artifacts=standard_artifacts,
        declared_artifact_outputs=declared_outputs,
    ) == ["file-1", "file-2", "file-3"]
