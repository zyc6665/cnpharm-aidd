"""Workflow run query helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ForbiddenException, NotFoundException
from app.common.keyset import apply_desc_keyset, encode_cursor, next_cursor
from app.models.users import User
from app.models.workflows import WorkflowDefinition, WorkflowRun
from app.services.project_access import load_project_membership
from app.services.workflow_run_access import is_admin


@dataclass(frozen=True)
class WorkflowRunPage:
    """工作流运行列表的一页。

    ``total`` 在游标模式为 ``None``（游标模式不计算 count）；``next_cursor`` /
    ``has_more`` 供前端「加载更多」。
    """

    runs: list[WorkflowRun]
    total: int | None
    next_cursor: str | None
    has_more: bool


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
    cursor: str | None = None,
) -> WorkflowRunPage:
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

    if cursor:
        # 游标模式：不算 count，多取一条判 hasMore；排序键 (created_at DESC, id DESC) 全序。
        query, _last = apply_desc_keyset(
            query,
            timestamp_column=WorkflowRun.created_at,
            id_column=WorkflowRun.id,
            cursor=cursor,
        )
        result = await db.execute(
            query.order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc()).limit(
                page_size + 1
            )
        )
        fetched = list(result.scalars().all())
        has_more = len(fetched) > page_size
        return WorkflowRunPage(
            runs=fetched[:page_size],
            total=None,
            next_cursor=next_cursor(
                fetched,
                timestamp_attr="created_at",
                id_attr="id",
                limit=page_size,
            ),
            has_more=has_more,
        )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = list(result.scalars().all())
    has_more = offset + len(rows) < total
    return WorkflowRunPage(
        runs=rows,
        total=total,
        next_cursor=(
            encode_cursor([rows[-1].created_at, rows[-1].id])
            if rows and has_more
            else None
        ),
        has_more=has_more,
    )


async def get_workflow_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> WorkflowRun:
    return await load_run_for_user(db, run_id=run_id, current_user=current_user)
