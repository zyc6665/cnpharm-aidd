"""ExecutionRecord lifecycle tests."""

from __future__ import annotations

from datetime import datetime, timedelta
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


@pytest.mark.asyncio
async def test_finish_task_execution_record_uses_task_external_id():
    from app.execution.records import finish_task_execution_record

    record = SimpleNamespace(
        external_id=None,
        status="running",
        error_message=None,
        finished_at=None,
    )

    class FakeSession:
        async def get(self, model, record_id):
            assert record_id == "record-1"
            return record

    task = SimpleNamespace(
        extra_data={
            "execution_record_id": "record-1",
            "remote_run_id": "run-1",
        },
    )

    await finish_task_execution_record(
        FakeSession(),
        task=task,
        status="succeeded",
    )

    assert record.external_id == "run-1"
    assert record.status == "succeeded"


@pytest.mark.asyncio
async def test_update_task_execution_record_external_id_persists_run_handle():
    from app.execution.records import update_task_execution_record_external_id

    record = SimpleNamespace(external_id=None)

    class FakeSession:
        async def get(self, model, record_id):
            assert record_id == "record-1"
            return record

    task = SimpleNamespace(extra_data={"execution_record_id": "record-1"})

    updated = await update_task_execution_record_external_id(
        FakeSession(),
        task=task,
        external_id="run-1",
    )

    assert updated is record
    assert record.external_id == "run-1"


@pytest.mark.asyncio
async def test_touch_task_execution_record_updates_running_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.execution.records import touch_task_execution_record_best_effort

    record = SimpleNamespace(status="running", updated_at=None)

    class FakeSession:
        async def get(self, model, record_id):
            assert record_id == "record-1"
            return record

        async def commit(self):
            return None

        async def rollback(self):
            return None

    class SessionContext:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(
        "app.database.session.async_session_factory",
        lambda: SessionContext(),
    )

    heartbeat_at = datetime(2026, 9, 20, 12, 0, 0)
    await touch_task_execution_record_best_effort(
        task=SimpleNamespace(
            id="task-1",
            extra_data={"execution_record_id": "record-1"},
        ),
        now=heartbeat_at,
    )

    assert record.updated_at == heartbeat_at


@pytest.mark.asyncio
async def test_finish_task_execution_record_best_effort_rolls_back_before_close(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.execution.records import finish_task_execution_record_best_effort

    events: list[str] = []

    class FakeSession:
        async def commit(self):
            events.append("commit")

        async def rollback(self):
            events.append("rollback")

    class SessionContext:
        async def __aenter__(self):
            events.append("open")
            return FakeSession()

        async def __aexit__(self, exc_type, exc, traceback):
            events.append("close")
            return False

    async def fail_finish(*args, **kwargs):
        events.append("finish")
        raise RuntimeError("record store unavailable")

    monkeypatch.setattr(
        "app.database.session.async_session_factory",
        lambda: SessionContext(),
    )
    monkeypatch.setattr(
        "app.execution.records.finish_task_execution_record",
        fail_finish,
    )

    await finish_task_execution_record_best_effort(
        task=SimpleNamespace(
            id="task-1",
            extra_data={"execution_record_id": "record-1"},
        ),
        status="failed",
    )

    assert events == ["open", "finish", "rollback", "close"]


@pytest.mark.asyncio
async def test_reconcile_running_execution_records_closes_orphans():
    from app.execution.records import reconcile_running_execution_records

    now = datetime(2026, 9, 20, 12, 0, 0)
    stale_started_at = now - timedelta(days=2)
    records = [
        SimpleNamespace(
            status="running",
            request_snapshot={"task_id": "success-task"},
            error_message=None,
            finished_at=None,
            started_at=now,
        ),
        SimpleNamespace(
            status="running",
            request_snapshot={"task_id": "missing-task"},
            error_message=None,
            finished_at=None,
            started_at=now,
        ),
        SimpleNamespace(
            status="running",
            request_snapshot={"task_id": "stale-pending-task"},
            error_message=None,
            finished_at=None,
            started_at=stale_started_at,
        ),
    ]
    tasks = {
        "success-task": SimpleNamespace(
            status="SUCCESS",
            error_message=None,
            finished_at=now,
        ),
        "stale-pending-task": SimpleNamespace(
            status="PENDING",
            error_message=None,
            finished_at=None,
        ),
        "long-running-task": SimpleNamespace(
            status="RUNNING",
            error_message=None,
            finished_at=None,
        ),
    }

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return records

    class FakeSession:
        async def execute(self, statement):
            return FakeResult()

        async def get(self, model, task_id):
            return tasks.get(task_id)

        async def flush(self):
            return None

    reconciled = await reconcile_running_execution_records(
        FakeSession(),
        now=now,
        stale_after=timedelta(days=1),
    )

    assert reconciled == 3
    assert records[0].status == "succeeded"
    assert records[0].finished_at == now
    assert records[1].status == "failed"
    assert records[1].error_message == "关联任务不存在"
    assert records[2].status == "failed"
    assert records[2].error_message == "执行记录超过保留运行时间"


@pytest.mark.asyncio
async def test_reconcile_running_execution_records_keeps_long_running_task():
    from app.execution.records import reconcile_running_execution_records

    now = datetime(2026, 9, 20, 12, 0, 0)
    record = SimpleNamespace(
        status="running",
        request_snapshot={"task_id": "long-running-task"},
        error_message=None,
        finished_at=None,
        started_at=now - timedelta(days=30),
    )

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [record]

    class FakeSession:
        async def execute(self, statement):
            return FakeResult()

        async def get(self, model, task_id):
            return SimpleNamespace(
                status="RUNNING",
                error_message=None,
                finished_at=None,
            )

        async def flush(self):
            raise AssertionError("long-running task must not be reconciled")

    reconciled = await reconcile_running_execution_records(
        FakeSession(),
        now=now,
        stale_after=timedelta(days=1),
    )

    assert reconciled == 0
    assert record.status == "running"


@pytest.mark.asyncio
async def test_reconcile_running_execution_records_skips_locked_rows():
    from app.execution.records import reconcile_running_execution_records

    statement = None

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class FakeSession:
        async def execute(self, candidate):
            nonlocal statement
            statement = candidate
            return FakeResult()

    reconciled = await reconcile_running_execution_records(
        FakeSession(),
        batch_size=10,
    )

    assert reconciled == 0
    assert statement is not None
    assert statement._for_update_arg is not None
    assert statement._for_update_arg.skip_locked is True


@pytest.mark.asyncio
async def test_reconcile_query_filters_healthy_running_tasks_before_batch_limit():
    from sqlalchemy.dialects import sqlite

    from app.execution.records import reconcile_running_execution_records

    statement = None

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class FakeSession:
        async def execute(self, candidate):
            nonlocal statement
            statement = candidate
            return FakeResult()

    await reconcile_running_execution_records(FakeSession(), batch_size=10)

    sql = str(statement.compile(dialect=sqlite.dialect()))
    assert "LEFT OUTER JOIN tasks" in sql
    assert "tasks.status !=" in sql
