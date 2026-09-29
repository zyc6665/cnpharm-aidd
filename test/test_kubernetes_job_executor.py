"""Task executor integration with the managed Kubernetes Job gateway."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_kubernetes_job_executor_polls_gateway_and_collects_file_ids():
    from app.execution.contracts import ExecutionHandle, ExecutionState, ProducedArtifact
    from app.execution.service import ExecutionService
    from app.tasks.executors.kubernetes_job import KubernetesJobExecutor

    calls: list[tuple] = []

    class Adapter:
        def __init__(self):
            self.states = iter((ExecutionState.QUEUED, ExecutionState.SUCCEEDED))

        async def submit(self, request):
            calls.append(("submit", request.executor_type, request.project_id))
            return ExecutionHandle(
                execution_id="job-1",
                external_id="job-1",
                state=ExecutionState.QUEUED,
            )

        async def reconcile(self, execution_id):
            calls.append(("reconcile", execution_id))
            return next(self.states)

        async def logs(self, execution_id, cursor=None):
            return SimpleNamespace(content="", next_cursor=cursor)

        async def collect_artifacts(self, execution_id):
            calls.append(("collect", execution_id))
            return [ProducedArtifact(filename="result.json", path="outputs/result.json", file_id="file-1")]

        async def cancel(self, execution_id):
            calls.append(("cancel", execution_id))

    task = SimpleNamespace(
        id="task-1",
        user_id="user-1",
        tool_version_id="version-1",
        extra_data={"project_id": "project-1", "attempt_id": "attempt-1"},
        inputs=SimpleNamespace(params={"threshold": 0.5}),
    )
    tool_version = SimpleNamespace(
        id="version-1",
        version="1.0.0",
        config={
            "type": "k8s_job",
            "tool_package_version_id": "package-version-1",
            "variant": "default",
            "poll_interval_sec": 0,
        },
    )
    service = ExecutionService({"k8s_job": Adapter()})

    result = await KubernetesJobExecutor(
        task,
        tool_version,
        execution_service=service,
    ).execute()

    assert result["success"] is True
    assert result["output_file_ids"] == ["file-1"]
    assert task.extra_data["external_id"] == "job-1"
    assert calls == [
        ("submit", "k8s_job", "project-1"),
        ("reconcile", "job-1"),
        ("reconcile", "job-1"),
        ("collect", "job-1"),
    ]
