"""Background reconciliation for non-terminal workflow runs."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_cache
from app.config import settings
from app.database.session import async_session_factory
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.tasks.service import create_and_schedule_tool_task
from app.services.workflow_runs import sync_workflow_run


logger = logging.getLogger(__name__)

NON_TERMINAL_WORKFLOW_RUN_STATUSES = ("pending", "waiting_task")
WORKFLOW_RECONCILE_LOCK_KEY = "workflow:reconcile:lock"

ScheduleTaskFn = Callable[..., Awaitable[object]]


async def reconcile_waiting_workflow_runs(
    db: AsyncSession,
    *,
    batch_size: int,
    schedule_task_fn: ScheduleTaskFn,
) -> int:
    processed = 0
    processed_run_ids: set[str] = set()

    # Claim one run per transaction boundary. Downstream scheduling helpers
    # commit their session, so selecting a whole batch up front would release
    # locks for not-yet-processed rows and allow another instance to race.
    while processed < max(int(batch_size), 0):
        result = await db.execute(
            select(WorkflowRun)
            .where(
                WorkflowRun.status.in_(NON_TERMINAL_WORKFLOW_RUN_STATUSES),
                WorkflowRun.id.not_in(processed_run_ids),
            )
            .order_by(WorkflowRun.created_at.asc(), WorkflowRun.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        run = result.scalar_one_or_none()
        if run is None:
            break
        processed_run_ids.add(str(run.id))

        owner = await db.get(User, run.owner_id)
        if not owner:
            logger.warning("Skip workflow run %s because owner %s is missing", run.id, run.owner_id)
            await db.commit()
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
    cache = get_cache()
    lock_token = uuid4().hex
    lock_ttl = max(int(settings.WORKFLOW_RECONCILE_LOCK_TTL_SECONDS), 1)
    acquired = await cache.set(
        WORKFLOW_RECONCILE_LOCK_KEY,
        lock_token,
        ex=lock_ttl,
        nx=True,
    )
    if not acquired:
        logger.debug("Skip workflow reconciliation because another instance owns the lock")
        return 0

    renewal_task = asyncio.create_task(
        _renew_workflow_lock(cache, lock_token, lock_ttl),
        name="workflow-reconcile-lock-renewal",
    )
    reconcile_task = asyncio.create_task(
        _reconcile_workflow_runs(batch_size=batch_size),
        name="workflow-reconcile-work",
    )
    try:
        done, _ = await asyncio.wait(
            {reconcile_task, renewal_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if reconcile_task in done:
            return await reconcile_task

        renewal_error = renewal_task.exception()
        if renewal_error is not None:
            raise RuntimeError("Workflow reconcile lock renewal failed") from renewal_error
        raise RuntimeError("Workflow reconcile lock was lost")
    finally:
        if not reconcile_task.done():
            reconcile_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reconcile_task
        renewal_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await renewal_task
        await cache.delete_if_value(WORKFLOW_RECONCILE_LOCK_KEY, lock_token)


async def _reconcile_workflow_runs(*, batch_size: int | None) -> int:
    async with async_session_factory() as session:
        return await reconcile_waiting_workflow_runs(
            session,
            batch_size=batch_size or settings.WORKFLOW_RECONCILE_BATCH_SIZE,
            schedule_task_fn=create_and_schedule_tool_task,
        )


async def _renew_workflow_lock(cache, lock_token: str, lock_ttl: int) -> None:
    interval = max(lock_ttl / 3, 1.0)
    while True:
        await asyncio.sleep(interval)
        renewed = await cache.expire_if_value(
            WORKFLOW_RECONCILE_LOCK_KEY,
            lock_token,
            lock_ttl,
        )
        if not renewed:
            logger.warning("Workflow reconcile lock was lost during renewal")
            return


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
    "WORKFLOW_RECONCILE_LOCK_KEY",
    "WorkflowReconcileLoop",
    "reconcile_all_waiting_workflow_runs",
    "reconcile_waiting_workflow_runs",
    "workflow_reconcile_loop",
]
