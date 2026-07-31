"""Centralized research project access checks."""

from collections.abc import Collection

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.projects import Project, ProjectMember
from app.models.users import User


async def load_project_membership(
    db: AsyncSession,
    *,
    project_id: str,
    user_id: str,
) -> tuple[Project, ProjectMember]:
    result = await db.execute(
        select(Project, ProjectMember)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(Project.id == project_id, ProjectMember.user_id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return row[0], row[1]


async def require_project_role(
    db: AsyncSession,
    *,
    project_id: str,
    user: User,
    allowed_roles: Collection[str],
) -> tuple[Project, ProjectMember]:
    project, membership = await load_project_membership(
        db,
        project_id=project_id,
        user_id=user.id,
    )
    if membership.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="没有执行此项目操作的权限")
    return project, membership
