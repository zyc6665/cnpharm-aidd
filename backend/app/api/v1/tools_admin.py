"""管理员工具管理路由。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.api.v1.tool_route_utils import (
    build_validated_tool_contract,
    commit_or_raise_conflict,
    load_tool_for_response,
    load_tool_with_current_version,
    require_active_tool_category,
    serialize_tool,
)
from app.auth.dependencies import get_admin_user
from app.common.exceptions import ConflictException, NotFoundException, ValidationException
from app.common.responses import success_response
from app.database.session import get_db
from app.models.tools import Tag, Tool, ToolProviderType, ToolReviewStatus, ToolStatus, ToolVersion
from app.models.users import User
from app.schemas.tools import (
    TagCreate,
    TagResponse,
    ToolUpdate,
)

router = APIRouter()

LEGACY_TOOL_REGISTRATION_GONE_DETAIL = (
    "旧工具注册入口已下线，请使用管理员 Tool Package 注册流程"
)


@router.post("/import-config", response_model=dict)
async def import_tool_config(
    current_user: User = Depends(get_admin_user),
):
    raise HTTPException(status_code=410, detail=LEGACY_TOOL_REGISTRATION_GONE_DETAIL)


@router.post("/register-remote", response_model=dict)
async def register_remote_tool(
    current_user: User = Depends(get_admin_user),
):
    raise HTTPException(status_code=410, detail=LEGACY_TOOL_REGISTRATION_GONE_DETAIL)


@router.post("", response_model=dict)
async def create_tool(
    current_user: User = Depends(get_admin_user),
):
    raise HTTPException(status_code=410, detail=LEGACY_TOOL_REGISTRATION_GONE_DETAIL)


@router.put("/{tool_id}", response_model=dict)
async def update_tool(
    tool_id: str,
    tool_data: ToolUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    tool = (
        await db.execute(
            select(Tool)
            .options(
                selectinload(Tool.tags),
                selectinload(Tool.current_version),
                selectinload(Tool.tool_category),
                joinedload(Tool.statistics),
            )
            .where(Tool.id == tool_id)
        )
    ).scalar_one_or_none()
    if not tool:
        raise NotFoundException("工具不存在")
    update_data = tool_data.model_dump(exclude_unset=True)
    if "tag_ids" in update_data:
        tag_ids = update_data.pop("tag_ids")
        if tag_ids is not None:
            tool.tags = list(
                (
                    await db.execute(select(Tag).where(Tag.id.in_(tag_ids)))
                )
                .scalars()
                .all()
            )
    if "category_id" in update_data:
        category = await require_active_tool_category(db, update_data.pop("category_id"))
        tool.category_id = category.id
        tool.category = category.name
    update_data.pop("category", None)
    if "slug" in update_data and update_data["slug"] != tool.slug:
        duplicate = await db.execute(
            select(Tool.id).where(Tool.slug == update_data["slug"], Tool.id != tool.id)
        )
        if duplicate.scalar_one_or_none():
            raise ConflictException("工具标识已存在")
    for field, value in update_data.items():
        setattr(tool, field, value)
    await commit_or_raise_conflict(db, "工具标识已存在")
    return success_response(
        data=serialize_tool(await load_tool_for_response(db, tool.id)),
        message="工具更新成功",
    )


@router.delete("/{tool_id}", response_model=dict)
async def delete_tool(
    tool_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    tool = (
        await db.execute(select(Tool).where(Tool.id == tool_id))
    ).scalar_one_or_none()
    if not tool:
        raise NotFoundException("工具不存在")
    await db.delete(tool)
    await db.commit()
    return success_response(message="工具删除成功")


@router.post("/{tool_id}/publish", response_model=dict)
async def publish_tool(
    tool_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    tool = await load_tool_with_current_version(db, tool_id)
    errors = build_validated_tool_contract(tool)["validation"]["errors"]
    if errors:
        raise ValidationException("；".join(str(error) for error in errors))
    tool.status = ToolStatus.PUBLISHED.value
    await db.commit()
    return success_response(message="工具发布成功")


@router.post("/tags", response_model=dict)
async def create_tag(
    tag_data: TagCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Tag).where(Tag.name == tag_data.name))
    if existing.scalar_one_or_none():
        raise ConflictException("标签已存在")
    tag = Tag(
        name=tag_data.name,
        color=tag_data.color,
        description=tag_data.description,
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return success_response(
        data=TagResponse.model_validate(tag).model_dump(),
        message="标签创建成功",
    )
