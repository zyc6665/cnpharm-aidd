"""管理员工具管理路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.api.v1.tool_route_utils import (
    build_validated_tool_contract,
    commit_or_raise_conflict,
    create_or_update_tool_from_import,
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
from app.schemas.tools import TagCreate, TagResponse, ToolCreate, ToolImportRequest, ToolUpdate

router = APIRouter()


@router.post("/import-config", response_model=dict)
async def import_tool_config(
    import_data: ToolImportRequest,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await create_or_update_tool_from_import(db, current_user, import_data)
    return success_response(data=result, message="工具配置导入成功")


@router.post("", response_model=dict)
async def create_tool(
    tool_data: ToolCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Tool).where(Tool.slug == tool_data.slug))
    if existing.scalar_one_or_none():
        raise ConflictException("工具标识已存在")
    category = await require_active_tool_category(db, tool_data.category_id)
    tags = []
    if tool_data.tag_ids:
        tags = list(
            (
                await db.execute(select(Tag).where(Tag.id.in_(tool_data.tag_ids)))
            )
            .scalars()
            .all()
        )
    tool = Tool(
        name=tool_data.name,
        slug=tool_data.slug,
        description=tool_data.description,
        category_id=category.id,
        category=category.name,
        icon=tool_data.icon,
        icon_url=tool_data.icon_url,
        is_public=tool_data.is_public,
        gpu_required=tool_data.gpu_required,
        gpu_memory_mb=tool_data.gpu_memory_mb,
        timeout_sec=tool_data.timeout_sec,
        owner_id=current_user.id,
        status=ToolStatus.DRAFT.value,
        provider_type=ToolProviderType.PLATFORM.value,
        review_status=ToolReviewStatus.NOT_REQUIRED.value,
        tags=tags,
    )
    db.add(tool)
    await db.flush()
    if tool_data.initial_version:
        version = ToolVersion(
            tool_id=tool.id,
            version=tool_data.initial_version.version,
            changelog=tool_data.initial_version.changelog,
            notes=tool_data.initial_version.notes,
            config=tool_data.initial_version.config,
            is_active=True,
        )
        db.add(version)
        await db.flush()
        tool.current_version_id = version.id
    await db.commit()
    return success_response(
        data=serialize_tool(await load_tool_for_response(db, tool.id)),
        message="工具创建成功",
    )


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
