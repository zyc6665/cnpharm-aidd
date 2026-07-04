"""Workflow API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.models.users import User
from app.models.workflows import WorkflowDefinition, WorkflowRun, WorkflowTemplate
from app.schemas.workflows import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionResponse,
    WorkflowDefinitionUpdate,
    WorkflowRunCreate,
    WorkflowTemplateCreate,
    WorkflowTemplateDuplicate,
    WorkflowTemplateUpdate,
)
from app.services.workflows import create_workflow_run, sync_workflow_run
from app.services.workflow_runs import get_workflow_run, list_workflow_runs
from app.services.workflow_templates import (
    create_workflow_template,
    delete_workflow_template,
    duplicate_workflow_template,
    get_workflow_template,
    list_workflow_templates,
    update_workflow_template,
)


router = APIRouter()


def _serialize_workflow(workflow: WorkflowDefinition) -> dict[str, Any]:
    return WorkflowDefinitionResponse.model_validate(workflow).model_dump(mode="json")


def _serialize_template(template: WorkflowTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "owner_id": template.owner_id,
        "name": template.name,
        "description": template.description,
        "status": template.status,
        "definition": template.definition or {},
        "is_public": template.is_public,
        "version": template.version,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def _serialize_run(run: WorkflowRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "owner_id": run.owner_id,
        "template_id": run.template_id,
        "name": run.name,
        "status": run.status,
        "definition": run.definition or {},
        "input_files": run.input_files or {},
        "execution_order": run.execution_order or [],
        "node_states": run.node_states or {},
        "artifact_lineage": run.artifact_lineage or {},
        "error_message": run.error_message,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


async def _get_owned_workflow(
    workflow_id: str,
    current_user: User,
    db: AsyncSession,
) -> WorkflowDefinition:
    result = await db.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.user_id == current_user.id,
        )
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return workflow


@router.get("", response_model=dict)
async def list_workflow_definitions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户保存的工作流定义。"""
    base_query = select(WorkflowDefinition).where(WorkflowDefinition.user_id == current_user.id)
    total_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = total_result.scalar_one()

    result = await db.execute(
        base_query
        .order_by(WorkflowDefinition.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    workflows = result.scalars().all()

    return paginated_response(
        items=[_serialize_workflow(workflow) for workflow in workflows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=dict)
async def create_workflow_definition(
    workflow_data: WorkflowDefinitionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存新的工作流定义。"""
    workflow = WorkflowDefinition(
        user_id=current_user.id,
        **workflow_data.model_dump(),
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)

    return success_response(data=_serialize_workflow(workflow), message="工作流已保存")


@router.post("/templates", response_model=dict)
async def create_template(
    data: WorkflowTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await create_workflow_template(db, current_user=current_user, data=data)
    return success_response(data=_serialize_template(template), message="工作流模板已保存")


@router.get("/templates", response_model=dict)
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    templates = await list_workflow_templates(db, current_user=current_user)
    return paginated_response(
        items=[_serialize_template(template) for template in templates],
        total=len(templates),
        page=1,
        page_size=len(templates),
    )


@router.post("/templates/{template_id}/duplicate", response_model=dict)
async def duplicate_template(
    template_id: str,
    data: WorkflowTemplateDuplicate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await duplicate_workflow_template(
        db,
        current_user=current_user,
        template_id=template_id,
        data=data,
    )
    return success_response(data=_serialize_template(template), message="工作流模板已复制")


@router.post("/templates/{template_id}/runs", response_model=dict)
async def create_run(
    template_id: str,
    data: WorkflowRunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await create_workflow_run(
        db,
        current_user=current_user,
        template_id=template_id,
        data=data,
    )
    return success_response(data=_serialize_run(run), message="工作流运行已创建")


@router.get("/templates/{template_id}", response_model=dict)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await get_workflow_template(
        db,
        current_user=current_user,
        template_id=template_id,
    )
    return success_response(data=_serialize_template(template))


@router.get("/runs", response_model=dict)
async def list_runs(
    template_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    runs, total = await list_workflow_runs(
        db,
        current_user=current_user,
        template_id=template_id,
        page=page,
        page_size=page_size,
    )
    return paginated_response(
        items=[_serialize_run(run) for run in runs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/runs/{run_id}", response_model=dict)
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await get_workflow_run(
        db,
        current_user=current_user,
        run_id=run_id,
    )
    return success_response(data=_serialize_run(run))


@router.post("/runs/{run_id}/sync", response_model=dict)
async def sync_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await sync_workflow_run(
        db,
        current_user=current_user,
        run_id=run_id,
    )
    return success_response(data=_serialize_run(run), message="工作流运行已同步")


@router.put("/templates/{template_id}", response_model=dict)
async def update_template(
    template_id: str,
    data: WorkflowTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = await update_workflow_template(
        db,
        current_user=current_user,
        template_id=template_id,
        data=data,
    )
    return success_response(data=_serialize_template(template), message="工作流模板已更新")


@router.delete("/templates/{template_id}", response_model=dict)
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await delete_workflow_template(
        db,
        current_user=current_user,
        template_id=template_id,
    )
    return success_response(data=result, message="工作流模板已删除")


@router.get("/{workflow_id}", response_model=dict)
async def get_workflow_definition(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个工作流定义。"""
    workflow = await _get_owned_workflow(workflow_id, current_user, db)
    return success_response(data=_serialize_workflow(workflow))


@router.put("/{workflow_id}", response_model=dict)
async def update_workflow_definition(
    workflow_id: str,
    workflow_data: WorkflowDefinitionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户的工作流定义。"""
    workflow = await _get_owned_workflow(workflow_id, current_user, db)
    updates = workflow_data.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(workflow, field, value)

    await db.commit()
    await db.refresh(workflow)

    return success_response(data=_serialize_workflow(workflow), message="工作流已更新")


@router.delete("/{workflow_id}", response_model=dict)
async def delete_workflow_definition(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除当前用户的工作流定义。"""
    workflow = await _get_owned_workflow(workflow_id, current_user, db)
    await db.delete(workflow)
    await db.commit()

    return success_response(message="工作流已删除")
