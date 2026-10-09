"""Worker-side Kubernetes client bootstrap with ServiceAccount credentials."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.execution.adapters.kubernetes import (
    KubernetesCredentials,
    KubernetesJobExecutionAdapter,
    KubernetesJobExecutionConfig,
    KubernetesSecretProvider,
)
from app.execution.service import ExecutionService
from app.execution.transports.kubernetes_artifacts import (
    KubernetesArtifactCollector,
    KubernetesObjectStorageConfig,
)
from app.execution.transports.kubernetes_http import KubernetesHttpTransport


class KubernetesCredentialConfigurationError(RuntimeError):
    """Raised when the worker cannot safely load its cluster credentials."""


class InClusterSecretProvider(KubernetesSecretProvider):
    """Resolve one approved credential reference from a Pod ServiceAccount."""

    def __init__(
        self,
        *,
        credential_ref: str,
        api_server: str,
        token_file: Path,
        ca_file: Path,
    ):
        self._credential_ref = credential_ref
        self._api_server = api_server
        self._token_file = Path(token_file)
        self._ca_file = Path(ca_file)

    async def resolve(self, reference: str) -> KubernetesCredentials:
        if reference != self._credential_ref:
            raise KubernetesCredentialConfigurationError(
                f"unexpected Kubernetes credential reference: {reference}"
            )
        try:
            token = self._token_file.read_text(encoding="utf-8").strip()
            ca = self._ca_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise KubernetesCredentialConfigurationError(
                "Kubernetes ServiceAccount token/CA files are unavailable"
            ) from exc
        if not token or not ca:
            raise KubernetesCredentialConfigurationError(
                "Kubernetes ServiceAccount token/CA files must not be empty"
            )
        return KubernetesCredentials(
            api_server=self._api_server,
            token=token,
            certificate_authority=ca,
        )


@dataclass
class KubernetesRuntime:
    """Own the HTTP client and Gateway registered in one worker process."""

    service: ExecutionService
    client: httpx.AsyncClient

    async def close(self) -> None:
        await self.client.aclose()


def build_kubernetes_runtime(settings: Any) -> KubernetesRuntime | None:
    """Build the managed K8s Gateway when the feature flag is enabled."""
    if not settings.EXECUTOR_ENABLED_K8S:
        return None

    required = {
        "K8S_ADAPTER_CLUSTER_ALIAS": settings.K8S_ADAPTER_CLUSTER_ALIAS,
        "K8S_ADAPTER_NAMESPACE": settings.K8S_ADAPTER_NAMESPACE,
        "K8S_ADAPTER_CREDENTIAL_REF": settings.K8S_ADAPTER_CREDENTIAL_REF,
        "K8S_ADAPTER_SERVICE_ACCOUNT": settings.K8S_ADAPTER_SERVICE_ACCOUNT,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise KubernetesCredentialConfigurationError(
            "Kubernetes runtime requires: " + ", ".join(missing)
        )

    token_file = Path(
        getattr(
            settings,
            "K8S_ADAPTER_TOKEN_FILE",
            "/var/run/secrets/kubernetes.io/serviceaccount/token",
        )
    )
    ca_file = Path(
        getattr(
            settings,
            "K8S_ADAPTER_CA_FILE",
            "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
        )
    )
    if not token_file.is_file() or not ca_file.is_file():
        raise KubernetesCredentialConfigurationError(
            "Kubernetes ServiceAccount token/CA files are unavailable"
        )

    api_server = (
        getattr(settings, "K8S_ADAPTER_API_SERVER", None)
        or "https://kubernetes.default.svc"
    )
    provider = InClusterSecretProvider(
        credential_ref=settings.K8S_ADAPTER_CREDENTIAL_REF,
        api_server=api_server,
        token_file=token_file,
        ca_file=ca_file,
    )
    client = httpx.AsyncClient(
        verify=str(ca_file),
        timeout=float(getattr(settings, "K8S_ADAPTER_REQUEST_TIMEOUT_SECONDS", 30)),
    )
    object_storage_endpoint = getattr(settings, "K8S_ADAPTER_OBJECT_STORAGE_ENDPOINT", None)
    object_storage_bucket = getattr(settings, "K8S_ADAPTER_OBJECT_STORAGE_BUCKET", None)
    object_storage_secret_ref = getattr(settings, "K8S_ADAPTER_OBJECT_STORAGE_SECRET_REF", None)
    if settings.STORAGE_BACKEND != "minio":
        raise KubernetesCredentialConfigurationError(
            "Kubernetes runtime requires STORAGE_BACKEND=minio for artifact collection"
        )
    if not object_storage_endpoint or not object_storage_bucket or not object_storage_secret_ref:
        raise KubernetesCredentialConfigurationError(
            "Kubernetes runtime requires object-storage endpoint, bucket, and Secret ref"
        )
    from app.storage.minio_backend import MinIOStorageBackend

    object_storage = MinIOStorageBackend()
    collector = KubernetesArtifactCollector(
        object_storage,
        storage_config=KubernetesObjectStorageConfig(
            output_prefix=getattr(
                settings,
                "K8S_ADAPTER_OBJECT_STORAGE_OUTPUT_PREFIX",
                "executions",
            )
        ),
        staging_root=Path(
            getattr(
                settings,
                "K8S_ADAPTER_OBJECT_STORAGE_STAGING_ROOT",
                "/tmp/sciminer-k8s-artifacts",
            )
        ),
    )

    async def collect_artifacts(external_id, config, credentials):
        return await collector.collect(external_id, config)

    transport = KubernetesHttpTransport(
        client=client,
        artifact_collector=collect_artifacts,
    )
    adapter = KubernetesJobExecutionAdapter(
        config=KubernetesJobExecutionConfig(
            cluster_alias=settings.K8S_ADAPTER_CLUSTER_ALIAS,
            namespace=settings.K8S_ADAPTER_NAMESPACE,
            credential_ref=settings.K8S_ADAPTER_CREDENTIAL_REF,
            service_account=settings.K8S_ADAPTER_SERVICE_ACCOUNT,
            job_name_prefix=settings.K8S_ADAPTER_JOB_NAME_PREFIX,
            object_storage_endpoint=object_storage_endpoint,
            object_storage_bucket=object_storage_bucket,
            object_storage_secret_ref=object_storage_secret_ref,
            object_storage_output_prefix=getattr(
                settings,
                "K8S_ADAPTER_OBJECT_STORAGE_OUTPUT_PREFIX",
                "executions",
            ),
        ),
        secret_provider=provider,
        transport=transport,
    )
    return KubernetesRuntime(
        service=ExecutionService({"k8s_job": adapter}),
        client=client,
    )
