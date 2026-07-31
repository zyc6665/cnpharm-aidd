"""Thin adapter registry implementing the execution application boundary."""

from __future__ import annotations

from fastapi import HTTPException

from app.execution.contracts import ExecutionHandle, ExecutionRequest, ExecutionState, LogChunk, ProducedArtifact
from app.execution.port import ExecutionPort


class ExecutionService:
    def __init__(self, adapters: dict[str, ExecutionPort]):
        self._adapters = dict(adapters)

    def _adapter(self, adapter_type: str) -> ExecutionPort:
        adapter = self._adapters.get(adapter_type)
        if adapter is None:
            raise HTTPException(status_code=422, detail=f"不支持的执行器类型: {adapter_type}")
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
