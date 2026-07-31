"""Research project APIs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.database.session import get_db
from app.models.projects import Organization, Project, ProjectMember
from app.models.users import User
from app.schemas.projects import ProjectCreate, ProjectMemberCreate, ProjectUpdate
from app.services.project_access import load_project_membership, require_project_role

router = APIRouter()
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
        await db.execute(select(Organization).where(Organization.slug == DEFAULT_ORGANIZATION_SLUG))
    ).scalar_one_or_none()
    if organization is None:
        organization = Organization(name="Default Organization", slug=DEFAULT_ORGANIZATION_SLUG)
        db.add(organization)
        await db.flush()
    return organization


@router.get("", response_model=dict)
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project, ProjectMember)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == current_user.id)
        .order_by(Project.updated_at.desc())
    )
    return success_response(data={"items": [_serialize(project, member) for project, member in result.all()]})


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
    membership = ProjectMember(project_id=project.id, user_id=current_user.id, role="owner")
    db.add(membership)
    await db.commit()
    await db.refresh(project)
    await db.refresh(membership)
    return success_response(data=_serialize(project, membership), message="研究项目已创建")


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
    return success_response(data=_serialize(project, membership), message="研究项目已更新")


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
    user = (await db.execute(select(User).where(User.email == data.email))).scalar_one_or_none()
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
        data={"id": membership.id, "user_id": user.id, "email": user.email, "role": membership.role},
        message="项目成员已添加",
    )
