"""任务工作台系统视图查询。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.common.exceptions import ValidationException
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import Tool
from app.models.users import User
from app.services.project_access import load_project_membership


TaskSystemView = Literal["all", "running", "history", "needs_attention", "recent_results"]

_VIEW_STATUSES: dict[str, tuple[str, ...]] = {
    "running": (TaskStatus.PENDING.value, TaskStatus.RUNNING.value),
    "history": (TaskStatus.SUCCESS.value, TaskStatus.FAILURE.value, TaskStatus.CANCELED.value),
    "needs_attention": (TaskStatus.FAILURE.value,),
    "recent_results": (TaskStatus.SUCCESS.value,),
}


@dataclass(frozen=True)
class TaskQueryInput:
    """任务查询输入，承载系统视图、权限上下文和基础筛选。"""

    current_user: User
    page: int = 1
    page_size: int = 20
    view: str | None = None
    status: str | None = None
    tool_id: str | None = None
    keyword: str | None = None
    project_id: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    workflow_run_id: str | None = None
    workflow_definition_id: str | None = None
    workflow_node_id: str | None = None


@dataclass(frozen=True)
class TaskQueryPage:
    """任务分页查询结果。"""

    tasks: list[Task]
    total: int


@dataclass(frozen=True)
class TaskViewCounts:
    """任务系统视图计数。"""

    all: int
    running: int
    history: int
    needs_attention: int
    recent_results: int


async def query_task_page(db: AsyncSession, query: TaskQueryInput) -> TaskQueryPage:
    """按系统视图和基础筛选查询当前用户可见任务。"""
    statement = await _build_task_statement(
        db,
        query,
        include_view_filters=True,
        include_load_options=True,
    )

    total = await _count_tasks(db, statement)
    page_size = max(query.page_size, 1)
    offset = (max(query.page, 1) - 1) * page_size
    result = await db.execute(
        statement.order_by(Task.created_at.desc()).offset(offset).limit(page_size)
    )
    return TaskQueryPage(tasks=list(result.scalars().all()), total=total)


async def query_task_view_counts(db: AsyncSession, query: TaskQueryInput) -> TaskViewCounts:
    """按同一权限和筛选条件返回各系统视图计数。"""
    statement = await _build_task_statement(
        db,
        query,
        include_view_filters=False,
        include_load_options=False,
    )
    status_subquery = statement.with_only_columns(Task.status.label("status")).subquery()
    result = await db.execute(
        select(status_subquery.c.status, func.count())
        .select_from(status_subquery)
        .group_by(status_subquery.c.status)
    )
    counts_by_status = {str(status): int(count) for status, count in result.all()}
    return TaskViewCounts(
        all=sum(counts_by_status.values()),
        running=_sum_status_counts(counts_by_status, _VIEW_STATUSES["running"]),
        history=_sum_status_counts(counts_by_status, _VIEW_STATUSES["history"]),
        needs_attention=_sum_status_counts(counts_by_status, _VIEW_STATUSES["needs_attention"]),
        recent_results=_sum_status_counts(counts_by_status, _VIEW_STATUSES["recent_results"]),
    )


async def _build_task_statement(
    db: AsyncSession,
    query: TaskQueryInput,
    *,
    include_view_filters: bool,
    include_load_options: bool,
):
    statement = select(Task)
    if include_load_options:
        statement = statement.options(
            selectinload(Task.tool),
            joinedload(Task.user),
        )

    is_admin = query.current_user.role == "admin"
    if query.project_id:
        if not is_admin:
            await load_project_membership(
                db,
                project_id=query.project_id,
                user_id=query.current_user.id,
            )
        statement = statement.where(Task.project_id_expression() == query.project_id)
    elif not is_admin:
        statement = statement.where(Task.user_id == query.current_user.id)

    if include_view_filters:
        view_statuses = _statuses_for_view(query.view)
        if view_statuses:
            statement = statement.where(Task.status.in_(view_statuses))

        if query.status:
            statement = statement.where(Task.status == query.status.upper())

    if query.tool_id:
        statement = statement.where(Task.tool_id == query.tool_id)

    if query.created_from:
        statement = statement.where(Task.created_at >= _naive_utc(query.created_from))
    if query.created_to:
        statement = statement.where(Task.created_at <= _naive_utc(query.created_to))

    if query.workflow_run_id or query.workflow_definition_id or query.workflow_node_id:
        statement = statement.join(TaskInput, TaskInput.task_id == Task.id)
        if query.workflow_run_id:
            statement = statement.where(
                TaskInput.params["workflow_run_id"].as_string() == query.workflow_run_id
            )
        if query.workflow_definition_id:
            statement = statement.where(
                TaskInput.params["workflow_definition_id"].as_string()
                == query.workflow_definition_id
            )
        if query.workflow_node_id:
            statement = statement.where(
                TaskInput.params["workflow_node_id"].as_string() == query.workflow_node_id
            )

    if query.keyword:
        search_pattern = f"%{query.keyword}%"
        statement = (
            statement.join(Tool, Task.tool_id == Tool.id, isouter=True)
            .join(User, Task.user_id == User.id, isouter=True)
            .where(
                or_(
                    Task.id.ilike(search_pattern),
                    Task.name.ilike(search_pattern),
                    Task.error_message.ilike(search_pattern),
                    Task.progress_message.ilike(search_pattern),
                    Tool.name.ilike(search_pattern),
                    Tool.slug.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                    User.display_name.ilike(search_pattern),
                )
            )
        )

    return statement


def _sum_status_counts(counts_by_status: dict[str, int], statuses: tuple[str, ...]) -> int:
    return sum(counts_by_status.get(status, 0) for status in statuses)


def _statuses_for_view(view: str | None) -> tuple[str, ...]:
    if not view or view == "all":
        return ()
    statuses = _VIEW_STATUSES.get(view)
    if statuses is None:
        raise ValidationException("未知任务系统视图", detail={"view": view})
    return statuses


async def _count_tasks(db: AsyncSession, statement) -> int:
    result = await db.execute(select(func.count()).select_from(statement.subquery()))
    return int(result.scalar() or 0)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
