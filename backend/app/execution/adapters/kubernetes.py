"""Secret-isolated Kubernetes Job execution adapter.

The adapter deliberately depends on a transport protocol instead of importing
the Kubernetes SDK. The infrastructure layer can provide a real client while
tests and local development use a deterministic fake transport.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.execution.contracts import (
    ExecutionArtifactCollection,
    ExecutionHandle,
    ExecutionRequest,
    ExecutionState,
    LogChunk,
    ProducedArtifact,
)


class KubernetesCredentials(BaseModel):
    """Resolved credentials kept at the transport boundary only."""

    api_server: str | None = None
    token: str | None = None
    certificate_authority: str | None = None

    model_config = ConfigDict(extra="forbid")


class KubernetesJobExecutionConfig(BaseModel):
    """Approved cluster and runtime references for one managed Job."""

    cluster_alias: str = Field(min_length=1, max_length=100)
    namespace: str = Field(min_length=1, max_length=255)
    credential_ref: str = Field(min_length=1, max_length=255)
    service_account: str = Field(min_length=1, max_length=255)
    job_name_prefix: str = Field(default="sciminer", min_length=1, max_length=63)
    image_pull_secret_ref: str | None = Field(default=None, max_length=255)
    job_ttl_seconds: int = Field(default=86400, ge=0, le=604800)
    object_storage_endpoint: str | None = Field(default=None, max_length=2048)
    object_storage_bucket: str | None = Field(default=None, max_length=255)
    object_storage_secret_ref: str | None = Field(default=None, max_length=255)
    object_storage_output_prefix: str = Field(
        default="executions",
        min_length=1,
        max_length=512,
    )

    model_config = ConfigDict(extra="forbid")


class KubernetesSecretProvider(Protocol):
    async def resolve(self, reference: str) -> KubernetesCredentials: ...


class KubernetesJobTransport(Protocol):
    async def submit(
        self,
        request: ExecutionRequest,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> str: ...

    async def status(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> ExecutionState: ...

    async def reconcile(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> ExecutionState: ...

    async def logs(
        self,
        external_id: str,
        cursor: str | None,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> tuple[str, str | None]: ...

    async def cancel(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> None: ...

    async def collect_artifacts(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> list[ProducedArtifact]: ...

    async def collect_result(
        self,
        external_id: str,
        config: KubernetesJobExecutionConfig,
        credentials: KubernetesCredentials,
    ) -> ExecutionArtifactCollection: ...


class KubernetesJobExecutionAdapter:
    """Adapter for one Kubernetes Job lifecycle."""

    def __init__(
        self,
        *,
        config: KubernetesJobExecutionConfig,
        secret_provider: KubernetesSecretProvider,
        transport: KubernetesJobTransport,
    ):
        self._config = config
        self._secret_provider = secret_provider
        self._transport = transport

    async def _credentials(self) -> KubernetesCredentials:
        return await self._secret_provider.resolve(self._config.credential_ref)

    @staticmethod
    def _redact(value: str, credentials: KubernetesCredentials) -> str:
        redacted = value
        for secret in (credentials.token, credentials.certificate_authority):
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        return redacted

    async def submit(self, request: ExecutionRequest) -> ExecutionHandle:
        credentials = await self._credentials()
        external_id = await self._transport.submit(request, self._config, credentials)
        return ExecutionHandle(
            execution_id=external_id,
            external_id=external_id,
            state=ExecutionState.QUEUED,
        )

    async def status(self, execution_id: str) -> ExecutionState:
        return await self._transport.status(
            execution_id,
            self._config,
            await self._credentials(),
        )

    async def reconcile(self, execution_id: str) -> ExecutionState:
        return await self._transport.reconcile(
            execution_id,
            self._config,
            await self._credentials(),
        )

    async def logs(self, execution_id: str, cursor: str | None = None) -> LogChunk:
        credentials = await self._credentials()
        content, next_cursor = await self._transport.logs(
            execution_id,
            cursor,
            self._config,
            credentials,
        )
        return LogChunk(
            content=self._redact(content, credentials),
            next_cursor=next_cursor,
        )

    async def cancel(self, execution_id: str) -> None:
        await self._transport.cancel(
            execution_id,
            self._config,
            await self._credentials(),
        )

    async def collect_artifacts(self, execution_id: str) -> list[ProducedArtifact]:
        return await self._transport.collect_artifacts(
            execution_id,
            self._config,
            await self._credentials(),
        )

    async def collect_result(self, execution_id: str) -> ExecutionArtifactCollection:
        collect_result = getattr(self._transport, "collect_result", None)
        if collect_result is None:
            return ExecutionArtifactCollection(
                artifacts=tuple(await self.collect_artifacts(execution_id))
            )
        return await collect_result(
            execution_id,
            self._config,
            await self._credentials(),
        )
