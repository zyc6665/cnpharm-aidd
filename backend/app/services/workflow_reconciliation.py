"""Background reconciliation for non-terminal workflow runs."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.session import async_session_factory
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.tasks.service import create_and_schedule_tool_task
from app.services.workflow_runs import sync_workflow_run


logger = logging.getLogger(__name__)

NON_TERMINAL_WORKFLOW_RUN_STATUSES = ("pending", "waiting_task")

ScheduleTaskFn = Callable[..., Awaitable[object]]


async def reconcile_waiting_workflow_runs(
    db: AsyncSession,
    *,
    batch_size: int,
    schedule_task_fn: ScheduleTaskFn,
) -> int:
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.status.in_(NON_TERMINAL_WORKFLOW_RUN_STATUSES))
        .order_by(WorkflowRun.created_at.asc(), WorkflowRun.id.asc())
        .limit(batch_size)
    )
    runs = list(result.scalars().all())
    processed = 0

    for run in runs:
        owner = await db.get(User, run.owner_id)
        if not owner:
            logger.warning("Skip workflow run %s because owner %s is missing", run.id, run.owner_id)
            continue

        await sync_workflow_run(
            db,
            current_user=owner,
            run_id=run.id,
            schedule_task_fn=schedule_task_fn,
        )
        processed += 1

    return processed


async def reconcile_all_waiting_workflow_runs(
    *,
    batch_size: int | None = None,
) -> int:
    async with async_session_factory() as session:
        return await reconcile_waiting_workflow_runs(
            session,
            batch_size=batch_size or settings.WORKFLOW_RECONCILE_BATCH_SIZE,
            schedule_task_fn=create_and_schedule_tool_task,
        )


class WorkflowReconcileLoop:
    """Periodically reconcile workflow runs whose tasks may have advanced."""

    def __init__(
        self,
        *,
        reconcile: Callable[[], Awaitable[object]],
        interval_seconds: float,
    ) -> None:
        self._reconcile = reconcile
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="workflow-reconcile-loop")

    async def stop(self) -> None:
        if not self._task:
            return
        if self._stop_event:
            self._stop_event.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self._reconcile()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Workflow background reconciliation failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                continue


workflow_reconcile_loop = WorkflowReconcileLoop(
    reconcile=reconcile_all_waiting_workflow_runs,
    interval_seconds=float(settings.WORKFLOW_RECONCILE_INTERVAL_SECONDS),
)


__all__ = [
    "NON_TERMINAL_WORKFLOW_RUN_STATUSES",
    "WorkflowReconcileLoop",
    "reconcile_all_waiting_workflow_runs",
    "reconcile_waiting_workflow_runs",
    "workflow_reconcile_loop",
]
