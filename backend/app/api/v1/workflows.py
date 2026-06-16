"""工作流定义 API"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.database.session import get_db
from app.models.users import User
from app.models.workflows import WorkflowDefinition
from app.schemas.workflows import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionResponse,
    WorkflowDefinitionUpdate,
)


router = APIRouter()


def _serialize_workflow(workflow: WorkflowDefinition) -> dict[str, Any]:
    return WorkflowDefinitionResponse.model_validate(workflow).model_dump(mode="json")


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

    return success_response(
        data={
            "items": [_serialize_workflow(workflow) for workflow in workflows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
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
