"""Research project APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.models.agent import AgentRun, AgentRunStep
from app.models.artifacts import Artifact, ArtifactLineage, ArtifactVersion
from app.models.conversations import (
    AgentEvent,
    Conversation,
    ConversationBranch,
    ConversationMessage,
    PlanDecision,
    PlanVersion,
)
from app.models.executions import ExecutionRecord
from app.models.files import File
from app.models.projects import Organization, Project, ProjectMember
from app.models.users import User
from app.models.workflows import (
    ResearchBoard,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowTemplate,
)
from app.schemas.projects import ProjectCreate, ProjectMemberCreate, ProjectUpdate
from app.services.project_access import load_project_membership, require_project_role

router = APIRouter(
    dependencies=[Depends(require_feature_flag("AIDD_PROJECT_WORKSPACE_ENABLED"))]
)
DEFAULT_ORGANIZATION_SLUG = "default"


def _serialize(project: Project, membership: ProjectMember) -> dict:
    return {
        "id": project.id,
        "organization_id": project.organization_id,
        "created_by": project.created_by,
        "name": project.name,
        "goal": project.goal,
        "status": project.status,
        "model_policy": project.model_policy or {},
        "data_policy": project.data_policy or {},
        "membership": {"id": membership.id, "role": membership.role},
        "created_at": project.created_at,
        "updated_at": project.updated_at,
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
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
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
    agent_run_ids = list(
        (
            await db.execute(
                select(AgentRun.id).where(AgentRun.project_id == project_id)
            )
        ).scalars()
    )
    if agent_run_ids:
        await db.execute(
            sa_delete(AgentEvent).where(AgentEvent.agent_run_id.in_(agent_run_ids))
        )
        await db.execute(
            sa_delete(AgentRunStep).where(AgentRunStep.agent_run_id.in_(agent_run_ids))
        )
        await db.execute(sa_delete(AgentRun).where(AgentRun.id.in_(agent_run_ids)))

    plan_version_ids = list(
        (
            await db.execute(
                select(PlanVersion.id).where(PlanVersion.project_id == project_id)
            )
        ).scalars()
    )
    if plan_version_ids:
        await db.execute(
            sa_delete(PlanDecision).where(
                PlanDecision.plan_version_id.in_(plan_version_ids)
            )
        )
    await db.execute(sa_delete(PlanVersion).where(PlanVersion.project_id == project_id))

    conversation_ids = list(
        (
            await db.execute(
                select(Conversation.id).where(Conversation.project_id == project_id)
            )
        ).scalars()
    )
    if conversation_ids:
        await db.execute(
            sa_delete(ConversationMessage).where(
                ConversationMessage.conversation_id.in_(conversation_ids)
            )
        )
        await db.execute(
            sa_delete(ConversationBranch).where(
                ConversationBranch.conversation_id.in_(conversation_ids)
            )
        )
    await db.execute(
        sa_delete(Conversation).where(Conversation.project_id == project_id)
    )

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

    template_ids = list(
        (
            await db.execute(
                select(WorkflowTemplate.id).where(WorkflowTemplate.project_id == project_id)
            )
        ).scalars()
    )
    if template_ids:
        await db.execute(
            sa_update(WorkflowRun)
            .where(WorkflowRun.template_id.in_(template_ids))
            .values(template_id=None)
        )

    await db.execute(sa_delete(ExecutionRecord).where(ExecutionRecord.project_id == project_id))
    await db.execute(sa_delete(WorkflowRun).where(WorkflowRun.project_id == project_id))
    await db.execute(sa_delete(WorkflowTemplate).where(WorkflowTemplate.project_id == project_id))
    await db.execute(
        sa_delete(WorkflowDefinition).where(WorkflowDefinition.project_id == project_id)
    )
    await db.execute(sa_delete(ResearchBoard).where(ResearchBoard.project_id == project_id))
    await db.execute(
        sa_update(File).where(File.project_id == project_id).values(project_id=None)
    )
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
    return success_response(
        data={
            "id": membership.id,
            "user_id": user.id,
            "email": user.email,
            "role": membership.role,
        },
        message="项目成员已添加",
    )
