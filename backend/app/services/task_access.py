"""集中管理任务读取与操作权限。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ForbiddenException
from app.common.task_context import task_project_id
from app.models.tasks import Task
from app.models.users import User
from app.services.project_access import load_project_membership, require_project_role


TASK_OPERATION_PROJECT_ROLES = {"owner", "editor", "runner"}


def _is_admin(user: User) -> bool:
    return user.role == "admin"


async def ensure_task_read_access(
    db: AsyncSession,
    *,
    task: Task,
    current_user: User,
) -> None:
    """Require that a user may read task status, logs, and results."""
    if _is_admin(current_user) or task.user_id == current_user.id:
        return
    project_id = task_project_id(task)
    if project_id:
        await load_project_membership(
            db,
            project_id=project_id,
            user_id=current_user.id,
        )
        return
    raise ForbiddenException("无权访问此任务")


async def ensure_task_operation_access(
    db: AsyncSession,
    *,
    task: Task,
    current_user: User,
) -> None:
    """Require that a user may cancel or retry a task."""
    if _is_admin(current_user) or task.user_id == current_user.id:
        return
    project_id = task_project_id(task)
    if project_id:
        await require_project_role(
            db,
            project_id=project_id,
            user=current_user,
            allowed_roles=TASK_OPERATION_PROJECT_ROLES,
        )
        return
    raise ForbiddenException("无权操作此任务")


async def load_task_for_read_access(
    db: AsyncSession,
    *,
    task_id: str,
    current_user: User,
) -> Task:
    """Load a task without revealing whether unauthorized IDs exist."""
    task = await db.get(Task, task_id)
    if task is None:
        raise ForbiddenException("无权访问此任务")
    await ensure_task_read_access(db, task=task, current_user=current_user)
    return task


__all__ = [
    "TASK_OPERATION_PROJECT_ROLES",
    "ensure_task_operation_access",
    "ensure_task_read_access",
    "load_task_for_read_access",
]
