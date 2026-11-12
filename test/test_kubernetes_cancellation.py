"""Cancellation routing for managed Kubernetes Jobs."""

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_k8s_cancellation_uses_execution_gateway_external_job_id(monkeypatch):
    from app.execution.service import ExecutionService
    from app.tasks.cancellation import _cancel_remote_tool_if_needed

    calls: list[tuple] = []

    class Adapter:
        async def cancel(self, execution_id):
            calls.append(("cancel", execution_id))

    monkeypatch.setattr(
        "app.execution.runtime.get_execution_service",
        lambda: ExecutionService({"k8s_job": Adapter()}),
    )

    task = SimpleNamespace(
        id="task-1",
        tool_version_id="version-1",
        extra_data={"execution_record_id": "record-1"},
        tool_version=SimpleNamespace(config={"type": "k8s_job"}),
    )

    class DB:
        async def get(self, model, record_id):
            return SimpleNamespace(external_id="job-1")

    await _cancel_remote_tool_if_needed(DB(), task=task)

    assert calls == [("cancel", "job-1")]


@pytest.mark.asyncio
async def test_cancel_survives_remote_failure_and_records_retry(monkeypatch):
    """远端取消失败只能「记一笔待重试」，不能让接口 500 且状态没落地。

    这里守着两个真实缺陷：①`cancellation` 里引用过已删除的
    `settings.REMOTE_CANCEL_RETRY_INTERVAL_SECONDS`，except 分支自己抛
    AttributeError，接口返回 500，而 `TaskStateMachine.cancel` 早已改过内存里的
    task 却没提交；②API 进程没有配置执行网关，云端 Job 实际不会停。
    """
    from app.models.tasks import Task, TaskStatus
    from app.tasks import cancellation as cancellation_module

    cancel_calls: list[str] = []

    async def failing_remote_cancel(db, *, task):
        raise RuntimeError("不支持的执行器类型: k8s_job")

    async def fake_release(task, *, reason=None):
        cancel_calls.append(f"release:{reason}")

    async def fake_finish(**kwargs):
        cancel_calls.append("finish")

    monkeypatch.setattr(
        cancellation_module, "_cancel_remote_tool_if_needed", failing_remote_cancel
    )
    monkeypatch.setattr(
        cancellation_module, "release_task_resource_reservation", fake_release
    )
    monkeypatch.setattr(
        cancellation_module, "finish_task_execution_record_best_effort", fake_finish
    )

    task = Task(
        id="11111111-1111-1111-1111-111111111111",
        name="分子生成",
        status=TaskStatus.RUNNING.value,
        tool_id="22222222-2222-2222-2222-222222222222",
        tool_version_id="33333333-3333-3333-3333-333333333333",
        user_id="44444444-4444-4444-4444-444444444444",
        extra_data={},
    )
    user = SimpleNamespace(id="55555555-5555-5555-5555-555555555555")
    monkeypatch.setattr(
        cancellation_module, "get_audit_logger", lambda: SimpleNamespace(log_task_operation=lambda **_: None)
    )

    handled = await cancellation_module.cancel_platform_task(
        None, task=task, current_user=user
    )

    assert handled is True
    assert task.status == TaskStatus.CANCELED.value
    extra = task.extra_data
    assert extra["remote_cancel_pending"] is True
    assert "不支持的执行器类型" in extra["remote_cancel_error"]
    assert extra["remote_cancel_next_retry_at"]
    assert cancel_calls == ["finish"]


def test_remote_cancel_retry_interval_is_a_module_constant():
    """这个间隔曾经指向已删除的配置项，删掉回归的口子。"""
    from app.config import settings
    from app.tasks.cancellation import REMOTE_CANCEL_RETRY_SECONDS

    assert REMOTE_CANCEL_RETRY_SECONDS >= 1
    assert not hasattr(settings, "REMOTE_CANCEL_RETRY_INTERVAL_SECONDS")
