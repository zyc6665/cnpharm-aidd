"""Project conversation, durable event, and plan approval APIs."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.database.session import get_db
from app.models.agent import AgentRun
from app.models.conversations import (
    AgentEvent,
    Conversation,
    ConversationMessage,
    PlanDecision,
    PlanVersion,
)
from app.models.users import User
from app.schemas.conversations import (
    ConversationCreate,
    MessageBranchCreate,
    MessageCreate,
    PlanDecisionCreate,
)
from app.services.conversations import (
    append_message,
    branch_message,
    create_conversation,
    load_conversation_for_member,
)
from app.services.project_access import load_project_membership, require_project_role


router = APIRouter()


def _conversation_data(item: Conversation, root_branch_id: str | None = None) -> dict:
    return {
        "id": item.id,
        "project_id": item.project_id,
        "created_by": item.created_by,
        "title": item.title,
        "status": item.status,
        "root_branch_id": root_branch_id,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _message_data(item: ConversationMessage) -> dict:
    return {
        "id": item.id,
        "conversation_id": item.conversation_id,
        "branch_id": item.branch_id,
        "author_id": item.author_id,
        "parent_message_id": item.parent_message_id,
        "role": item.role,
        "content": item.content or [],
        "plain_text": item.plain_text,
        "sequence": item.sequence,
        "created_at": item.created_at,
    }


@router.get("/projects/{project_id}/conversations", response_model=dict)
async def list_conversations(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)
    items = (
        await db.execute(
            select(Conversation)
            .where(Conversation.project_id == project_id)
            .order_by(Conversation.updated_at.desc())
        )
    ).scalars().all()
    return success_response(data={"items": [_conversation_data(item) for item in items]})


@router.post("/projects/{project_id}/conversations", response_model=dict)
async def create_project_conversation(
    project_id: str,
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation, branch = await create_conversation(
        db, project_id=project_id, user=current_user, title=data.title
    )
    await db.commit()
    return success_response(
        data=_conversation_data(conversation, branch.id), message="会话已创建"
    )


@router.get("/conversations/{conversation_id}/messages", response_model=dict)
async def list_messages(
    conversation_id: str,
    branch_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation, _ = await load_conversation_for_member(
        db, conversation_id=conversation_id, user_id=current_user.id
    )
    query = select(ConversationMessage).where(
        ConversationMessage.conversation_id == conversation.id
    )
    if branch_id:
        query = query.where(ConversationMessage.branch_id == branch_id)
    items = (
        await db.execute(query.order_by(ConversationMessage.created_at, ConversationMessage.id))
    ).scalars().all()
    return success_response(data={"items": [_message_data(item) for item in items]})


@router.post("/conversations/{conversation_id}/messages", response_model=dict)
async def create_message(
    conversation_id: str,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation, _ = await load_conversation_for_member(
        db, conversation_id=conversation_id, user_id=current_user.id
    )
    message = await append_message(
        db,
        conversation=conversation,
        user=current_user,
        role=data.role,
        content=data.content,
        branch_id=data.branch_id,
    )
    await db.commit()
    return success_response(data=_message_data(message), message="消息已创建")


@router.post("/messages/{message_id}/branch", response_model=dict)
async def create_message_branch(
    message_id: str,
    data: MessageBranchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source = (
        await db.execute(select(ConversationMessage).where(ConversationMessage.id == message_id))
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    await load_conversation_for_member(
        db, conversation_id=source.conversation_id, user_id=current_user.id
    )
    branch, message = await branch_message(
        db, source=source, user=current_user, content=data.content, title=data.title
    )
    await db.commit()
    return success_response(
        data={
            "branch": {
                "id": branch.id,
                "parent_branch_id": branch.parent_branch_id,
                "forked_from_message_id": branch.forked_from_message_id,
                "title": branch.title,
            },
            "message": _message_data(message),
        },
        message="消息分支已创建",
    )


@router.get("/agent-runs/{run_id}/events", response_model=dict)
async def list_agent_events(
    run_id: str,
    after_sequence: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
    if run is None or run.project_id is None:
        raise HTTPException(status_code=404, detail="智能体运行不存在")
    await load_project_membership(db, project_id=run.project_id, user_id=current_user.id)
    events = (
        await db.execute(
            select(AgentEvent)
            .where(AgentEvent.agent_run_id == run.id, AgentEvent.sequence > after_sequence)
            .order_by(AgentEvent.sequence)
        )
    ).scalars().all()
    return success_response(
        data={
            "items": [
                {
                    "id": event.id,
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "payload": event.payload or {},
                    "created_at": event.created_at,
                }
                for event in events
            ]
        }
    )


async def _decide_plan(
    plan_id: str,
    decision: str,
    data: PlanDecisionCreate,
    current_user: User,
    db: AsyncSession,
) -> dict:
    plan = (await db.execute(select(PlanVersion).where(PlanVersion.id == plan_id))).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="计划版本不存在")
    await require_project_role(
        db,
        project_id=plan.project_id,
        user=current_user,
        allowed_roles={"owner", "runner"},
    )
    if plan.status != "pending":
        raise HTTPException(status_code=409, detail="计划版本已完成决策")
    record = PlanDecision(
        plan_version_id=plan.id,
        reviewer_id=current_user.id,
        decision=decision,
        comment=data.comment,
        created_at=datetime.now(timezone.utc),
    )
    plan.status = "approved" if decision == "approve" else "rejected"
    db.add(record)
    await db.commit()
    return {
        "id": plan.id,
        "status": plan.status,
        "decision": {
            "id": record.id,
            "reviewer_id": record.reviewer_id,
            "decision": record.decision,
            "comment": record.comment,
            "created_at": record.created_at,
        },
    }


@router.post("/plan-versions/{plan_id}/approve", response_model=dict)
async def approve_plan(
    plan_id: str,
    data: PlanDecisionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return success_response(
        data=await _decide_plan(plan_id, "approve", data, current_user, db),
        message="计划已批准",
    )


@router.post("/plan-versions/{plan_id}/reject", response_model=dict)
async def reject_plan(
    plan_id: str,
    data: PlanDecisionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return success_response(
        data=await _decide_plan(plan_id, "reject", data, current_user, db),
        message="计划已驳回",
    )
