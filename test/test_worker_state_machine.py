"""Tests enforcing task state transitions go through TaskStateMachine."""

import re
from datetime import datetime
from pathlib import Path

import pytest

from app.models.tasks import Task, TaskStatus
from app.tasks.state_machine import TaskStateMachine, TaskStateError


def _source_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[1] / "backend" / "app" / "tasks" / Path(*parts)


def _assert_no_direct_status_assignment(source: Path) -> None:
    text = source.read_text()
    # Match task.status = ... but not task.status == ...
    matches = list(re.finditer(r"task\.status\s*=\s*[^=]", text))
    assert not matches, f"Found direct task.status assignment in {source}: {matches[0].group()}"


def _make_task(status: TaskStatus = TaskStatus.PENDING) -> Task:
    task = Task(
        id="task-1",
        user_id="user-1",
        tool_id="tool-1",
        tool_version_id="version-1",
        status=status.value,
    )
    return task


class TestStateMachineTransitions:
    def test_pending_to_running(self):
        task = _make_task(TaskStatus.PENDING)
        TaskStateMachine.start(task)
        assert task.status == TaskStatus.RUNNING.value
        assert task.started_at is not None
        assert task.progress == 0.0

    def test_running_to_success(self):
        task = _make_task(TaskStatus.RUNNING)
        task.started_at = datetime(2024, 1, 1, 12, 0, 0)
        TaskStateMachine.complete(task, success=True)
        assert task.status == TaskStatus.SUCCESS.value
        assert task.finished_at is not None
        assert task.progress == 100.0

    def test_running_to_failure(self):
        task = _make_task(TaskStatus.RUNNING)
        task.started_at = datetime(2024, 1, 1, 12, 0, 0)
        TaskStateMachine.complete(task, success=False, error_message="boom")
        assert task.status == TaskStatus.FAILURE.value
        assert task.error_message == "boom"
        assert task.finished_at is not None

    def test_pending_to_failure(self):
        task = _make_task(TaskStatus.PENDING)
        TaskStateMachine.complete(task, success=False, error_message="launch failed")
        assert task.status == TaskStatus.FAILURE.value
        assert task.error_message == "launch failed"

    def test_running_to_pending_for_gpu_requeue(self):
        task = _make_task(TaskStatus.RUNNING)
        TaskStateMachine.transition(task, TaskStatus.PENDING, progress_message="GPU资源不足")
        assert task.status == TaskStatus.PENDING.value

    def test_canceled_to_success_for_recovery(self):
        task = _make_task(TaskStatus.CANCELED)
        TaskStateMachine.complete(task, success=True)
        assert task.status == TaskStatus.SUCCESS.value
        assert task.progress == 100.0

    def test_canceled_to_failure_for_recovery(self):
        task = _make_task(TaskStatus.CANCELED)
        TaskStateMachine.complete(task, success=False, error_message="remote failed")
        assert task.status == TaskStatus.FAILURE.value
        assert task.error_message == "remote failed"

    def test_invalid_transition_raises(self):
        task = _make_task(TaskStatus.SUCCESS)
        with pytest.raises(TaskStateError):
            TaskStateMachine.start(task)

    def test_update_progress_only_when_running(self):
        task = _make_task(TaskStatus.RUNNING)
        TaskStateMachine.update_progress(task, 50.0, "halfway")
        assert task.progress == 50.0
        assert task.progress_message == "halfway"

    def test_update_progress_fails_when_not_running(self):
        task = _make_task(TaskStatus.PENDING)
        with pytest.raises(ValueError):
            TaskStateMachine.update_progress(task, 50.0)


class TestNoDirectStatusAssignments:
    def test_worker_tasks_does_not_assign_status_directly(self):
        """Spot-check: worker/tasks.py should not contain direct task.status assignments."""
        source = Path(__file__).resolve().parents[1] / "backend" / "app" / "worker" / "tasks.py"
        _assert_no_direct_status_assignment(source)

    def test_service_does_not_assign_status_directly(self):
        source = _source_path("service.py")
        _assert_no_direct_status_assignment(source)

    def test_direct_runner_does_not_assign_status_directly(self):
        source = _source_path("direct_runner.py")
        _assert_no_direct_status_assignment(source)

    def test_direct_recovery_does_not_assign_status_directly(self):
        source = _source_path("direct_recovery.py")
        _assert_no_direct_status_assignment(source)
