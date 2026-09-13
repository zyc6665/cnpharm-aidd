"""Workflow run query helpers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ForbiddenException, NotFoundException
from app.models.users import User
from app.models.workflows import WorkflowDefinition, WorkflowRun
from app.services.project_access import load_project_membership
from app.services.workflow_run_access import is_admin


async def load_run_for_user(
    db: AsyncSession,
    *,
    run_id: str,
    current_user: User,
) -> WorkflowRun:
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise NotFoundException("Workflow run not found")
    if run.project_id:
        if not is_admin(current_user):
            await load_project_membership(
                db,
                project_id=run.project_id,
                user_id=current_user.id,
            )
        return run
    if run.owner_id != current_user.id and not is_admin(current_user):
        raise ForbiddenException("No permission to access workflow run")
    return run


async def load_definition_for_run(
    db: AsyncSession,
    *,
    workflow_definition_id: str,
    current_user: User,
) -> WorkflowDefinition:
    result = await db.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.id == workflow_definition_id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise NotFoundException("Workflow definition not found")
    if workflow.project_id:
        if not is_admin(current_user):
            await load_project_membership(
                db,
                project_id=workflow.project_id,
                user_id=current_user.id,
            )
        return workflow
    if workflow.user_id != current_user.id and not is_admin(current_user):
        raise NotFoundException("Workflow definition not found")
    return workflow


async def list_workflow_runs(
    db: AsyncSession,
    *,
    current_user: User,
    workflow_definition_id: str | None = None,
    project_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[WorkflowRun], int]:
    if workflow_definition_id and not project_id:
        workflow = await load_definition_for_run(
            db,
            workflow_definition_id=workflow_definition_id,
            current_user=current_user,
        )
        project_id = workflow.project_id
    if project_id:
        if not is_admin(current_user):
            await load_project_membership(
                db,
                project_id=project_id,
                user_id=current_user.id,
            )
        query = select(WorkflowRun).where(WorkflowRun.project_id == project_id)
    else:
        query = select(WorkflowRun).where(WorkflowRun.owner_id == current_user.id)
    if workflow_definition_id:
        query = query.where(WorkflowRun.workflow_definition_id == workflow_definition_id)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0
    result = await db.execute(
        query
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> WorkflowRun:
    return await load_run_for_user(db, run_id=run_id, current_user=current_user)
