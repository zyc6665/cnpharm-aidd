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
