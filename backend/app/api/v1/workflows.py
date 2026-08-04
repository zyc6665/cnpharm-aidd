"""Workflow API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.models.users import User
from app.models.workflows import WorkflowDefinition, WorkflowRun
from app.schemas.workflows import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionResponse,
    WorkflowDefinitionUpdate,
    WorkflowRunCreate,
)
from app.services.project_access import load_project_membership
from app.services.workflows import create_workflow_run, sync_workflow_run
from app.services.workflow_runs import get_workflow_run, list_workflow_runs


router = APIRouter()


def _serialize_workflow(workflow: WorkflowDefinition) -> dict[str, Any]:
    return WorkflowDefinitionResponse.model_validate(workflow).model_dump(mode="json")


def _serialize_run(run: WorkflowRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "owner_id": run.owner_id,
        "workflow_definition_id": run.workflow_definition_id,
        "project_id": run.project_id,
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
    if workflow.project_id:
        await load_project_membership(
            db,
            project_id=workflow.project_id,
            user_id=current_user.id,
        )
    return workflow


async def _validate_workflow_project_access(
    db: AsyncSession,
    *,
    project_id: str | None,
    current_user: User,
) -> None:
    if not project_id:
        return
    await load_project_membership(
        db,
        project_id=project_id,
        user_id=current_user.id,
    )


@router.get("", response_model=dict)
async def list_workflow_definitions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: Annotated[str | None, Query(min_length=1, max_length=36)] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户保存的工作流定义。"""
    await _validate_workflow_project_access(
        db,
        project_id=project_id,
        current_user=current_user,
    )
    base_query = select(WorkflowDefinition).where(WorkflowDefinition.user_id == current_user.id)
    if project_id:
        base_query = base_query.where(WorkflowDefinition.project_id == project_id)
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
    await _validate_workflow_project_access(
        db,
        project_id=workflow_data.project_id,
        current_user=current_user,
    )
    workflow = WorkflowDefinition(
        user_id=current_user.id,
        **workflow_data.model_dump(),
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)

    return success_response(data=_serialize_workflow(workflow), message="工作流已保存")


@router.get("/runs", response_model=dict)
async def list_runs(
    workflow_definition_id: str | None = None,
    project_id: Annotated[str | None, Query(min_length=1, max_length=36)] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    runs, total = await list_workflow_runs(
        db,
        current_user=current_user,
        workflow_definition_id=workflow_definition_id,
        project_id=project_id,
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


@router.post("/{workflow_id}/runs", response_model=dict)
async def create_run(
    workflow_id: str,
    data: WorkflowRunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await create_workflow_run(
        db,
        current_user=current_user,
        workflow_definition_id=workflow_id,
        data=data,
    )
    return success_response(data=_serialize_run(run), message="工作流运行已创建")


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
    if "project_id" in updates:
        await _validate_workflow_project_access(
            db,
            project_id=updates["project_id"],
            current_user=current_user,
        )

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
