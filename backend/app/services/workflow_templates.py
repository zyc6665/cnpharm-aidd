"""Workflow template persistence service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ForbiddenException, NotFoundException
from app.models.users import User
from app.models.workflows import WorkflowTemplate
from app.schemas.workflows import (
    WorkflowTemplateCreate,
    WorkflowTemplateDuplicate,
    WorkflowTemplateUpdate,
)
from app.services.workflow_validation import validate_workflow_definition


async def load_template_for_user(
    db: AsyncSession,
    *,
    template_id: str,
    current_user: User,
) -> WorkflowTemplate:
    result = await db.execute(
        select(WorkflowTemplate)
        .options(selectinload(WorkflowTemplate.runs))
        .where(WorkflowTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException("Workflow template not found")
    if template.owner_id != current_user.id and not template.is_public and current_user.role != "admin":
        raise ForbiddenException("No permission to access workflow template")
    return template


async def create_workflow_template(
    db: AsyncSession,
    *,
    current_user: User,
    data: WorkflowTemplateCreate,
) -> WorkflowTemplate:
    validate_workflow_definition(data.definition)
    template = WorkflowTemplate(
        owner_id=current_user.id,
        name=data.name,
        description=data.description,
        definition=data.definition,
        is_public=data.is_public,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def list_workflow_templates(
    db: AsyncSession,
    *,
    current_user: User,
) -> list[WorkflowTemplate]:
    query = select(WorkflowTemplate).order_by(WorkflowTemplate.updated_at.desc())
    if current_user.role != "admin":
        query = query.where(
            (WorkflowTemplate.owner_id == current_user.id) | WorkflowTemplate.is_public.is_(True)
        )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_workflow_template(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str,
) -> WorkflowTemplate:
    return await load_template_for_user(db, template_id=template_id, current_user=current_user)


async def update_workflow_template(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str,
    data: WorkflowTemplateUpdate,
) -> WorkflowTemplate:
    template = await load_template_for_user(db, template_id=template_id, current_user=current_user)
    if template.owner_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException("No permission to update workflow template")
    if data.name is not None:
        template.name = data.name
    if data.description is not None:
        template.description = data.description
    if data.definition is not None:
        validate_workflow_definition(data.definition)
        template.definition = data.definition
        template.version += 1
    if data.is_public is not None:
        template.is_public = data.is_public
    if data.status is not None:
        template.status = data.status
    await db.commit()
    await db.refresh(template)
    return template


async def duplicate_workflow_template(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str,
    data: WorkflowTemplateDuplicate,
) -> WorkflowTemplate:
    template = await load_template_for_user(db, template_id=template_id, current_user=current_user)
    duplicated = WorkflowTemplate(
        owner_id=current_user.id,
        name=data.name or f"{template.name} Copy",
        description=template.description,
        definition=dict(template.definition or {}),
        is_public=False,
        version=1,
    )
    db.add(duplicated)
    await db.commit()
    await db.refresh(duplicated)
    return duplicated


async def delete_workflow_template(
    db: AsyncSession,
    *,
    current_user: User,
    template_id: str,
) -> dict[str, str]:
    template = await load_template_for_user(db, template_id=template_id, current_user=current_user)
    if template.owner_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException("No permission to delete workflow template")
    deleted_id = template.id
    await db.delete(template)
    await db.commit()
    return {"id": deleted_id}
