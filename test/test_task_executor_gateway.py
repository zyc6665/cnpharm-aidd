"""TaskExecutor wiring for the managed execution gateway."""

from __future__ import annotations

from types import SimpleNamespace


def test_task_executor_injects_gateway_into_kubernetes_executor():
    from app.execution.service import ExecutionService
    from app.tasks.executors.factory import TaskExecutor
    from app.tasks.executors.kubernetes_job import KubernetesJobExecutor

    gateway = ExecutionService({})
    task = SimpleNamespace(id="task-1", extra_data={})
    tool_version = SimpleNamespace(config={"type": "k8s_job"})

    executor = TaskExecutor(
        task,
        tool_version,
        execution_service=gateway,
    )._get_executor()

    assert isinstance(executor, KubernetesJobExecutor)
    assert executor.execution_service is gateway
