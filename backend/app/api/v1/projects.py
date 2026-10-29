"""Research project APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.common.exceptions import ConflictException
from app.common.responses import success_response
from app.common.time import utcnow
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.models.artifacts import Artifact, ArtifactLineage, ArtifactVersion
from app.models.executions import ExecutionRecord
from app.models.files import File
from app.models.projects import Organization, Project, ProjectMember
from app.models.quotas import ProjectQuota
from app.models.tasks import Task
from app.models.users import User
from app.models.workflows import (
    ResearchBoard,
    WorkflowDefinition,
    WorkflowRun,
)
from app.schemas.projects import (
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberUpdate,
    ProjectUpdate,
)
from app.services.domain_compounds import (
    delete_project_compound_rows,
    project_compound_counts,
)
from app.services.domain_targets import delete_project_domain_rows, project_domain_counts
from app.services.project_access import load_project_membership, require_project_role

router = APIRouter(
    dependencies=[Depends(require_feature_flag("AIDD_PROJECT_WORKSPACE_ENABLED"))]
)
DEFAULT_ORGANIZATION_SLUG = "default"


def _serialize(project: Project, membership: ProjectMember | None) -> dict:
    return {
        "id": project.id,
        "organization_id": project.organization_id,
        "created_by": project.created_by,
        "name": project.name,
        "goal": project.goal,
        "status": project.status,
        "model_policy": project.model_policy or {},
        "data_policy": project.data_policy or {},
        "version": project.version,
        # Platform admins bypass membership, so this may legitimately be None.
        "membership": (
            {"id": membership.id, "role": membership.role}
            if membership is not None
            else None
        ),
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def _serialize_member(membership: ProjectMember) -> dict:
    user = membership.user
    return {
        "id": membership.id,
        "project_id": membership.project_id,
        "user_id": membership.user_id,
        "email": user.email if user else None,
        "display_name": user.display_name if user else None,
        "role": membership.role,
        "created_at": membership.created_at,
        "updated_at": membership.updated_at,
    }


def _serialize_artifact_version(version: ArtifactVersion) -> dict:
    return {
        "id": version.id,
        "version": version.version,
        "filename": version.filename,
        "content_type": version.content_type,
        "size_bytes": version.size_bytes,
        "sha256": version.sha256,
        "status": version.status,
        "expires_at": version.expires_at,
        "created_at": version.created_at,
    }


def _serialize_artifact(artifact: Artifact) -> dict:
    return {
        "id": artifact.id,
        "project_id": artifact.project_id,
        "artifact_type": artifact.artifact_type,
        "semantic_type": artifact.semantic_type,
        "standard_type": artifact.standard_type,
        "standard_version": artifact.standard_version,
        "name": artifact.name,
        "description": artifact.description,
        "latest_version": _serialize_artifact_version(artifact.latest_version),
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }


def _serialize_project_task(task: Task) -> dict:
    return {
        "id": task.id,
        "name": task.name,
        "status": (task.status or "").lower(),
        "progress": task.progress,
        "progress_message": task.progress_message,
        "error_message": task.error_message,
        "tool_id": task.tool_id,
        "tool_name": task.tool.name if task.tool else None,
        "tool_slug": task.tool.slug if task.tool else None,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _serialize_workflow_definition(workflow: WorkflowDefinition) -> dict:
    return {
        "id": workflow.id,
        "project_id": workflow.project_id,
        "name": workflow.name,
        "description": workflow.description,
        "status": workflow.status,
        "updated_at": workflow.updated_at,
        "created_at": workflow.created_at,
    }


async def _get_or_create_default_organization(db: AsyncSession) -> Organization:
    organization = (
        await db.execute(
            select(Organization).where(Organization.slug == DEFAULT_ORGANIZATION_SLUG)
        )
    ).scalar_one_or_none()
    if organization is None:
        organization = Organization(
            name="Default Organization", slug=DEFAULT_ORGANIZATION_SLUG
        )
        db.add(organization)
        await db.flush()
    return organization


@router.get("", response_model=dict)
async def list_projects(
    include_archived: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Project, ProjectMember)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == current_user.id)
        .order_by(Project.updated_at.desc())
    )
    if not include_archived:
        query = query.where(Project.status != "archived")
    result = await db.execute(query)
    return success_response(
        data={
            "items": [_serialize(project, member) for project, member in result.all()]
        }
    )


@router.post("", response_model=dict)
async def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    organization = await _get_or_create_default_organization(db)
    project = Project(
        organization_id=organization.id,
        created_by=current_user.id,
        **data.model_dump(),
    )
    db.add(project)
    await db.flush()
    membership = ProjectMember(
        project_id=project.id, user_id=current_user.id, role="owner"
    )
    db.add(membership)
    await db.commit()
    await db.refresh(project)
    await db.refresh(membership)
    return success_response(
        data=_serialize(project, membership), message="研究项目已创建"
    )


@router.get("/{project_id}", response_model=dict)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project, membership = await load_project_membership(
        db,
        project_id=project_id,
        user_id=current_user.id,
    )
    return success_response(data=_serialize(project, membership))


@router.get("/{project_id}/overview", response_model=dict)
async def get_project_overview(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project, membership = await load_project_membership(
        db,
        project_id=project_id,
        user_id=current_user.id,
    )
    task_filter = Task.project_id_expression() == project_id
    artifact_filter = (
        Artifact.project_id == project_id,
        ArtifactVersion.status == "available",
        or_(ArtifactVersion.expires_at.is_(None), ArtifactVersion.expires_at > utcnow()),
    )

    task_result = await db.execute(
        select(Task)
        .options(selectinload(Task.tool))
        .where(task_filter)
        .order_by(Task.updated_at.desc())
        .limit(8)
    )
    artifact_result = await db.execute(
        select(Artifact)
        .options(selectinload(Artifact.latest_version))
        .join(ArtifactVersion, ArtifactVersion.id == Artifact.latest_version_id)
        .where(*artifact_filter)
        .order_by(Artifact.updated_at.desc())
        .limit(8)
    )
    workflow_result = await db.execute(
        select(WorkflowDefinition)
        .where(WorkflowDefinition.project_id == project_id)
        .order_by(WorkflowDefinition.updated_at.desc())
        .limit(8)
    )
    task_count = await db.scalar(select(func.count(Task.id)).where(task_filter))
    artifact_count = await db.scalar(
        select(func.count(Artifact.id))
        .join(ArtifactVersion, ArtifactVersion.id == Artifact.latest_version_id)
        .where(*artifact_filter)
    )
    workflow_count = await db.scalar(
        select(func.count(WorkflowDefinition.id)).where(
            WorkflowDefinition.project_id == project_id
        )
    )
    domain_counts = await project_domain_counts(db, project_id=project_id)
    compound_counts = await project_compound_counts(db, project_id=project_id)
    return success_response(
        data={
            "project": _serialize(project, membership),
            "counts": {
                "artifacts": artifact_count or 0,
                "tasks": task_count or 0,
                "workflows": workflow_count or 0,
                "targets": domain_counts["targets"],
                "structures": domain_counts["structures"],
                "pockets": domain_counts["pockets"],
                "candidates": compound_counts["candidates"],
                "candidate_sets": compound_counts["candidate_sets"],
            },
            "tasks": [_serialize_project_task(task) for task in task_result.scalars()],
            "artifacts": [
                _serialize_artifact(artifact) for artifact in artifact_result.scalars()
            ],
            "workflows": [
                _serialize_workflow_definition(workflow)
                for workflow in workflow_result.scalars()
            ],
        }
    )


@router.patch("/{project_id}", response_model=dict)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project, membership = await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles={"owner", "editor"},
    )
    values = data.model_dump(exclude_unset=True, exclude={"expected_version"})
    expected_version = data.expected_version
    values["updated_at"] = utcnow()
    if expected_version is not None:
        values["version"] = expected_version + 1
        result = await db.execute(
            sa_update(Project)
            .where(Project.id == project_id, Project.version == expected_version)
            .values(**values)
        )
        if result.rowcount == 0:
            await db.rollback()
            current_version = (
                await db.execute(
                    select(Project.version).where(Project.id == project_id)
                )
            ).scalar_one_or_none()
            raise ConflictException(
                "项目已被其他人修改，请刷新后重试",
                detail={"currentVersion": current_version},
            )
    else:
        values["version"] = (project.version or 1) + 1
        await db.execute(
            sa_update(Project).where(Project.id == project_id).values(**values)
        )
    await db.commit()
    await db.refresh(project)
    return success_response(
        data=_serialize(project, membership), message="研究项目已更新"
    )


@router.post("/{project_id}/archive", response_model=dict)
async def archive_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project, membership = await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles={"owner", "editor"},
    )
    project.status = "archived"
    await db.commit()
    await db.refresh(project)
    return success_response(data=_serialize(project, membership), message="研究项目已归档")


async def _delete_project_related_rows(db: AsyncSession, project_id: str) -> None:
    artifact_ids = list(
        (
            await db.execute(select(Artifact.id).where(Artifact.project_id == project_id))
        ).scalars()
    )
    if artifact_ids:
        await db.execute(
            sa_update(Artifact)
            .where(Artifact.id.in_(artifact_ids))
            .values(latest_version_id=None)
        )
        await db.execute(
            sa_delete(ArtifactLineage).where(ArtifactLineage.project_id == project_id)
        )
        await db.execute(
            sa_delete(ArtifactVersion).where(ArtifactVersion.artifact_id.in_(artifact_ids))
        )
        await db.execute(sa_delete(Artifact).where(Artifact.id.in_(artifact_ids)))

    await db.execute(sa_delete(ExecutionRecord).where(ExecutionRecord.project_id == project_id))
    await db.execute(sa_delete(WorkflowRun).where(WorkflowRun.project_id == project_id))
    await db.execute(
        sa_delete(WorkflowDefinition).where(WorkflowDefinition.project_id == project_id)
    )
    await db.execute(sa_delete(ResearchBoard).where(ResearchBoard.project_id == project_id))
    await db.execute(
        sa_update(File).where(File.project_id == project_id).values(project_id=None)
    )
    await delete_project_compound_rows(db, project_id=project_id)
    await delete_project_domain_rows(db, project_id=project_id)
    # 配额是项目的一等附属行，必须在删项目之前显式清掉：`project_quotas.project_id`
    # 是普通外键（SQLite 默认不强制），留着孤儿行会让重建同名项目沿用旧配额，
    # 也会让 `GET /compute/quota` 把已删项目的额度继续算进分母。
    await db.execute(sa_delete(ProjectQuota).where(ProjectQuota.project_id == project_id))
    await db.execute(sa_delete(ProjectMember).where(ProjectMember.project_id == project_id))


@router.delete("/{project_id}", response_model=dict)
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project, _membership = await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles={"owner"},
    )
    deleted_id = project.id
    await _delete_project_related_rows(db, project_id=project.id)
    await db.delete(project)
    await db.commit()
    return success_response(data={"id": deleted_id}, message="研究项目已删除")


@router.get("/{project_id}/members", response_model=dict)
async def list_project_members(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await load_project_membership(
        db,
        project_id=project_id,
        user_id=current_user.id,
    )
    members = (
        (
            await db.execute(
                select(ProjectMember)
                .options(selectinload(ProjectMember.user))
                .where(ProjectMember.project_id == project_id)
                .order_by(ProjectMember.created_at.asc(), ProjectMember.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return success_response(
        data={"items": [_serialize_member(member) for member in members]}
    )


@router.post("/{project_id}/members", response_model=dict)
async def add_project_member(
    project_id: str,
    data: ProjectMemberCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles={"owner"},
    )
    user = (
        await db.execute(select(User).where(User.email == data.email))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    existing = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="用户已经是项目成员")
    membership = ProjectMember(project_id=project_id, user_id=user.id, role=data.role)
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    await db.refresh(user)
    membership.user = user
    return success_response(
        data=_serialize_member(membership),
        message="项目成员已添加",
    )


async def _load_project_member_or_404(
    db: AsyncSession,
    *,
    project_id: str,
    membership_id: str,
) -> ProjectMember:
    membership = (
        await db.execute(
            select(ProjectMember)
            .options(selectinload(ProjectMember.user))
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.id == membership_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="项目成员不存在")
    return membership


async def _project_owner_count(db: AsyncSession, project_id: str) -> int:
    return (
        await db.scalar(
            select(func.count(ProjectMember.id)).where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == "owner",
            )
        )
        or 0
    )


@router.patch("/{project_id}/members/{membership_id}", response_model=dict)
async def update_project_member(
    project_id: str,
    membership_id: str,
    data: ProjectMemberUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles={"owner"},
    )
    membership = await _load_project_member_or_404(
        db,
        project_id=project_id,
        membership_id=membership_id,
    )
    if membership.role == "owner" and data.role != "owner":
        raise HTTPException(status_code=400, detail="不能修改项目 owner 角色")
    membership.role = data.role
    await db.commit()
    await db.refresh(membership)
    return success_response(data=_serialize_member(membership), message="项目成员已更新")


@router.delete("/{project_id}/members/{membership_id}", response_model=dict)
async def remove_project_member(
    project_id: str,
    membership_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles={"owner"},
    )
    membership = await _load_project_member_or_404(
        db,
        project_id=project_id,
        membership_id=membership_id,
    )
    if membership.role == "owner" and await _project_owner_count(db, project_id) <= 1:
        raise HTTPException(status_code=400, detail="不能移除项目最后一个 owner")
    removed_id = membership.id
    await db.delete(membership)
    await db.commit()
    return success_response(data={"id": removed_id}, message="项目成员已移除")
