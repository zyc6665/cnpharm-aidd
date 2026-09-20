"""ExecutionRecord lifecycle tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_task_execution_record_pointer_round_trips_through_extra_data():
    from app.execution.records import (
        set_task_execution_record_id,
        task_execution_record_id,
    )

    task = SimpleNamespace(extra_data={"project_id": "project-1"})

    set_task_execution_record_id(task, "record-1")
    assert task_execution_record_id(task) == "record-1"

    set_task_execution_record_id(task, None)
    assert task_execution_record_id(task) is None
    assert task.extra_data == {"project_id": "project-1"}


@pytest.mark.asyncio
async def test_start_task_execution_record_skips_legacy_and_builtin_tasks():
    from app.execution.records import start_task_execution_record

    class FakeSession:
        def __init__(self):
            self.records = []

        def add(self, record):
            self.records.append(record)

        async def flush(self):
            raise AssertionError("legacy and builtin tasks must not create records")

    task = SimpleNamespace(
        id="task-1",
        tool_id="tool-1",
        user_id="user-1",
        extra_data={"project_id": "project-1"},
    )

    for tool_type in ("builtin", "legacy_unknown"):
        record = await start_task_execution_record(
            FakeSession(),
            task=task,
            tool_slug="demo-tool",
            tool_version_id="tool-version-1",
            tool_version="1.0.0",
            tool_type=tool_type,
            attempt_id="attempt-1",
        )
        assert record is None


@pytest.mark.asyncio
async def test_start_task_execution_record_persists_safe_package_backed_attempt():
    from app.execution.records import (
        start_task_execution_record,
        task_execution_record_id,
    )

    class FakeResult:
        def scalar_one_or_none(self):
            return "package-version-1"

    class FakeSession:
        def __init__(self):
            self.records = []

        async def execute(self, statement):
            return FakeResult()

        async def scalar(self, statement):
            return None

        def add(self, record):
            self.records.append(record)

        async def flush(self):
            self.records[0].id = "record-1"

    task = SimpleNamespace(
        id="task-1",
        tool_id="tool-1",
        user_id="user-1",
        extra_data={"project_id": "project-1"},
    )
    session = FakeSession()

    record = await start_task_execution_record(
        session,
        task=task,
        tool_slug="remote-tool",
        tool_version_id="tool-version-1",
        tool_version="1.0.0",
        tool_type="remote_api",
        attempt_id="attempt-1",
        tool_config={
            "timeout_sec": 600,
            "mode": "remote_tool_v1",
            "headers": {"Authorization": "secret"},
            "endpoint": "https://internal.example",
        },
    )

    assert record is session.records[0]
    assert record.adapter_type == "remote_job"
    assert record.tool_package_version_id == "package-version-1"
    assert record.request_snapshot["task_id"] == "task-1"
    assert record.request_snapshot["parameters"] == {
        "timeout_sec": 600,
        "mode": "remote_tool_v1",
    }
    assert task_execution_record_id(task) == "record-1"


def test_execution_record_snapshot_excludes_runtime_configuration():
    from app.execution.records import _safe_parameters

    assert _safe_parameters(
        {
            "timeout_sec": 600,
            "mode": "remote_tool_v1",
            "headers": {"Authorization": "secret"},
            "endpoint": "https://internal.example",
        }
    ) == {"timeout_sec": 600, "mode": "remote_tool_v1"}
