"""Task command projection tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.run_preparation import PreparedRun  # noqa: E402
from app.tasks.commands import TaskCommand  # noqa: E402


def test_task_command_projects_prepared_run_without_mutating_input_data():
    prepared = PreparedRun(
        ready=True,
        project_id="project-1",
        params={"threshold": 0.5},
        file_ids=["file-1"],
        input_bindings={"protein": "version-1"},
        standard_input_uploads={"ligand": "file-2"},
        binding_decisions={"protein": {"status": "ready"}},
    )
    extra_data = {"resource_snapshot": {"gpu_required": True}}

    command = TaskCommand.from_prepared_run(
        user_id="user-1",
        tool_id="tool-1",
        tool_version_id="tool-version-1",
        name="Example run",
        priority="high",
        prepared_run=prepared,
        requested_input_bindings={"protein": "version-0"},
        extra_data=extra_data,
    )

    assert command.project_id == "project-1"
    assert command.task_input == {
        "params": {"threshold": 0.5},
        "file_ids": ["file-1"],
    }
    assert command.extra_data["input_bindings"] == {"protein": "version-1"}
    assert command.extra_data["standard_input_uploads"] == {"ligand": "file-2"}
    assert command.extra_data["binding_decisions"] == {"protein": {"status": "ready"}}
    assert extra_data == {"resource_snapshot": {"gpu_required": True}}
