"""HTTP Kubernetes Job transport tests."""

from __future__ import annotations

import httpx
import pytest


def _request():
    from app.execution.contracts import ExecutionRequest

    return ExecutionRequest(
        idempotency_key="task:task-1:attempt:attempt-1",
        project_id="project-1",
        requested_by="user-1",
        tool_package_version_id="package-version-1",
        variant="cpu",
        executor_type="k8s_job",
        runtime={
            "image": "registry.example/model@sha256:" + "a" * 64,
            "entrypoint": ["/app/run.sh"],
        },
        resources={
            "resource_request": {
                "cpu": 2,
                "memory_limit": "4Gi",
                "cpu_limit": 2,
                "gpu_count": 0,
                "timeout_sec": 120,
            }
        },
        task_id="task-1",
        attempt_id="attempt-1",
        tool_version_id="tool-version-1",
    )


def _config():
    from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig

    return KubernetesJobExecutionConfig(
        cluster_alias="platform",
        namespace="model-jobs",
        credential_ref="platform-k8s",
        service_account="model-runner",
    )


def _credentials():
    from app.execution.adapters.kubernetes import KubernetesCredentials

    return KubernetesCredentials(
        api_server="https://kubernetes.default.svc",
        token="secret-token",
    )


@pytest.mark.asyncio
async def test_http_transport_delegates_job_lifecycle_to_kubernetes_api():
    from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
    from app.execution.transports.kubernetes_http import KubernetesHttpTransport
    from app.execution.contracts import ExecutionState

    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path.endswith("/jobs"):
            return httpx.Response(
                201,
                json={"metadata": {"name": "sciminer-job-1"}},
                request=request,
            )
        if request.method == "GET" and request.url.path.endswith("/jobs/sciminer-job-1"):
            return httpx.Response(
                200,
                json={"status": {"active": 1}},
                request=request,
            )
        if request.method == "GET" and request.url.path.endswith("/pods"):
            return httpx.Response(
                200,
                json={"items": [{"metadata": {"name": "sciminer-job-1-pod"}}]},
                request=request,
            )
        if request.method == "GET" and request.url.path.endswith("/pods/sciminer-job-1-pod/log"):
            return httpx.Response(200, text="smoke log", request=request)
        if request.method == "DELETE" and request.url.path.endswith("/jobs/sciminer-job-1"):
            return httpx.Response(200, json={}, request=request)
        return httpx.Response(500, json={"message": "unexpected request"}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = KubernetesHttpTransport(client=client)
    try:
        external_id = await transport.submit(_request(), _config(), _credentials())
        assert external_id == "model-jobs/sciminer-job-1"
        assert await transport.status(external_id, _config(), _credentials()) == ExecutionState.RUNNING
        assert await transport.reconcile(external_id, _config(), _credentials()) == ExecutionState.RUNNING
        content, cursor = await transport.logs(external_id, None, _config(), _credentials())
        assert content == "smoke log"
        assert cursor is None
        await transport.cancel(external_id, _config(), _credentials())
    finally:
        await client.aclose()

    assert calls == [
        ("POST", "/apis/batch/v1/namespaces/model-jobs/jobs"),
        ("GET", "/apis/batch/v1/namespaces/model-jobs/jobs/sciminer-job-1"),
        ("GET", "/apis/batch/v1/namespaces/model-jobs/jobs/sciminer-job-1"),
        ("GET", "/api/v1/namespaces/model-jobs/pods"),
        ("GET", "/api/v1/namespaces/model-jobs/pods/sciminer-job-1-pod/log"),
        ("DELETE", "/apis/batch/v1/namespaces/model-jobs/jobs/sciminer-job-1"),
    ]


@pytest.mark.asyncio
async def test_http_transport_treats_duplicate_job_submission_as_idempotent():
    from app.execution.transports.kubernetes_http import KubernetesHttpTransport

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(409, json={"reason": "AlreadyExists"}, request=request)
        return httpx.Response(
            200,
            json={"metadata": {"name": "sciminer-job-1"}},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = KubernetesHttpTransport(client=client)
    try:
        assert await transport.submit(_request(), _config(), _credentials()) == (
            "model-jobs/sciminer-job-1"
        )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_http_transport_requires_api_server_and_explicit_artifact_collector():
    from app.execution.adapters.kubernetes import KubernetesCredentials
    from app.execution.transports.kubernetes_http import (
        KubernetesArtifactCollectionError,
        KubernetesHttpTransport,
        KubernetesTransportError,
    )

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    transport = KubernetesHttpTransport(client=client)
    try:
        with pytest.raises(KubernetesTransportError, match="api_server"):
            await transport.status("model-jobs/job-1", _config(), KubernetesCredentials(token="x"))
        with pytest.raises(KubernetesArtifactCollectionError, match="artifact collector"):
            await transport.collect_artifacts("model-jobs/job-1", _config(), _credentials())
    finally:
        await client.aclose()
