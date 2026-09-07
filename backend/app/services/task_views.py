"""任务工作台系统视图查询。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.common.exceptions import ValidationException
from app.models.tasks import Task, TaskStatus
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


@dataclass(frozen=True)
class TaskQueryPage:
    """任务分页查询结果。"""

    tasks: list[Task]
    total: int


async def query_task_page(db: AsyncSession, query: TaskQueryInput) -> TaskQueryPage:
    """按系统视图和基础筛选查询当前用户可见任务。"""
    statement = select(Task).options(
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
        statement = statement.where(Task.extra_data["project_id"].as_string() == query.project_id)
    elif not is_admin:
        statement = statement.where(Task.user_id == query.current_user.id)

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

    if query.keyword:
        search_pattern = f"%{query.keyword}%"
        statement = (
            statement.join(Tool, Task.tool_id == Tool.id, isouter=True)
            .join(User, Task.user_id == User.id, isouter=True)
            .where(
                or_(
                    Task.id.ilike(search_pattern),
                    Task.name.ilike(search_pattern),
                    Tool.name.ilike(search_pattern),
                    Tool.slug.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                    User.display_name.ilike(search_pattern),
                )
            )
        )

    total = await _count_tasks(db, statement)
    page_size = max(query.page_size, 1)
    offset = (max(query.page, 1) - 1) * page_size
    result = await db.execute(
        statement.order_by(Task.created_at.desc()).offset(offset).limit(page_size)
    )
    return TaskQueryPage(tasks=list(result.scalars().all()), total=total)


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
