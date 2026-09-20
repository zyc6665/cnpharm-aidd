"""Execution result collection tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.execution.contracts import ProducedArtifact  # noqa: E402
from app.services import execution_artifacts as execution_artifacts_module  # noqa: E402
from app.services.execution_results import collect_execution_task_result  # noqa: E402


@pytest.mark.asyncio
async def test_collect_execution_task_result_materializes_and_normalizes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source_root = tmp_path / "output"
    source_root.mkdir()
    (source_root / "result.json").write_text('{"ok": true}', encoding="utf-8")
    storage_root = tmp_path / "storage"
    monkeypatch.setattr(
        "app.files.storage_path.STORAGE_PATH",
        storage_root,
    )

    class FakeSession:
        def __init__(self):
            self.records = []

        def add(self, record):
            self.records.append(record)

        async def flush(self):
            assert all(record.storage_path for record in self.records)
            return None

    class FakeSource:
        async def collect_artifacts(self, execution_id: str):
            assert execution_id == "execution-1"
            return [
                ProducedArtifact(
                    filename="result.json",
                    path="result.json",
                    artifact_type="run_report@1",
                )
            ]

    result = await collect_execution_task_result(
        FakeSession(),
        source=FakeSource(),
        execution_id="execution-1",
        task=SimpleNamespace(
            id="task-1",
            user_id="user-1",
            extra_data={"project_id": "project-1"},
        ),
        source_root=source_root,
    )

    assert result.artifacts[0].file_id
    assert result.task_output["file_ids"] == [result.artifacts[0].file_id]
    assert result.task_output["output_type"] == "visualization"


@pytest.mark.asyncio
async def test_collect_execution_task_result_does_not_add_record_when_copy_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source_root = tmp_path / "output"
    source_root.mkdir()
    (source_root / "result.json").write_text('{"ok": true}', encoding="utf-8")
    monkeypatch.setattr("app.files.storage_path.STORAGE_PATH", tmp_path / "storage")

    class FakeSession:
        def __init__(self):
            self.records = []

        def add(self, record):
            self.records.append(record)

        async def flush(self):
            return None

    class FakeSource:
        async def collect_artifacts(self, execution_id: str):
            return [ProducedArtifact(filename="result.json", path="result.json")]

    def fail_copy(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(execution_artifacts_module.shutil, "copy2", fail_copy)
    session = FakeSession()

    with pytest.raises(OSError, match="disk full"):
        await collect_execution_task_result(
            session,
            source=FakeSource(),
            execution_id="execution-1",
            task=SimpleNamespace(
                id="task-1",
                user_id="user-1",
                extra_data={"project_id": "project-1"},
            ),
            source_root=source_root,
        )

    assert session.records == []
