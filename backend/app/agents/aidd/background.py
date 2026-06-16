"""Background reconciliation loop for AIDD agent runs."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from app.database.session import async_session_factory

logger = logging.getLogger(__name__)


class AgentReconcileLoop:
    """Periodically reconcile agent steps whose platform tasks finished."""

    def __init__(
        self,
        *,
        reconcile: Callable[[], Awaitable[object]],
        interval_seconds: float = 5.0,
    ) -> None:
        self._reconcile = reconcile
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    @property
    def task(self) -> asyncio.Task | None:
        return self._task

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="aidd-agent-reconcile-loop")

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
                logger.exception("AIDD agent background reconciliation failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                continue


async def reconcile_all_waiting_agent_steps() -> int:
    from app.agents.aidd.service import reconcile_waiting_agent_steps

    async with async_session_factory() as session:
        return await reconcile_waiting_agent_steps(session)


agent_reconcile_loop = AgentReconcileLoop(reconcile=reconcile_all_waiting_agent_steps)
