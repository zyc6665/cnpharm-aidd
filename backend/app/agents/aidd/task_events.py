"""Bridge platform Task lifecycle changes back into project Agent events."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.models.agent import AgentRun
from app.models.conversations import AgentEvent
from app.models.tasks import Task
from app.realtime.agent_events import publish_agent_event_wakeup


TERMINAL_AGENT_STATUSES = {"success", "failure", "canceled"}


def _agent_run_id(task: Task) -> str | None:
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    run_id = data.get("agent_run_id")
    return str(run_id) if run_id else None


def _base_payload(task: Task) -> dict[str, Any]:
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    payload: dict[str, Any] = {"task_id": str(task.id)}
    for key in ("project_id", "plan_version_id"):
        value = data.get(key)
        if value:
            payload[key] = str(value)
    return payload


async def append_task_agent_event(
    db: AsyncSession,
    *,
    task: Task,
    event_type: str,
    payload: dict[str, Any] | None = None,
    run_status: str | None = None,
    error_message: str | None = None,
    flush: bool = True,
) -> str | None:
    """Append an AgentEvent for project-Agent-owned tasks and return the run id."""
    run_id = _agent_run_id(task)
    if not run_id:
        return None

    with db.no_autoflush:
        run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        if run is None:
            return None

        if run_status:
            run.status = run_status
            if run_status in TERMINAL_AGENT_STATUSES:
                run.finished_at = utcnow()
        if error_message:
            run.error_message = error_message

        last_sequence = await db.scalar(
            select(func.max(AgentEvent.sequence)).where(AgentEvent.agent_run_id == run_id)
        )
        event = AgentEvent(
            agent_run_id=run_id,
            sequence=(last_sequence or 0) + 1,
            event_type=event_type,
            payload={**_base_payload(task), **(payload or {})},
        )
        db.add(event)

    if flush:
        await db.flush()
    return run_id


async def notify_task_agent_event(run_id: str | None) -> None:
    """Wake Agent SSE consumers after the event transaction has committed."""
    if run_id:
        await publish_agent_event_wakeup(run_id)
