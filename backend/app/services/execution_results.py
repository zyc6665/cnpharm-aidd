"""Application-level collection of execution artifacts for task outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.contracts import ProducedArtifact
from app.models.tasks import Task
from app.services.execution_artifacts import materialize_execution_artifacts
from app.tasks.output import prepare_execution_artifacts


class ExecutionArtifactSource(Protocol):
    async def collect_artifacts(self, execution_id: str) -> list[ProducedArtifact]: ...


@dataclass(frozen=True)
class CollectedExecutionTaskResult:
    """Materialized artifacts plus the legacy-compatible TaskOutput payload."""

    artifacts: tuple[ProducedArtifact, ...]
    task_output: dict[str, Any]


async def collect_execution_task_result(
    db: AsyncSession,
    *,
    source: ExecutionArtifactSource,
    execution_id: str,
    task: Task,
    source_root: Path,
) -> CollectedExecutionTaskResult:
    """Collect, materialize, and normalize one standard execution result."""
    produced_artifacts = await source.collect_artifacts(execution_id)
    materialized_artifacts = await materialize_execution_artifacts(
        db,
        task=task,
        artifacts=produced_artifacts,
        source_root=source_root,
    )
    return CollectedExecutionTaskResult(
        artifacts=tuple(materialized_artifacts),
        task_output=prepare_execution_artifacts(materialized_artifacts),
    )
