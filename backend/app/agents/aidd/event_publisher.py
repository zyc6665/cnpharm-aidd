"""Durable, monotonically ordered project Agent event publishing."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.conversations import AgentEvent
from app.realtime.agent_events import publish_agent_event_wakeup


class AgentEventPublisher:
    """Append Agent events in the same transaction as lifecycle state changes."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def append(
        self,
        *,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> AgentEvent:
        run = await self._db.scalar(
            select(AgentRun).where(AgentRun.id == run_id).with_for_update()
        )
        if run is None:
            raise ValueError(f"Agent run does not exist: {run_id}")
        last_sequence = await self._db.scalar(
            select(func.max(AgentEvent.sequence)).where(
                AgentEvent.agent_run_id == run_id
            )
        )
        event = AgentEvent(
            agent_run_id=run_id,
            sequence=(last_sequence or 0) + 1,
            event_type=event_type,
            payload=payload or {},
        )
        self._db.add(event)
        await self._db.flush()
        return event

    async def notify(self, run_id: str) -> None:
        await publish_agent_event_wakeup(run_id)
