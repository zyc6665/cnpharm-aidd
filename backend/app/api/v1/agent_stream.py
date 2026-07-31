"""Recoverable Server-Sent Events endpoint for agent runs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.agent import AgentRun
from app.models.users import User
from app.realtime.agent_events import stream_agent_events
from app.services.project_access import load_project_membership


router = APIRouter()


def _resume_sequence(last_event_id: str | None, after_sequence: int) -> int:
    if last_event_id is None or not last_event_id.strip():
        return after_sequence
    try:
        header_sequence = int(last_event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Last-Event-ID 必须是非负整数") from exc
    if header_sequence < 0:
        raise HTTPException(status_code=400, detail="Last-Event-ID 必须是非负整数")
    return max(after_sequence, header_sequence)


@router.get("/agent-runs/{run_id}/stream")
async def stream_run_events(
    run_id: str,
    after_sequence: int = Query(0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
    if run is None or run.project_id is None:
        raise HTTPException(status_code=404, detail="智能体运行不存在")
    await load_project_membership(db, project_id=run.project_id, user_id=current_user.id)

    return StreamingResponse(
        stream_agent_events(
            db,
            run_id=run.id,
            after_sequence=_resume_sequence(last_event_id, after_sequence),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
