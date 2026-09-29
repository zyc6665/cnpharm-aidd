"""Secret-isolated SSH adapter for fixed-node remote execution."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.execution.contracts import (
    ExecutionHandle,
    ExecutionRequest,
    ExecutionState,
    LogChunk,
    ProducedArtifact,
)


class SSHCredentials(BaseModel):
    private_key: str | None = None
    password: str | None = None
    known_hosts: str | None = None

    model_config = ConfigDict(extra="forbid")


class SSHExecutionConfig(BaseModel):
    node_alias: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=100)
    credential_ref: str = Field(min_length=1, max_length=255)
    remote_base_dir: str = Field(min_length=1, max_length=1000)
    strict_host_key_checking: bool = True

    model_config = ConfigDict(extra="forbid")


class SSHSecretProvider(Protocol):
    async def resolve(self, reference: str) -> SSHCredentials: ...


class SSHExecutionTransport(Protocol):
    async def submit(
        self,
        request: ExecutionRequest,
        config: SSHExecutionConfig,
        credentials: SSHCredentials,
    ) -> str: ...

    async def status(
        self,
        external_id: str,
        config: SSHExecutionConfig,
        credentials: SSHCredentials,
    ) -> ExecutionState: ...

    async def logs(
        self,
        external_id: str,
        cursor: str | None,
        config: SSHExecutionConfig,
        credentials: SSHCredentials,
    ) -> tuple[str, str | None]: ...

    async def cancel(
        self,
        external_id: str,
        config: SSHExecutionConfig,
        credentials: SSHCredentials,
    ) -> None: ...

    async def collect_artifacts(
        self,
        external_id: str,
        config: SSHExecutionConfig,
        credentials: SSHCredentials,
    ) -> list[ProducedArtifact]: ...


class SSHExecutionAdapter:
    def __init__(
        self,
        *,
        config: SSHExecutionConfig,
        secret_provider: SSHSecretProvider,
        transport: SSHExecutionTransport,
    ):
        self._config = config
        self._secret_provider = secret_provider
        self._transport = transport

    async def _credentials(self) -> SSHCredentials:
        return await self._secret_provider.resolve(self._config.credential_ref)

    @staticmethod
    def _redact(value: str, credentials: SSHCredentials) -> str:
        redacted = value
        for secret in (credentials.private_key, credentials.password):
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
        return await self._transport.status(execution_id, self._config, await self._credentials())

    async def reconcile(self, execution_id: str) -> ExecutionState:
        """Refresh SSH state; transport may later add scheduler-specific reconcile."""
        reconcile = getattr(self._transport, "reconcile", None)
        if reconcile is not None:
            return await reconcile(
                execution_id,
                self._config,
                await self._credentials(),
            )
        return await self.status(execution_id)

    async def logs(self, execution_id: str, cursor: str | None = None) -> LogChunk:
        credentials = await self._credentials()
        content, next_cursor = await self._transport.logs(
            execution_id, cursor, self._config, credentials
        )
        return LogChunk(
            content=self._redact(content, credentials),
            next_cursor=next_cursor,
        )

    async def cancel(self, execution_id: str) -> None:
        await self._transport.cancel(
            execution_id, self._config, await self._credentials()
        )

    async def collect_artifacts(self, execution_id: str) -> list[ProducedArtifact]:
        return await self._transport.collect_artifacts(
            execution_id, self._config, await self._credentials()
        )
