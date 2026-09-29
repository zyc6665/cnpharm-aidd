"""ExecutionPort protocol consumed by project and Agent services."""

from __future__ import annotations

from typing import Protocol

from app.execution.contracts import (
    ExecutionHandle,
    ExecutionRequest,
    ExecutionState,
    LogChunk,
    ProducedArtifact,
)


class ExecutionPort(Protocol):
    async def submit(self, request: ExecutionRequest) -> ExecutionHandle: ...

    async def status(self, execution_id: str) -> ExecutionState: ...

    async def reconcile(self, execution_id: str) -> ExecutionState: ...

    async def logs(self, execution_id: str, cursor: str | None = None) -> LogChunk: ...

    async def cancel(self, execution_id: str) -> None: ...

    async def collect_artifacts(self, execution_id: str) -> list[ProducedArtifact]: ...
