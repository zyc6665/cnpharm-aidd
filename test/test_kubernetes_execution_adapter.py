"""Kubernetes Job execution adapter contract tests."""

from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_kubernetes_adapter_delegates_lifecycle_and_redacts_logs():
    from app.execution.adapters.kubernetes import (
        KubernetesCredentials,
        KubernetesJobExecutionAdapter,
        KubernetesJobExecutionConfig,
    )
    from app.execution.contracts import ExecutionRequest, ExecutionState, ProducedArtifact

    token = "k8s-secret-token"

    class SecretProvider:
        async def resolve(self, reference: str):
            assert reference == "platform-k8s"
            return KubernetesCredentials(token=token)

    class Transport:
        def __init__(self):
            self.calls: list[tuple] = []

        async def submit(self, request, config, credentials):
            self.calls.append(("submit", request.idempotency_key, config.namespace))
            assert credentials.token == token
            return "job-1"

        async def status(self, external_id, config, credentials):
            self.calls.append(("status", external_id))
            return ExecutionState.RUNNING

        async def reconcile(self, external_id, config, credentials):
            self.calls.append(("reconcile", external_id))
            return ExecutionState.SUCCEEDED

        async def logs(self, external_id, cursor, config, credentials):
            self.calls.append(("logs", external_id, cursor))
            return f"token={token}", "2"

        async def cancel(self, external_id, config, credentials):
            self.calls.append(("cancel", external_id))

        async def collect_artifacts(self, external_id, config, credentials):
            self.calls.append(("collect", external_id))
            return [ProducedArtifact(filename="result.json", path="outputs/result.json")]

    transport = Transport()
    adapter = KubernetesJobExecutionAdapter(
        config=KubernetesJobExecutionConfig(
            cluster_alias="platform",
            namespace="model-jobs",
            credential_ref="platform-k8s",
            service_account="model-runner",
            job_name_prefix="sciminer",
        ),
        secret_provider=SecretProvider(),
        transport=transport,
    )
    request = ExecutionRequest(
        idempotency_key="project-1:attempt-1",
        project_id="project-1",
        requested_by="user-1",
        tool_package_version_id="version-1",
        variant="default",
        executor_type="k8s_job",
    )

    handle = await adapter.submit(request)
    assert handle.execution_id == "job-1"
    assert await adapter.status("job-1") == ExecutionState.RUNNING
    assert await adapter.reconcile("job-1") == ExecutionState.SUCCEEDED
    chunk = await adapter.logs("job-1")
    assert token not in chunk.content
    assert "[REDACTED]" in chunk.content
    await adapter.cancel("job-1")
    artifacts = await adapter.collect_artifacts("job-1")

    assert artifacts[0].path == "outputs/result.json"
    assert transport.calls == [
        ("submit", "project-1:attempt-1", "model-jobs"),
        ("status", "job-1"),
        ("reconcile", "job-1"),
        ("logs", "job-1", None),
        ("cancel", "job-1"),
        ("collect", "job-1"),
    ]
    assert token not in json.dumps(request.model_dump())


def test_kubernetes_config_rejects_inline_credentials():
    from pydantic import ValidationError

    from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig

    with pytest.raises(ValidationError):
        KubernetesJobExecutionConfig(
            cluster_alias="platform",
            namespace="model-jobs",
            credential_ref="platform-k8s",
            service_account="model-runner",
            image="registry.example/model@sha256:abc",
            token="inline-secret",
        )
