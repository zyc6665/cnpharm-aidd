"""Stable execution port and orchestration service tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_execution_service_delegates_complete_lifecycle_to_registered_adapter():
    from app.execution.contracts import (
        ExecutionHandle,
        ExecutionRequest,
        ExecutionState,
        LogChunk,
        ProducedArtifact,
    )
    from app.execution.service import ExecutionService

    calls: list[tuple] = []

    class FakeAdapter:
        async def submit(self, request):
            calls.append(("submit", request.idempotency_key))
            return ExecutionHandle(execution_id="exec-1", state=ExecutionState.QUEUED)

        async def status(self, execution_id):
            calls.append(("status", execution_id))
            return ExecutionState.RUNNING

        async def logs(self, execution_id, cursor=None):
            calls.append(("logs", execution_id, cursor))
            return LogChunk(content="running", next_cursor="2")

        async def cancel(self, execution_id):
            calls.append(("cancel", execution_id))

        async def collect_artifacts(self, execution_id):
            calls.append(("collect", execution_id))
            return [ProducedArtifact(filename="result.json", path="output/result.json")]

    service = ExecutionService({"ssh": FakeAdapter()})
    request = ExecutionRequest(
        idempotency_key="project-1:plan-1",
        project_id="project-1",
        requested_by="user-1",
        tool_package_version_id="package-version-1",
        variant="nvidia-cuda",
        executor_type="ssh",
    )

    handle = await service.submit(request)
    assert await service.status("ssh", handle.execution_id) == ExecutionState.RUNNING
    assert (await service.logs("ssh", handle.execution_id, "1")).content == "running"
    await service.cancel("ssh", handle.execution_id)
    artifacts = await service.collect_artifacts("ssh", handle.execution_id)

    assert artifacts[0].path == "output/result.json"
    assert calls == [
        ("submit", "project-1:plan-1"),
        ("status", "exec-1"),
        ("logs", "exec-1", "1"),
        ("cancel", "exec-1"),
        ("collect", "exec-1"),
    ]


def test_execution_request_contract_cannot_contain_inline_credentials():
    from pydantic import ValidationError

    from app.execution.contracts import ExecutionRequest

    with pytest.raises(ValidationError):
        ExecutionRequest.model_validate(
            {
                "idempotency_key": "key",
                "project_id": "project-1",
                "requested_by": "user-1",
                "tool_package_version_id": "version-1",
                "variant": "cpu",
                "executor_type": "ssh",
                "private_key": "PRIVATE KEY CONTENT",
            }
        )
