"""Idempotent migration of user-owned legacy resources into research projects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.files import File
from app.models.projects import Organization, Project, ProjectMember
from app.models.users import User
from app.models.workflows import ResearchBoard, WorkflowDefinition, WorkflowRun


DEFAULT_ORGANIZATION_SLUG = "default"
MIGRATION_POLICY_KEY = "migration_default"


@dataclass(frozen=True)
class ProjectBackfillResult:
    users_processed: int
    projects_created: int
    resources_linked: int
    unowned_resources: int


RESOURCE_OWNERS: tuple[tuple[type[Any], Any], ...] = (
    (File, File.owner_id),
    (AgentRun, AgentRun.user_id),
    (WorkflowDefinition, WorkflowDefinition.user_id),
    (WorkflowRun, WorkflowRun.owner_id),
    (ResearchBoard, ResearchBoard.owner_id),
)


async def _legacy_owner_ids(db: AsyncSession) -> set[str]:
    owner_ids: set[str] = set()
    for model, owner_column in RESOURCE_OWNERS:
        result = await db.execute(
            select(owner_column).where(model.project_id.is_(None), owner_column.is_not(None)).distinct()
        )
        owner_ids.update(str(owner_id) for owner_id in result.scalars())
    return owner_ids


async def _count_unowned_resources(db: AsyncSession) -> int:
    result = await db.execute(
        select(File.id).where(File.project_id.is_(None), File.owner_id.is_(None))
    )
    return len(result.scalars().all())


async def _migration_project_by_owner(db: AsyncSession, owner_ids: set[str]) -> dict[str, Project]:
    if not owner_ids:
        return {}
    result = await db.execute(select(Project).where(Project.created_by.in_(owner_ids)))
    projects: dict[str, Project] = {}
    for project in result.scalars():
        if (project.data_policy or {}).get(MIGRATION_POLICY_KEY) is True:
            projects.setdefault(str(project.created_by), project)
    return projects


async def _default_organization(db: AsyncSession) -> Organization:
    result = await db.execute(
        select(Organization).where(Organization.slug == DEFAULT_ORGANIZATION_SLUG)
    )
    organization = result.scalar_one_or_none()
    if organization is None:
        organization = Organization(name="默认组织", slug=DEFAULT_ORGANIZATION_SLUG)
        db.add(organization)
        await db.flush()
    return organization


async def ensure_migration_project_for_owner(db: AsyncSession, user: User) -> Project:
    """Return the stable default project used for legacy or context-free resources."""

    owner_id = str(user.id)
    existing_projects = await _migration_project_by_owner(db, {owner_id})
    existing = existing_projects.get(owner_id)
    if existing is not None:
        return existing

    organization = await _default_organization(db)
    project = Project(
        organization_id=organization.id,
        created_by=owner_id,
        name="默认项目",
        goal="承接未显式选择项目时创建的科研资源",
        status="active",
        data_policy={MIGRATION_POLICY_KEY: True},
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=owner_id, role="owner"))
    await db.flush()
    return project


async def backfill_legacy_projects(
    db: AsyncSession,
    *,
    dry_run: bool = False,
) -> ProjectBackfillResult:
    """Link every attributable legacy resource to one stable migration project per owner."""

    owner_ids = await _legacy_owner_ids(db)
    unowned_resources = await _count_unowned_resources(db)
    existing_projects = await _migration_project_by_owner(db, owner_ids)

    resources_to_link = 0
    for model, owner_column in RESOURCE_OWNERS:
        result = await db.execute(
            select(model.id).where(model.project_id.is_(None), owner_column.in_(owner_ids))
        )
        resources_to_link += len(result.scalars().all())

    missing_owner_ids = owner_ids - set(existing_projects)
    if dry_run or not owner_ids:
        return ProjectBackfillResult(
            users_processed=len(owner_ids),
            projects_created=len(missing_owner_ids),
            resources_linked=resources_to_link,
            unowned_resources=unowned_resources,
        )

    organization = await _default_organization(db)
    users = {
        str(user.id): user
        for user in (
            await db.execute(select(User).where(User.id.in_(missing_owner_ids)))
        ).scalars()
    }
    for owner_id in sorted(missing_owner_ids):
        user = users.get(owner_id)
        if user is None:
            continue
        project = Project(
            organization_id=organization.id,
            created_by=owner_id,
            name="迁移项目",
            goal="承接升级前创建的科研资源",
            status="active",
            data_policy={MIGRATION_POLICY_KEY: True},
        )
        db.add(project)
        await db.flush()
        db.add(ProjectMember(project_id=project.id, user_id=owner_id, role="owner"))
        existing_projects[owner_id] = project

    linked = 0
    for owner_id, project in existing_projects.items():
        for model, owner_column in RESOURCE_OWNERS:
            statement = (
                update(model)
                .where(model.project_id.is_(None), owner_column == owner_id)
                .values(project_id=project.id, updated_at=model.updated_at)
            )
            result = await db.execute(statement)
            linked += result.rowcount or 0
    await db.flush()

    return ProjectBackfillResult(
        users_processed=len(owner_ids),
        projects_created=len(existing_projects) - (len(owner_ids) - len(missing_owner_ids)),
        resources_linked=linked,
        unowned_resources=unowned_resources,
    )
