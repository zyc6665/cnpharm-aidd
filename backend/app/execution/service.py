"""Thin adapter registry implementing the execution application boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.execution.contracts import ExecutionHandle, ExecutionRequest, ExecutionState, LogChunk, ProducedArtifact
from app.execution.port import ExecutionPort


class UnsupportedExecutionTypeError(ValueError):
    """Raised when no execution adapter is registered for a request type."""


@dataclass(frozen=True)
class BoundExecutionArtifactSource:
    """Bind one adapter type to the artifact collection seam."""

    service: "ExecutionService"
    adapter_type: str

    async def collect_artifacts(self, execution_id: str) -> list[ProducedArtifact]:
        return await self.service.collect_artifacts(self.adapter_type, execution_id)


class ExecutionService:
    def __init__(self, adapters: Mapping[str, ExecutionPort]):
        self._adapters = dict(adapters)

    def _adapter(self, adapter_type: str) -> ExecutionPort:
        adapter = self._adapters.get(adapter_type)
        if adapter is None:
            raise UnsupportedExecutionTypeError(f"不支持的执行器类型: {adapter_type}")
        return adapter

    async def submit(self, request: ExecutionRequest) -> ExecutionHandle:
        return await self._adapter(request.executor_type).submit(request)

    async def status(self, adapter_type: str, execution_id: str) -> ExecutionState:
        return await self._adapter(adapter_type).status(execution_id)

    async def logs(
        self,
        adapter_type: str,
        execution_id: str,
        cursor: str | None = None,
    ) -> LogChunk:
        return await self._adapter(adapter_type).logs(execution_id, cursor)

    async def cancel(self, adapter_type: str, execution_id: str) -> None:
        await self._adapter(adapter_type).cancel(execution_id)

    async def collect_artifacts(
        self,
        adapter_type: str,
        execution_id: str,
    ) -> list[ProducedArtifact]:
        return await self._adapter(adapter_type).collect_artifacts(execution_id)

    def artifact_source(self, adapter_type: str) -> BoundExecutionArtifactSource:
        """Return a source compatible with application-level result collection."""
        self._adapter(adapter_type)
        return BoundExecutionArtifactSource(self, adapter_type)
