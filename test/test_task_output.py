"""Shared task output normalization tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tasks.output import (  # noqa: E402
    prepare_execution_artifacts,
    prepare_task_output,
)
from app.execution.contracts import ProducedArtifact  # noqa: E402
from app.services.execution_artifacts import (  # noqa: E402
    materialize_execution_artifacts,
)


def test_prepare_task_output_is_shared_and_deduplicates_file_ids():
    result = {
        "success": True,
        "output_file_ids": ["file-1", "file-1", "file-2"],
    }

    assert prepare_task_output(result) == {
        "result": result,
        "file_ids": ["file-1", "file-2"],
        "output_type": "visualization",
    }


def test_prepare_execution_artifacts_bridges_standard_artifact_refs():
    payload = prepare_execution_artifacts(
        [
            {
                "filename": "pocket.pdb",
                "path": "output/pocket.pdb",
                "file_id": "file-1",
                "artifact_type": "binding_pocket@1",
            },
            {
                "filename": "report.json",
                "path": "output/report.json",
            },
        ]
    )

    assert payload["file_ids"] == ["file-1"]
    assert payload["output_type"] == "visualization"
    assert payload["result"]["output_files"][0]["artifact_type"] == "binding_pocket@1"


@pytest.mark.asyncio
async def test_materialize_execution_artifacts_creates_platform_file_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.files import storage_path

    source_root = tmp_path / "output"
    source_root.mkdir()
    source_file = source_root / "pocket.pdb"
    source_file.write_text("ATOM\n", encoding="utf-8")
    storage_root = tmp_path / "storage"
    monkeypatch.setattr(storage_path, "STORAGE_PATH", storage_root)

    class FakeSession:
        def __init__(self):
            self.records = []

        def add(self, record):
            self.records.append(record)

        async def flush(self):
            return None

    db = FakeSession()
    task = SimpleNamespace(
        id="task-1",
        user_id="user-1",
        extra_data={"project_id": "project-1"},
    )

    materialized = await materialize_execution_artifacts(
        db,
        task=task,
        artifacts=[
            ProducedArtifact(
                filename="pocket.pdb",
                path="pocket.pdb",
                artifact_type="binding_pocket@1",
            )
        ],
        source_root=source_root,
    )

    assert len(db.records) == 1
    assert materialized[0].file_id == db.records[0].id
    assert db.records[0].project_id == "project-1"
    assert Path(db.records[0].storage_path).read_text(encoding="utf-8") == "ATOM\n"
