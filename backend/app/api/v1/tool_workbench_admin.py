"""工具工作台分组与映射的管理 API。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.dependencies import get_admin_user
from app.common.exceptions import ConflictException, NotFoundException, ValidationException
from app.common.responses import success_response
from app.database.session import get_db
from app.models.tools import Tool, ToolWorkbenchGroup, ToolWorkbenchGroupMapping
from app.models.users import User
from app.schemas.tools import (
    ToolWorkbenchGroupCreate,
    ToolWorkbenchGroupMappingCreate,
    ToolWorkbenchGroupMappingResponse,
    ToolWorkbenchGroupMappingUpdate,
    ToolWorkbenchGroupReorderRequest,
    ToolWorkbenchGroupResponse,
    ToolWorkbenchGroupUpdate,
)


group_router = APIRouter(prefix="/admin/workbench-groups", tags=["工具工作台分组管理"])
mapping_router = APIRouter(
    prefix="/admin/workbench-group-mappings",
    tags=["工具工作台分组映射管理"],
)


def _serialize_group(group: ToolWorkbenchGroup) -> dict:
    return ToolWorkbenchGroupResponse.model_validate(group).model_dump()


def _serialize_mapping(mapping: ToolWorkbenchGroupMapping) -> dict:
    return ToolWorkbenchGroupMappingResponse(
        id=mapping.id,
        tool_id=mapping.tool_id,
        group_id=mapping.group_id,
        tool_name=mapping.tool.name,
        tool_slug=mapping.tool.slug,
        group_name=mapping.group.name,
        sort_order=mapping.sort_order,
        is_recommended=mapping.is_recommended,
        is_enabled=mapping.is_enabled,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    ).model_dump()


async def _load_mapping_with_labels(
    db: AsyncSession,
    mapping_id: str,
) -> ToolWorkbenchGroupMapping:
    result = await db.execute(
        select(ToolWorkbenchGroupMapping)
        .options(
            joinedload(ToolWorkbenchGroupMapping.tool),
            joinedload(ToolWorkbenchGroupMapping.group),
        )
        .where(ToolWorkbenchGroupMapping.id == mapping_id)
    )
    return result.scalar_one()


async def _commit_or_raise_conflict(db: AsyncSession, message: str) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(message) from exc


async def _list_groups_in_order(db: AsyncSession) -> list[ToolWorkbenchGroup]:
    result = await db.execute(
        select(ToolWorkbenchGroup).order_by(
            ToolWorkbenchGroup.sort_order.asc(),
            ToolWorkbenchGroup.created_at.asc(),
        )
    )
    return list(result.scalars().all())


def _resequence_groups(groups: list[ToolWorkbenchGroup]) -> None:
    for index, group in enumerate(groups):
        group.sort_order = index


async def _move_group_to_position(
    db: AsyncSession,
    group: ToolWorkbenchGroup,
    target_position: int,
) -> None:
    groups = await _list_groups_in_order(db)
    ordered_groups = [item for item in groups if item.id != group.id]
    if target_position > len(ordered_groups):
        raise ValidationException("工作台分组排序值超出范围")
    ordered_groups.insert(target_position, group)
    _resequence_groups(ordered_groups)


async def _list_mappings_in_order(
    db: AsyncSession,
    group_id: str,
    exclude_mapping_id: Optional[str] = None,
) -> list[ToolWorkbenchGroupMapping]:
    query = (
        select(ToolWorkbenchGroupMapping)
        .where(ToolWorkbenchGroupMapping.group_id == group_id)
        .order_by(
            ToolWorkbenchGroupMapping.sort_order.asc(),
            ToolWorkbenchGroupMapping.created_at.asc(),
        )
    )
    if exclude_mapping_id:
        query = query.where(ToolWorkbenchGroupMapping.id != exclude_mapping_id)
    result = await db.execute(query)
    return list(result.scalars().all())


def _resequence_mappings(mappings: list[ToolWorkbenchGroupMapping]) -> None:
    for index, mapping in enumerate(mappings):
        mapping.sort_order = index


async def _move_mapping_between_groups(
    db: AsyncSession,
    mapping: ToolWorkbenchGroupMapping,
    target_group_id: str,
    target_position: int,
) -> None:
    source_group_id = mapping.group_id
    if source_group_id == target_group_id:
        ordered = await _list_mappings_in_order(db, source_group_id, exclude_mapping_id=mapping.id)
        if target_position > len(ordered):
            raise ValidationException("工作台分组映射排序值超出范围")
        ordered.insert(target_position, mapping)
        _resequence_mappings(ordered)
        return

    source = await _list_mappings_in_order(db, source_group_id, exclude_mapping_id=mapping.id)
    target = await _list_mappings_in_order(db, target_group_id)
    if target_position > len(target):
        raise ValidationException("工作台分组映射排序值超出范围")

    mapping.group_id = target_group_id
    target.insert(target_position, mapping)
    _resequence_mappings(source)
    _resequence_mappings(target)


@group_router.get("", response_model=dict)
async def list_workbench_groups(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=[_serialize_group(group) for group in await _list_groups_in_order(db)])


@group_router.post("", response_model=dict)
async def create_workbench_group(
    group_data: ToolWorkbenchGroupCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(ToolWorkbenchGroup).where(
            or_(ToolWorkbenchGroup.name == group_data.name, ToolWorkbenchGroup.slug == group_data.slug)
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException("工作台分组名称或标识已存在")

    sort_order = group_data.sort_order
    if "sort_order" not in group_data.model_fields_set:
        maximum = await db.execute(select(func.max(ToolWorkbenchGroup.sort_order)))
        sort_order = (maximum.scalar() or 0) + 1

    group = ToolWorkbenchGroup(
        name=group_data.name,
        slug=group_data.slug,
        description=group_data.description,
        sort_order=sort_order,
        is_enabled=group_data.is_enabled,
    )
    db.add(group)
    await _commit_or_raise_conflict(db, "工作台分组名称或标识已存在")
    await db.refresh(group)
    return success_response(data=_serialize_group(group), message="工作台分组创建成功")


@group_router.post("/reorder", response_model=dict)
async def reorder_workbench_groups(
    reorder_data: ToolWorkbenchGroupReorderRequest,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    groups = await _list_groups_in_order(db)
    group_ids = [group.id for group in groups]
    if (
        len(reorder_data.group_ids) != len(group_ids)
        or len(set(reorder_data.group_ids)) != len(reorder_data.group_ids)
        or set(reorder_data.group_ids) != set(group_ids)
    ):
        raise ValidationException("工作台分组重排必须包含全部且唯一的分组ID")

    groups_by_id = {group.id: group for group in groups}
    _resequence_groups([groups_by_id[group_id] for group_id in reorder_data.group_ids])
    await db.commit()
    return success_response(
        data=[_serialize_group(groups_by_id[group_id]) for group_id in reorder_data.group_ids],
        message="工作台分组排序更新成功",
    )


@group_router.put("/{group_id}", response_model=dict)
async def update_workbench_group(
    group_id: str,
    group_data: ToolWorkbenchGroupUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(ToolWorkbenchGroup, group_id)
    if not group:
        raise NotFoundException("工作台分组不存在")

    update_data = group_data.model_dump(exclude_unset=True)
    sort_order = update_data.pop("sort_order", None)
    if "name" in update_data or "slug" in update_data:
        conditions = []
        if "name" in update_data:
            conditions.append(ToolWorkbenchGroup.name == update_data["name"])
        if "slug" in update_data:
            conditions.append(ToolWorkbenchGroup.slug == update_data["slug"])
        conflicts = await db.execute(
            select(ToolWorkbenchGroup).where(ToolWorkbenchGroup.id != group_id, or_(*conditions))
        )
        if conflicts.scalar_one_or_none():
            raise ConflictException("工作台分组名称或标识已存在")

    for field, value in update_data.items():
        setattr(group, field, value)
    if sort_order is not None and sort_order != group.sort_order:
        await _move_group_to_position(db, group, sort_order)

    await _commit_or_raise_conflict(db, "工作台分组名称或标识已存在")
    await db.refresh(group)
    return success_response(data=_serialize_group(group), message="工作台分组更新成功")


@group_router.delete("/{group_id}", response_model=dict)
async def delete_workbench_group(
    group_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(ToolWorkbenchGroup, group_id)
    if not group:
        raise NotFoundException("工作台分组不存在")
    count = await db.execute(
        select(func.count(ToolWorkbenchGroupMapping.id)).where(
            ToolWorkbenchGroupMapping.group_id == group_id
        )
    )
    if (count.scalar() or 0) > 0:
        raise ConflictException("工作台分组下仍有关联工具，无法删除")

    await db.delete(group)
    await db.flush()
    _resequence_groups(await _list_groups_in_order(db))
    await db.commit()
    return success_response(message="工作台分组删除成功")


@mapping_router.get("", response_model=dict)
async def list_workbench_group_mappings(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ToolWorkbenchGroupMapping)
        .options(
            joinedload(ToolWorkbenchGroupMapping.tool),
            joinedload(ToolWorkbenchGroupMapping.group),
        )
        .join(ToolWorkbenchGroup, ToolWorkbenchGroup.id == ToolWorkbenchGroupMapping.group_id)
        .order_by(
            ToolWorkbenchGroup.sort_order.asc(),
            ToolWorkbenchGroupMapping.sort_order.asc(),
            ToolWorkbenchGroupMapping.created_at.asc(),
        )
    )
    return success_response(data=[_serialize_mapping(mapping) for mapping in result.scalars().all()])


@mapping_router.post("", response_model=dict)
async def create_workbench_group_mapping(
    mapping_data: ToolWorkbenchGroupMappingCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Tool, mapping_data.tool_id):
        raise ValidationException("工具不存在")
    if not await db.get(ToolWorkbenchGroup, mapping_data.group_id):
        raise ValidationException("工作台分组不存在")

    existing = await db.execute(
        select(ToolWorkbenchGroupMapping).where(
            ToolWorkbenchGroupMapping.tool_id == mapping_data.tool_id,
            ToolWorkbenchGroupMapping.group_id == mapping_data.group_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException("工具与工作台分组映射已存在")

    mapping = ToolWorkbenchGroupMapping(**mapping_data.model_dump())
    db.add(mapping)
    await _commit_or_raise_conflict(db, "工具与工作台分组映射已存在")
    mapping = await _load_mapping_with_labels(db, mapping.id)
    return success_response(data=_serialize_mapping(mapping), message="工作台分组映射创建成功")


@mapping_router.put("/{mapping_id}", response_model=dict)
async def update_workbench_group_mapping(
    mapping_id: str,
    mapping_data: ToolWorkbenchGroupMappingUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    mapping = await db.get(ToolWorkbenchGroupMapping, mapping_id)
    if not mapping:
        raise NotFoundException("工作台分组映射不存在")

    update_data = mapping_data.model_dump(exclude_unset=True)
    requested_sort_order = update_data.pop("sort_order", None)
    new_tool_id = update_data.get("tool_id", mapping.tool_id)
    new_group_id = update_data.get("group_id", mapping.group_id)
    if "tool_id" in update_data and not await db.get(Tool, new_tool_id):
        raise ValidationException("工具不存在")
    if "group_id" in update_data and not await db.get(ToolWorkbenchGroup, new_group_id):
        raise ValidationException("工作台分组不存在")

    if new_tool_id != mapping.tool_id or new_group_id != mapping.group_id:
        conflict = await db.execute(
            select(ToolWorkbenchGroupMapping).where(
                ToolWorkbenchGroupMapping.id != mapping_id,
                ToolWorkbenchGroupMapping.tool_id == new_tool_id,
                ToolWorkbenchGroupMapping.group_id == new_group_id,
            )
        )
        if conflict.scalar_one_or_none():
            raise ConflictException("工具与工作台分组映射已存在")

    if requested_sort_order is not None:
        if new_group_id != mapping.group_id or requested_sort_order != mapping.sort_order:
            await _move_mapping_between_groups(db, mapping, new_group_id, requested_sort_order)
        update_data["group_id"] = mapping.group_id
        update_data["sort_order"] = mapping.sort_order
    elif new_group_id != mapping.group_id:
        target = await _list_mappings_in_order(db, new_group_id)
        await _move_mapping_between_groups(db, mapping, new_group_id, len(target))
        update_data["group_id"] = mapping.group_id
        update_data["sort_order"] = mapping.sort_order

    for field, value in update_data.items():
        setattr(mapping, field, value)
    await _commit_or_raise_conflict(db, "工具与工作台分组映射已存在")
    mapping = await _load_mapping_with_labels(db, mapping.id)
    return success_response(data=_serialize_mapping(mapping), message="工作台分组映射更新成功")


@mapping_router.delete("/{mapping_id}", response_model=dict)
async def delete_workbench_group_mapping(
    mapping_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    mapping = await db.get(ToolWorkbenchGroupMapping, mapping_id)
    if not mapping:
        raise NotFoundException("工作台分组映射不存在")

    group_id = mapping.group_id
    await db.delete(mapping)
    await db.flush()
    _resequence_mappings(await _list_mappings_in_order(db, group_id, exclude_mapping_id=mapping_id))
    await db.commit()
    return success_response(message="工作台分组映射删除成功")
