"""Project conversation, durable event, and plan approval APIs."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.agents.aidd.project_service import ProjectAgentService, ProjectPlanResult
from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.models.agent import AgentRun, AgentRunStep
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
    ProjectAgentRunCreate,
)
from app.services.conversations import (
    append_message,
    branch_message,
    create_conversation,
    load_conversation_for_member,
)
from app.services.project_access import load_project_membership, require_project_role


router = APIRouter(
    dependencies=[Depends(require_feature_flag("AIDD_PROJECT_CONVERSATIONS_ENABLED"))]
)


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


def _plan_version_data(item: PlanVersion) -> dict:
    return {
        "id": item.id,
        "project_id": item.project_id,
        "conversation_id": item.conversation_id,
        "agent_run_id": item.agent_run_id,
        "created_by": item.created_by,
        "version": item.version,
        "content": item.content or {},
        "risk_level": item.risk_level,
        "status": item.status,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _agent_run_step_data(item: AgentRunStep) -> dict:
    return {
        "id": item.id,
        "step_key": item.step_key,
        "tool_slug": item.tool_slug,
        "tool_id": item.tool_id,
        "task_id": item.task_id,
        "status": item.status,
        "sort_order": item.sort_order,
        "depends_on_step_ids": item.depends_on_step_ids or [],
        "semantic_inputs": item.semantic_inputs or {},
        "semantic_outputs": item.semantic_outputs or {},
        "params": item.params or {},
        "input_file_ids": item.input_file_ids or [],
        "output_file_ids": item.output_file_ids or [],
        "error_message": item.error_message,
        "started_at": item.started_at,
        "finished_at": item.finished_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _agent_run_data(item: AgentRun) -> dict:
    steps = sorted(item.steps or [], key=lambda step: step.sort_order or 0)
    return {
        "id": item.id,
        "project_id": item.project_id,
        "user_id": item.user_id,
        "message": item.message,
        "intent": item.intent,
        "status": item.status,
        "input_type": item.input_type,
        "input_file_id": item.input_file_id,
        "requested_outputs": item.requested_outputs or [],
        "plan": item.plan or {},
        "summary": item.summary,
        "error_message": item.error_message,
        "finished_at": item.finished_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "steps": [_agent_run_step_data(step) for step in steps],
    }


def _project_plan_result_data(result: ProjectPlanResult) -> dict:
    data = {
        "id": result.run.id,
        "project_id": result.run.project_id,
        "conversation_id": (
            result.plan_version.conversation_id if result.plan_version else None
        ),
        "message": result.run.message,
        "intent": result.run.intent,
        "status": result.run.status,
        "input_type": result.run.input_type,
        "requested_outputs": result.run.requested_outputs or [],
        "plan": result.run.plan or {},
        "created_at": result.run.created_at,
        "updated_at": result.run.updated_at,
        "plan_version": (
            _plan_version_data(result.plan_version) if result.plan_version else None
        ),
    }
    return data


@router.get("/projects/{project_id}/conversations", response_model=dict)
async def list_conversations(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await load_project_membership(db, project_id=project_id, user_id=current_user.id)
    items = (
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.project_id == project_id)
                .order_by(Conversation.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return success_response(
        data={"items": [_conversation_data(item) for item in items]}
    )


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
        (
            await db.execute(
                query.order_by(ConversationMessage.created_at, ConversationMessage.id)
            )
        )
        .scalars()
        .all()
    )
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


@router.post(
    "/projects/{project_id}/conversations/{conversation_id}/agent-runs",
    response_model=dict,
)
async def create_project_agent_run(
    project_id: str,
    conversation_id: str,
    data: ProjectAgentRunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectAgentService(db)
    result = await service.create_plan(
        project_id=project_id,
        conversation_id=conversation_id,
        user=current_user,
        goal=data.goal,
        protein_artifact_version_id=data.protein_artifact_version_id,
    )
    return success_response(
        data=_project_plan_result_data(result),
        message="智能体计划已创建",
    )


@router.get("/projects/{project_id}/agent-runs", response_model=dict)
async def list_project_agent_runs(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectAgentService(db)
    runs = await service.list_project_runs(project_id=project_id, user=current_user)
    total = len(runs)
    start = (page - 1) * page_size
    return success_response(
        data={
            "items": [_agent_run_data(run) for run in runs[start : start + page_size]],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/projects/{project_id}/agent-runs/{run_id}", response_model=dict)
async def get_project_agent_run(
    project_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await ProjectAgentService(db).get_project_run(
        project_id=project_id,
        run_id=run_id,
        user=current_user,
    )
    return success_response(data=_agent_run_data(run))


@router.post("/projects/{project_id}/agent-runs/{run_id}/cancel", response_model=dict)
async def cancel_project_agent_run(
    project_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await ProjectAgentService(db).cancel_project_run(
        project_id=project_id,
        run_id=run_id,
        user=current_user,
    )
    return success_response(data=_agent_run_data(run), message="智能体运行已取消")


@router.post("/messages/{message_id}/branch", response_model=dict)
async def create_message_branch(
    message_id: str,
    data: MessageBranchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source = (
        await db.execute(
            select(ConversationMessage).where(ConversationMessage.id == message_id)
        )
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
    run = (
        await db.execute(select(AgentRun).where(AgentRun.id == run_id))
    ).scalar_one_or_none()
    if run is None or run.project_id is None:
        raise HTTPException(status_code=404, detail="智能体运行不存在")
    await load_project_membership(
        db, project_id=run.project_id, user_id=current_user.id
    )
    events = (
        (
            await db.execute(
                select(AgentEvent)
                .where(
                    AgentEvent.agent_run_id == run.id,
                    AgentEvent.sequence > after_sequence,
                )
                .order_by(AgentEvent.sequence)
            )
        )
        .scalars()
        .all()
    )
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
) -> tuple[PlanVersion, dict]:
    plan = (
        await db.execute(select(PlanVersion).where(PlanVersion.id == plan_id))
    ).scalar_one_or_none()
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
    await _sync_approval_message_status(db, plan=plan)
    await db.flush()
    return (
        plan,
        {
            "id": plan.id,
            "status": plan.status,
            "decision": {
                "id": record.id,
                "reviewer_id": record.reviewer_id,
                "decision": record.decision,
                "comment": record.comment,
                "created_at": record.created_at,
            },
        },
    )


async def _sync_approval_message_status(
    db: AsyncSession,
    *,
    plan: PlanVersion,
) -> None:
    if not plan.conversation_id:
        return
    messages = (
        (
            await db.execute(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == plan.conversation_id
                )
            )
        )
        .scalars()
        .all()
    )
    for message in messages:
        content = list(message.content or [])
        changed = False
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "approval_ref"
                and block.get("plan_id") == plan.id
            ):
                block["status"] = plan.status
                changed = True
        if changed:
            message.content = content
            flag_modified(message, "content")


@router.post("/plan-versions/{plan_id}/approve", response_model=dict)
async def approve_plan(
    plan_id: str,
    data: PlanDecisionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan, decision_data = await _decide_plan(
        plan_id,
        "approve",
        data,
        current_user,
        db,
    )
    if plan.agent_run_id:
        submission = await ProjectAgentService(db).submit_approved_plan(
            plan_version_id=plan.id,
            user=current_user,
        )
        decision_data["execution"] = submission.as_execution_payload()
    else:
        await db.commit()
    return success_response(
        data=decision_data,
        message="计划已批准",
    )


@router.post("/plan-versions/{plan_id}/reject", response_model=dict)
async def reject_plan(
    plan_id: str,
    data: PlanDecisionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _, decision_data = await _decide_plan(plan_id, "reject", data, current_user, db)
    await db.commit()
    return success_response(
        data=decision_data,
        message="计划已驳回",
    )
