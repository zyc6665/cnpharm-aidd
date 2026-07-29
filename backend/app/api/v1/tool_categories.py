"""工具分类管理 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_admin_user
from app.common.exceptions import ConflictException, NotFoundException, ValidationException
from app.common.responses import success_response
from app.database.session import get_db
from app.models.tools import Tool, ToolCategory
from app.models.users import User
from app.schemas.tools import (
    ToolCategoryCreate,
    ToolCategoryReorderRequest,
    ToolCategoryResponse,
    ToolCategoryStatusUpdate,
    ToolCategoryUpdate,
)


router = APIRouter(prefix="/admin/tool-categories", tags=["工具分类管理"])


def _serialize_category(category: ToolCategory, tool_count: int | None = None) -> dict:
    data = ToolCategoryResponse.model_validate(category).model_dump()
    if tool_count is not None:
        data["tool_count"] = tool_count
        data["count"] = tool_count
    return data


@router.get("", response_model=dict)
async def list_tool_categories(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员获取全部工具分类。"""
    result = await db.execute(
        select(ToolCategory, func.count(Tool.id).label("tool_count"))
        .outerjoin(Tool, Tool.category_id == ToolCategory.id)
        .group_by(ToolCategory.id)
        .order_by(ToolCategory.sort_order.asc(), ToolCategory.created_at.asc())
    )
    categories = [_serialize_category(category, tool_count) for category, tool_count in result.all()]
    return success_response(data=categories)


@router.post("", response_model=dict)
async def create_tool_category(
    category_data: ToolCategoryCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员创建工具分类。"""
    existing = await db.execute(
        select(ToolCategory).where(
            or_(ToolCategory.name == category_data.name, ToolCategory.slug == category_data.slug)
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException("工具分类名称或标识已存在")

    sort_order = category_data.sort_order
    if "sort_order" not in category_data.model_fields_set:
        max_sort_result = await db.execute(select(func.max(ToolCategory.sort_order)))
        sort_order = (max_sort_result.scalar() or 0) + 1

    category = ToolCategory(
        name=category_data.name,
        slug=category_data.slug,
        description=category_data.description,
        sort_order=sort_order,
        is_enabled=category_data.is_enabled,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return success_response(data=_serialize_category(category), message="工具分类创建成功")


@router.put("/{category_id}", response_model=dict)
async def update_tool_category(
    category_id: str,
    category_data: ToolCategoryUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员更新工具分类。"""
    result = await db.execute(select(ToolCategory).where(ToolCategory.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise NotFoundException("工具分类不存在")

    update_data = category_data.model_dump(exclude_unset=True)
    if "name" in update_data or "slug" in update_data:
        conflict_conditions = []
        if "name" in update_data:
            conflict_conditions.append(ToolCategory.name == update_data["name"])
        if "slug" in update_data:
            conflict_conditions.append(ToolCategory.slug == update_data["slug"])
        conflict_result = await db.execute(
            select(ToolCategory).where(
                ToolCategory.id != category_id,
                or_(*conflict_conditions),
            )
        )
        if conflict_result.scalar_one_or_none():
            raise ConflictException("工具分类名称或标识已存在")

    for field, value in update_data.items():
        setattr(category, field, value)

    await db.commit()
    await db.refresh(category)
    return success_response(data=_serialize_category(category), message="工具分类更新成功")


@router.patch("/{category_id}/status", response_model=dict)
async def update_tool_category_status(
    category_id: str,
    status_data: ToolCategoryStatusUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员更新工具分类启用状态。"""
    result = await db.execute(select(ToolCategory).where(ToolCategory.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise NotFoundException("工具分类不存在")

    category.is_enabled = status_data.is_enabled
    await db.commit()
    await db.refresh(category)
    return success_response(data=_serialize_category(category), message="工具分类状态更新成功")


@router.post("/reorder", response_model=dict)
async def reorder_tool_categories(
    reorder_data: ToolCategoryReorderRequest,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员重排工具分类。"""
    result = await db.execute(
        select(ToolCategory).where(ToolCategory.id.in_(reorder_data.category_ids))
    )
    categories = {category.id: category for category in result.scalars().all()}
    if len(categories) != len(reorder_data.category_ids):
        raise ValidationException("存在无效的工具分类ID")

    for index, category_id in enumerate(reorder_data.category_ids):
        categories[category_id].sort_order = index

    await db.commit()
    ordered_categories = [_serialize_category(categories[category_id]) for category_id in reorder_data.category_ids]
    return success_response(data=ordered_categories, message="工具分类排序更新成功")


@router.delete("/{category_id}", response_model=dict)
async def delete_tool_category(
    category_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员删除工具分类。"""
    result = await db.execute(select(ToolCategory).where(ToolCategory.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise NotFoundException("工具分类不存在")

    tool_count_result = await db.execute(
        select(func.count(Tool.id)).where(Tool.category_id == category_id)
    )
    if (tool_count_result.scalar() or 0) > 0:
        raise ConflictException("分类下仍有关联工具，无法删除")

    await db.delete(category)
    await db.commit()
    return success_response(message="工具分类删除成功")
