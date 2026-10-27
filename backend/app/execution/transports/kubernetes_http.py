"""Minimal Kubernetes HTTP transport for managed Job lifecycle operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.common.trace import TRACE_ID_HEADER, get_trace_id
from app.execution.adapters.kubernetes import (
    KubernetesCredentials,
    KubernetesJobExecutionConfig,
)
from app.execution.adapters.kubernetes_manifest import build_kubernetes_job_manifest
from app.execution.contracts import (
    ExecutionArtifactCollection,
    ExecutionHandleGone,
    ExecutionRequest,
    ExecutionState,
    ProducedArtifact,
)
from app.execution.transports.kubernetes_artifacts import (
    KubernetesArtifactCollectionError,
    KubernetesTransportError,
)


ArtifactCollector = Callable[[str, KubernetesJobExecutionConfig, KubernetesCredentials], Any]


class KubernetesHttpTransport:
    """Transport the adapter contract over the Kubernetes REST API."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        artifact_collector: ArtifactCollector | None = None,
    ):
        self._client = client
        self._artifact_collector = artifact_collector

    async def submit(
        self,
        request: ExecutionRequest,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> str:
        job = build_kubernetes_job_manifest(request, config)
        response = await self._request(
            "POST",
            self._jobs_path(config.namespace),
            config,
            credentials,
            json_body=job,
        )
        if response.status_code == 409:
            existing = await self._request(
                "GET",
                f"{self._jobs_path(config.namespace)}/{job['metadata']['name']}",
                config,
                credentials,
            )
            self._raise_for_status(existing, "read existing Kubernetes Job")
            name = _metadata_name(existing.json())
        else:
            self._raise_for_status(response, "create Kubernetes Job")
            name = _metadata_name(response.json())
        return _external_id(config.namespace, name)

    async def status(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> ExecutionState:
        payload = await self._get_job(external_id, config, credentials)
        return _job_state(payload)

    async def reconcile(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> ExecutionState:
        return await self.status(external_id, config, credentials)

    async def job_exists(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> bool:
        """Report whether the Job is still present, without raising on 404."""
        try:
            await self._get_job(external_id, config, credentials)
        except ExecutionHandleGone:
            return False
        return True

    async def logs(
        self,
        external_id: str,
        cursor: str | None,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> tuple[str, str | None]:
        pod_name = await self._pod_name(external_id, config, credentials)
        params = {"timestamps": "true"}
        if cursor:
            params["sinceTime"] = cursor
        response = await self._request(
            "GET",
            self._pod_log_path(config.namespace, pod_name),
            config,
            credentials,
            params=params,
        )
        self._raise_for_status(response, "read Kubernetes Pod logs")
        return response.text, None

    async def cancel(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> None:
        response = await self._request(
            "DELETE",
            self._job_path(external_id, config.namespace),
            config,
            credentials,
            params={"propagationPolicy": "Background"},
        )
        if response.status_code not in {200, 202, 404}:
            self._raise_for_status(response, "delete Kubernetes Job")

    async def collect_artifacts(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> list[ProducedArtifact]:
        collection = await self.collect_result(external_id, config, credentials)
        return list(collection.artifacts)

    async def collect_result(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> ExecutionArtifactCollection:
        if self._artifact_collector is None:
            raise KubernetesArtifactCollectionError(
                "Kubernetes artifact collector is not configured; MinIO staging is required"
            )
        result = self._artifact_collector(external_id, config, credentials)
        if hasattr(result, "__await__"):
            result = await result
        if isinstance(result, ExecutionArtifactCollection):
            return result
        return ExecutionArtifactCollection(artifacts=tuple(result))

    async def _get_job(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            self._job_path(external_id, config.namespace),
            config,
            credentials,
        )
        if response.status_code == 404:
            # A 404 is the expected shape of "the Job is gone": TTL reclamation,
            # a completed cancellation, or a job that never existed. Raise a
            # dedicated signal instead of a transport error so callers can map it
            # to a terminal state rather than a retryable failure.
            raise ExecutionHandleGone(
                f"Kubernetes Job no longer exists: {external_id}"
            )
        self._raise_for_status(response, "read Kubernetes Job")
        return response.json()

    async def _pod_name(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> str:
        name = external_id.rsplit("/", 1)[-1]
        response = await self._request(
            "GET",
            f"/api/v1/namespaces/{config.namespace}/pods",
            config,
            credentials,
            params={"labelSelector": f"job-name={name}"},
        )
        self._raise_for_status(response, "list Kubernetes Job Pods")
        items = response.json().get("items") or []
        if not items:
            raise KubernetesTransportError(f"no Pod found for Kubernetes Job: {name}")
        return _metadata_name(items[0])

    async def _request(
        self,
        method: str,
        path: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        if not credentials.api_server:
            raise KubernetesTransportError("Kubernetes credentials require api_server")
        headers = {"Accept": "application/json"}
        if credentials.token:
            headers["Authorization"] = f"Bearer {credentials.token}"
        # docs/10 §8.3 跨服务透传：这是仓库里唯一真正跨进程的业务出站，带上当前
        # traceId，K8s 侧（以及其后的 apiserver 审计日志）才能和这次任务提交对上。
        # K8s apiserver 接受并忽略不认识的请求头，不设置时保持原样不发空头。
        trace_id = get_trace_id()
        if trace_id:
            headers[TRACE_ID_HEADER] = trace_id
        url = credentials.api_server.rstrip("/") + path
        return await self._client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        if response.is_success:
            return
        detail = response.text[:500]
        raise KubernetesTransportError(f"{operation} failed: HTTP {response.status_code}: {detail}")

    @staticmethod
    def _jobs_path(namespace: str) -> str:
        return f"/apis/batch/v1/namespaces/{namespace}/jobs"

    @staticmethod
    def _job_path(external_id: str, namespace: str) -> str:
        name = external_id.rsplit("/", 1)[-1]
        return f"/apis/batch/v1/namespaces/{namespace}/jobs/{name}"

    @staticmethod
    def _pod_log_path(namespace: str, pod_name: str) -> str:
        return f"/api/v1/namespaces/{namespace}/pods/{pod_name}/log"


def _external_id(namespace: str, name: str) -> str:
    return f"{namespace}/{name}"


def _metadata_name(payload: dict[str, Any]) -> str:
    name = payload.get("metadata", {}).get("name")
    if not isinstance(name, str) or not name:
        raise KubernetesTransportError("Kubernetes response has no metadata.name")
    return name


def _job_state(payload: dict[str, Any]) -> ExecutionState:
    status = payload.get("status") or {}
    if status.get("succeeded", 0) > 0:
        return ExecutionState.SUCCEEDED
    if status.get("failed", 0) > 0:
        return ExecutionState.FAILED
    if status.get("active", 0) > 0:
        return ExecutionState.RUNNING
    return ExecutionState.QUEUED
