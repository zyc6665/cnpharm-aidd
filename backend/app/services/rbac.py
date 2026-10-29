"""Project-scoped RBAC matrix and guard (plan §4).

The platform previously had two different notions of "project access":
``require_project_role`` (a fixed allowed-role set) and ad-hoc membership loads.
This module gives one declarative matrix so every entry point can ask for the
*minimum action* it needs instead of hand-picking role strings.

Ranking
-------
``viewer < runner < editor < owner``. ``runner`` is intentionally above
``viewer``: read-only viewers must not be able to submit compute tasks, while a
runner may run but not edit project data. ``admin`` is not a project role; it is
a platform role that bypasses membership entirely (see ``require_project_action``).
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.projects import Project, ProjectMember
from app.models.users import User
from app.services.project_access import load_project_membership

PROJECT_ROLE_RANK = {"viewer": 1, "runner": 2, "editor": 3, "owner": 4}

PROJECT_ACTIONS = {
    "read": {"viewer"},
    "run": {"runner", "editor", "owner"},
    "write": {"editor", "owner"},
    "admin": {"owner"},
}


def role_allows(role: str | None, action: str) -> bool:
    """Return whether ``role`` satisfies ``action``.

    ``PROJECT_ACTIONS`` lists the *minimum* role(s) for an action, so the check
    is rank-based: any role at or above the action's lowest listed role passes
    (``read`` lists ``viewer`` → every project role may read). Unknown roles and
    unknown actions are denied (fail closed).
    """
    rank = PROJECT_ROLE_RANK.get(role)
    allowed = PROJECT_ACTIONS.get(action)
    if rank is None or not allowed:
        return False
    required_rank = min(PROJECT_ROLE_RANK[item] for item in allowed)
    return rank >= required_rank


async def require_project_action(
    db: AsyncSession,
    *,
    project_id: str,
    user: User,
    action: str,
) -> tuple[Project, ProjectMember | None]:
    """Require a minimum project ``action`` for ``user``.

    Platform admins bypass membership: they get the project with a possibly
    ``None`` membership instead of a 404. Every other user must be a member and
    hold a role that satisfies ``action``.
    """
    if action not in PROJECT_ACTIONS:
        raise ValueError(f"unknown project action: {action}")

    project, membership = await load_project_membership(
        db,
        project_id=project_id,
        user_id=user.id,
    )
    if getattr(user, "role", None) == "admin":
        return project, membership
    if not role_allows(membership.role if membership else None, action):
        raise HTTPException(status_code=403, detail="没有执行此项目操作的权限")
    return project, membership
