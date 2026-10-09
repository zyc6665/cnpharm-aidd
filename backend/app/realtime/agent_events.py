"""Database-first SSE delivery for durable agent events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from time import monotonic
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent import AgentRun
from app.models.conversations import AgentEvent


HEARTBEAT_INTERVAL_SECONDS = 15.0
POLL_INTERVAL_SECONDS = 1.0
TERMINAL_RUN_STATUSES = {
    "success",
    "failure",
    "canceled",
    "completed",
    "failed",
    "cancelled",
    "stopped",
}
AGENT_EVENT_CHANNEL_PREFIX = "scitool:agent-events:"

logger = logging.getLogger(__name__)


class AgentEventWakeup(Protocol):
    """Wake a stream so it can re-read durable events from the database."""

    async def wait(self, timeout: float) -> None: ...

    async def close(self) -> None: ...


class PollingAgentEventWakeup:
    """Portable fallback used when Redis is disabled or unavailable."""

    async def wait(self, timeout: float) -> None:
        await asyncio.sleep(timeout)

    async def close(self) -> None:
        return None


class RedisAgentEventWakeup:
    """One cancellable Redis Pub/Sub subscription for an SSE connection."""

    def __init__(self, client, pubsub, channel: str) -> None:
        self._client = client
        self._pubsub = pubsub
        self._channel = channel
        self._closed = False

    async def wait(self, timeout: float) -> None:
        await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with suppress(Exception):
            await self._pubsub.unsubscribe(self._channel)
        with suppress(Exception):
            await self._pubsub.aclose()
        with suppress(Exception):
            await self._client.aclose()


def _agent_event_channel(run_id: str) -> str:
    return f"{AGENT_EVENT_CHANNEL_PREFIX}{run_id}"


def _new_redis_client():
    import redis.asyncio as redis

    return redis.from_url(
        settings.effective_redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


async def _connect_redis_wakeup(run_id: str) -> RedisAgentEventWakeup:
    client = _new_redis_client()
    pubsub = client.pubsub()
    channel = _agent_event_channel(run_id)
    try:
        await pubsub.subscribe(channel)
    except Exception:
        with suppress(Exception):
            await pubsub.aclose()
        with suppress(Exception):
            await client.aclose()
        raise
    return RedisAgentEventWakeup(client, pubsub, channel)


async def create_agent_event_wakeup(run_id: str) -> AgentEventWakeup:
    """Create a Redis subscriber, falling back to bounded database polling."""
    if settings.CACHE_BACKEND != "redis":
        return PollingAgentEventWakeup()
    try:
        return await _connect_redis_wakeup(run_id)
    except Exception as exc:
        logger.warning("Agent event Redis subscription unavailable; using polling: %s", exc)
        return PollingAgentEventWakeup()


async def publish_agent_event_wakeup(run_id: str) -> bool:
    """Notify followers after an AgentEvent transaction has been committed."""
    if settings.CACHE_BACKEND != "redis":
        return False
    client = None
    try:
        client = _new_redis_client()
        await client.publish(_agent_event_channel(run_id), "event")
        return True
    except Exception as exc:
        logger.warning("Agent event Redis publish failed; durable event remains available: %s", exc)
        return False
    finally:
        if client is not None:
            with suppress(Exception):
                await client.aclose()


def format_sse_event(event: AgentEvent) -> str:
    """Serialize one persisted event using the platform SSE contract."""
    data = json.dumps(
        {"run_id": event.agent_run_id, "payload": event.payload or {}},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {data}\n\n"


async def stream_agent_events(
    db: AsyncSession,
    *,
    run_id: str,
    after_sequence: int = 0,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    wakeup: AgentEventWakeup | None = None,
) -> AsyncIterator[str]:
    """Replay durable events, then follow the run until it reaches a terminal state.

    The database remains the source of truth. Polling is intentionally retained as
    a fallback wake-up mechanism so Redis outages cannot interrupt event recovery.
    """
    active_wakeup = wakeup
    try:
        last_sequence = after_sequence
        last_output_at = monotonic()

        while True:
            events = (
                await db.execute(
                    select(AgentEvent)
                    .where(
                        AgentEvent.agent_run_id == run_id,
                        AgentEvent.sequence > last_sequence,
                    )
                    .order_by(AgentEvent.sequence)
                )
            ).scalars().all()
            for event in events:
                last_sequence = event.sequence
                last_output_at = monotonic()
                yield format_sse_event(event)

            run_status = await db.scalar(select(AgentRun.status).where(AgentRun.id == run_id))
            if run_status is None or run_status in TERMINAL_RUN_STATUSES:
                return

            elapsed = monotonic() - last_output_at
            if elapsed >= heartbeat_interval:
                last_output_at = monotonic()
                yield ": heartbeat\n\n"
                continue

            if active_wakeup is None:
                # Subscribe only after replay, then query once more to close the race
                # between the first database read and subscription establishment.
                active_wakeup = await create_agent_event_wakeup(run_id)
                continue
            try:
                await active_wakeup.wait(min(poll_interval, heartbeat_interval - elapsed))
            except Exception as exc:
                logger.warning("Agent event wakeup failed; using polling: %s", exc)
                await active_wakeup.close()
                active_wakeup = PollingAgentEventWakeup()
    finally:
        if active_wakeup is not None:
            await active_wakeup.close()
