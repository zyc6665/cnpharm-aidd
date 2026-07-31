"""SSH ExecutionPort adapter security and lifecycle tests."""

from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_ssh_adapter_resolves_secret_only_at_transport_boundary_and_redacts_logs():
    from app.execution.adapters.ssh import SSHCredentials, SSHExecutionAdapter, SSHExecutionConfig
    from app.execution.contracts import ExecutionRequest, ExecutionState

    secret = "-----BEGIN PRIVATE KEY-----very-secret-----END PRIVATE KEY-----"

    class SecretProvider:
        async def resolve(self, reference: str):
            assert reference == "ssh-node-a"
            return SSHCredentials(private_key=secret)

    class Transport:
        def __init__(self):
            self.credentials_seen = None
            self.request_seen = None

        async def submit(self, request, config, credentials):
            self.request_seen = request
            self.credentials_seen = credentials
            return "remote-1"

        async def status(self, external_id, config, credentials):
            return ExecutionState.RUNNING

        async def logs(self, external_id, cursor, config, credentials):
            return f"connected with {secret}", "next"

        async def cancel(self, external_id, config, credentials):
            return None

        async def collect_artifacts(self, external_id, config, credentials):
            return []

    transport = Transport()
    adapter = SSHExecutionAdapter(
        config=SSHExecutionConfig(
            node_alias="gpu-node-a",
            host="gpu-node-a.internal",
            username="runner",
            credential_ref="ssh-node-a",
            remote_base_dir="/srv/aidd-jobs",
        ),
        secret_provider=SecretProvider(),
        transport=transport,
    )
    request = ExecutionRequest(
        idempotency_key="project-1:plan-1",
        project_id="project-1",
        requested_by="user-1",
        tool_package_version_id="version-1",
        variant="nvidia-cuda",
        executor_type="ssh",
        parameters={"threshold": 0.5},
    )

    handle = await adapter.submit(request)
    assert handle.external_id == "remote-1"
    assert transport.credentials_seen.private_key == secret
    assert secret not in request.model_dump_json()
    assert secret not in json.dumps(transport.request_seen.model_dump())

    chunk = await adapter.logs(handle.execution_id)
    assert secret not in chunk.content
    assert "[REDACTED]" in chunk.content


def test_execution_record_model_has_no_secret_columns():
    from app.models.executions import ExecutionRecord

    column_names = set(ExecutionRecord.__table__.columns.keys())
    assert not column_names & {"password", "private_key", "secret", "credentials"}
    assert {"project_id", "adapter_type", "external_id", "request_snapshot"} <= column_names
