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

    def test_pending_to_running_clears_resource_wait_metadata(self):
        task = _make_task(TaskStatus.PENDING)
        task.extra_data = {
            "resource_snapshot": {"gpu_required": True},
            "resource_wait_reason": "gpu_unavailable",
            "resource_wait_code": "gpu_unavailable",
            "resource_wait_category": "gpu",
            "resource_wait_dimension": "gpu",
            "resource_retry_count": 2,
            "resource_retry_next_at": "2026-09-20T12:00:00",
        }

        TaskStateMachine.start(task)

        assert task.extra_data == {"resource_snapshot": {"gpu_required": True}}

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

    def test_retry_uses_model_defaults_before_flush(self):
        task = _make_task(TaskStatus.FAILURE)
        task.retry_count = None
        task.max_retries = None

        assert TaskStateMachine.can_retry(task) is True

        TaskStateMachine.retry(task)

        assert task.status == TaskStatus.PENDING.value
        assert task.retry_count == 1

    def test_zero_max_retries_still_disables_retry(self):
        task = _make_task(TaskStatus.FAILURE)
        task.retry_count = 0
        task.max_retries = 0

        assert TaskStateMachine.can_retry(task) is False
        with pytest.raises(ValueError, match="maximum retry count"):
            TaskStateMachine.retry(task)

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


class TestQueuedAndTimeoutStates:
    """docs/03 §3.4 八态：CREATED → QUEUED → RUNNING → .../TIMEOUT。"""

    def test_pending_to_queued_does_not_consume_retry_budget(self):
        task = _make_task(TaskStatus.PENDING)
        task.retry_count = None

        TaskStateMachine.enqueue(task)

        assert task.status == TaskStatus.QUEUED.value
        assert task.progress == 0.0
        assert task.progress_message == "任务已入队等待调度"
        # 首次入队不算一次重试
        assert (task.retry_count or 0) == 0

    def test_queued_to_running(self):
        task = _make_task(TaskStatus.QUEUED)
        TaskStateMachine.start(task)
        assert task.status == TaskStatus.RUNNING.value
        assert task.started_at is not None

    def test_running_requeue_goes_to_queued_and_counts_retry(self):
        task = _make_task(TaskStatus.RUNNING)
        task.retry_count = 0
        task.started_at = datetime(2024, 1, 1, 12, 0, 0)

        TaskStateMachine.transition(task, TaskStatus.QUEUED, progress_message="GPU资源不足")

        assert task.status == TaskStatus.QUEUED.value
        assert task.retry_count == 1
        assert task.started_at is None
        assert task.progress == 0.0

    def test_running_to_timeout_is_terminal(self):
        task = _make_task(TaskStatus.RUNNING)
        task.started_at = datetime(2024, 1, 1, 12, 0, 0)

        TaskStateMachine.mark_timeout(task, error_message="Docker execution timeout")

        assert task.status == TaskStatus.TIMEOUT.value
        assert task.error_message == "Docker execution timeout"
        assert task.finished_at is not None
        assert TaskStateMachine.is_terminal(TaskStatus.TIMEOUT) is True
        assert TaskStateMachine.is_terminal(task.status) is True

    def test_queued_can_time_out(self):
        task = _make_task(TaskStatus.QUEUED)
        TaskStateMachine.mark_timeout(task)
        assert task.status == TaskStatus.TIMEOUT.value
        assert task.progress_message == "任务执行超时"

    def test_timeout_is_retryable(self):
        task = _make_task(TaskStatus.TIMEOUT)
        task.retry_count = 0
        task.max_retries = 3

        assert TaskStateMachine.can_retry(task) is True

        TaskStateMachine.retry(task)

        assert task.status == TaskStatus.PENDING.value
        assert task.retry_count == 1

    def test_timeout_cannot_go_back_to_success_directly(self):
        task = _make_task(TaskStatus.TIMEOUT)
        with pytest.raises(TaskStateError):
            TaskStateMachine.transition(task, TaskStatus.SUCCESS)

    def test_queued_task_can_be_cancelled(self):
        task = _make_task(TaskStatus.QUEUED)
        assert TaskStateMachine.can_cancel(task) is True
        TaskStateMachine.cancel(task)
        assert task.status == TaskStatus.CANCELED.value


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
