"""Remote API task recovery tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.tasks import TaskOutput, TaskStatus
from app.tasks.executors.errors import TaskExecutionError
from app.tasks.executors.remote_api import RemoteAPIExecutor


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def unique(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement):
        return _FakeResult(self.rows)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _task() -> SimpleNamespace:
    return SimpleNamespace(
        id="task-remote-1",
        status=TaskStatus.RUNNING.value,
        started_at=datetime(2026, 9, 20, 10, 0, 0),
        finished_at=None,
        execution_time_sec=None,
        progress=0.0,
        progress_message="任务开始执行",
        error_message=None,
        extra_data={"remote_run_id": "run-1"},
        inputs=SimpleNamespace(params={}),
        outputs=None,
    )


def _tool_version() -> SimpleNamespace:
    return SimpleNamespace(
        id="version-1",
        config={"type": "remote_api", "mode": "remote_tool_v1"},
    )


@pytest.mark.asyncio
async def test_remote_recovery_materializes_terminal_run_without_invoke(
    monkeypatch: pytest.MonkeyPatch,
):
    task = _task()
    tool_version = _tool_version()
    task.tool_version = tool_version
    record = SimpleNamespace(external_id="run-1")
    db = _FakeSession([(task, record)])
    finished_records: list[str] = []

    async def recover(self, remote_run_id=None):
        assert remote_run_id == "run-1"
        return {
            "success": True,
            "remote_run_id": "run-1",
            "result": {"success": True},
        }

    async def prepare(db, *, task, tool_version, output_result):
        return (
            {"result": {"success": True}, "file_ids": [], "output_type": "json"},
            output_result,
        )

    async def finish(*, task, status, **kwargs):
        finished_records.append(status)

    monkeypatch.setattr(RemoteAPIExecutor, "recover_remote_run", recover)
    monkeypatch.setattr(
        "app.tasks.recovery.prepare_recovered_task_output",
        prepare,
    )
    monkeypatch.setattr(
        "app.tasks.remote_recovery.finish_task_execution_record_best_effort",
        finish,
    )

    from app.tasks.remote_recovery import reconcile_orphaned_remote_tasks

    recovered = await reconcile_orphaned_remote_tasks(
        db,
        now=datetime(2026, 9, 20, 12, 0, 0),
        stale_after=timedelta(minutes=5),
    )

    assert recovered == 1
    assert task.status == TaskStatus.SUCCESS.value
    assert finished_records == ["succeeded"]
    assert any(isinstance(value, TaskOutput) for value in db.added)
    assert db.commits == 1


@pytest.mark.asyncio
async def test_remote_recovery_keeps_running_remote_run_pending(
    monkeypatch: pytest.MonkeyPatch,
):
    task = _task()
    tool_version = _tool_version()
    task.tool_version = tool_version
    record = SimpleNamespace(external_id="run-1")
    db = _FakeSession([(task, record)])

    async def recover(self, remote_run_id=None):
        return {
            "success": False,
            "status": "running",
            "recovery_pending": True,
            "remote_status": {"progress": 34, "message": "模型计算中"},
        }

    monkeypatch.setattr(RemoteAPIExecutor, "recover_remote_run", recover)

    from app.tasks.remote_recovery import reconcile_orphaned_remote_tasks

    recovered = await reconcile_orphaned_remote_tasks(
        db,
        now=datetime(2026, 9, 20, 12, 0, 0),
        stale_after=timedelta(minutes=5),
    )

    assert recovered == 0
    assert task.status == TaskStatus.RUNNING.value
    assert task.progress == 34
    assert task.progress_message == "模型计算中"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_remote_recovery_closes_terminal_remote_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    task = _task()
    tool_version = _tool_version()
    task.tool_version = tool_version
    record = SimpleNamespace(external_id="run-1")
    db = _FakeSession([(task, record)])
    finished_records: list[tuple[str, str]] = []

    async def recover(self, remote_run_id=None):
        return {
            "success": False,
            "recovery_terminal": True,
            "remote_run_id": "run-1",
            "result": {"success": False, "message": "远端模型失败"},
        }

    async def prepare(db, *, task, tool_version, output_result):
        return (
            {"result": output_result["result"], "file_ids": [], "output_type": "json"},
            output_result,
        )

    async def finish(*, task, status, error_message=None, **kwargs):
        finished_records.append((status, error_message or ""))

    monkeypatch.setattr(RemoteAPIExecutor, "recover_remote_run", recover)
    monkeypatch.setattr("app.tasks.recovery.prepare_recovered_task_output", prepare)
    monkeypatch.setattr(
        "app.tasks.remote_recovery.finish_task_execution_record_best_effort",
        finish,
    )

    from app.tasks.remote_recovery import reconcile_orphaned_remote_tasks

    recovered = await reconcile_orphaned_remote_tasks(db)

    assert recovered == 1
    assert task.status == TaskStatus.FAILURE.value
    assert finished_records == [("failed", "远端模型失败")]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_remote_recovery_backoffs_transient_service_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    task = _task()
    tool_version = _tool_version()
    task.tool_version = tool_version
    record = SimpleNamespace(external_id="run-1")
    db = _FakeSession([(task, record)])
    calls = 0

    async def recover(self, remote_run_id=None):
        nonlocal calls
        calls += 1
        raise TaskExecutionError("remote service unavailable")

    monkeypatch.setattr(RemoteAPIExecutor, "recover_remote_run", recover)

    from app.tasks.remote_recovery import reconcile_orphaned_remote_tasks

    now = datetime(2026, 9, 20, 12, 0, 0)
    recovered = await reconcile_orphaned_remote_tasks(
        db,
        now=now,
        stale_after=timedelta(minutes=5),
    )

    assert recovered == 0
    assert calls == 1
    assert task.status == TaskStatus.RUNNING.value
    assert task.extra_data["remote_recovery_failures"] == 1
    assert task.extra_data["remote_recovery_next_attempt_at"] == (
        now + timedelta(seconds=60)
    ).isoformat()
    assert "远端服务暂时不可用" in task.progress_message
    assert db.commits == 1


@pytest.mark.asyncio
async def test_remote_recovery_skips_task_during_backoff_window(
    monkeypatch: pytest.MonkeyPatch,
):
    task = _task()
    task.tool_version = _tool_version()
    now = datetime(2026, 9, 20, 12, 0, 0)
    task.extra_data.update(
        {
            "remote_recovery_failures": 2,
            "remote_recovery_next_attempt_at": (
                now + timedelta(seconds=30)
            ).isoformat(),
        }
    )
    record = SimpleNamespace(external_id="run-1")
    db = _FakeSession([(task, record)])

    async def recover(self, remote_run_id=None):
        raise AssertionError("recovery must respect the backoff window")

    monkeypatch.setattr(RemoteAPIExecutor, "recover_remote_run", recover)

    from app.tasks.remote_recovery import reconcile_orphaned_remote_tasks

    recovered = await reconcile_orphaned_remote_tasks(
        db,
        now=now,
        stale_after=timedelta(minutes=5),
    )

    assert recovered == 0
    assert db.commits == 0


@pytest.mark.asyncio
async def test_remote_recovery_logs_alert_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
):
    task = _task()
    task.tool_version = _tool_version()
    now = datetime(2026, 9, 20, 12, 0, 0)
    task.extra_data.update(
        {
            "remote_recovery_failures": 1,
            "remote_recovery_next_attempt_at": (
                now - timedelta(seconds=1)
            ).isoformat(),
        }
    )
    record = SimpleNamespace(external_id="run-1")
    db = _FakeSession([(task, record)])

    async def recover(self, remote_run_id=None):
        raise TaskExecutionError("remote service unavailable")

    monkeypatch.setattr(RemoteAPIExecutor, "recover_remote_run", recover)
    monkeypatch.setattr(
        "app.tasks.remote_recovery.settings.REMOTE_TASK_RECOVERY_ALERT_AFTER_FAILURES",
        2,
    )

    from app.tasks.remote_recovery import reconcile_orphaned_remote_tasks

    await reconcile_orphaned_remote_tasks(db, now=now)

    assert task.extra_data["remote_recovery_failures"] == 2
    assert task.extra_data["remote_recovery_alerted"] is True
    assert any(
        getattr(value, "level", None) == "ERROR"
        and "连续失败" in getattr(value, "message", "")
        for value in db.added
    )
