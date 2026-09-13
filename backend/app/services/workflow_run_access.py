"""Workflow run access checks."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ForbiddenException
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.services.project_access import require_project_role


WORKFLOW_RUN_OPERATION_PROJECT_ROLES = {"owner", "editor", "runner"}


def is_admin(user: User) -> bool:
    return user.role == "admin"


async def ensure_run_operation_access(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    current_user: User,
) -> None:
    if is_admin(current_user) or run.owner_id == current_user.id:
        return
    if run.project_id:
        await require_project_role(
            db,
            project_id=run.project_id,
            user=current_user,
            allowed_roles=WORKFLOW_RUN_OPERATION_PROJECT_ROLES,
        )
        return
    raise ForbiddenException("No permission to operate workflow run")
