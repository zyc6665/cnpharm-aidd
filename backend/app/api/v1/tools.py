# backend/app/api/v1/tools.py
"""工具管理API"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List

from app.database.session import get_db
from app.models.users import User
from app.models.tools import Tool, ToolVersion, Tag, ToolFavorite, ToolStatus
from app.auth.dependencies import get_current_user, get_current_user_optional, get_admin_user
from app.schemas.tools import (
    ToolCreate, ToolUpdate, ToolResponse, ToolListResponse,
    ToolVersionCreate, ToolVersionResponse, TagCreate, TagResponse
)
from app.common.responses import success_response, error_response
from app.common.exceptions import NotFoundException, ForbiddenException, ConflictException

router = APIRouter()


@router.get("", response_model=dict)
async def list_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """获取工具列表"""
    query = select(Tool).options(
        selectinload(Tool.tags),
        selectinload(Tool.current_version)
    )

    # 默认只显示已发布的工具（管理员可以看到所有）
    is_admin = current_user and current_user.role.value == "admin"
    if not is_admin:
        query = query.where(Tool.status == ToolStatus.PUBLISHED)
    elif status:
        query = query.where(Tool.status == status)

    # 分类过滤
    if category:
        query = query.where(Tool.category == category)

    # 标签过滤
    if tag:
        query = query.where(Tool.tags.any(Tag.name == tag))

    # 搜索
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                Tool.name.ilike(search_pattern),
                Tool.description.ilike(search_pattern),
                Tool.slug.ilike(search_pattern)
            )
        )

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Tool.created_at.desc())

    result = await db.execute(query)
    tools = result.scalars().all()

    return success_response(
        data={
            "items": [ToolListResponse.model_validate(t).model_dump() for t in tools],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    )


@router.get("/categories", response_model=dict)
async def list_categories(
    db: AsyncSession = Depends(get_db)
):
    """获取所有工具分类"""
    result = await db.execute(
        select(Tool.category, func.count(Tool.id))
        .where(Tool.status == ToolStatus.PUBLISHED)
        .group_by(Tool.category)
    )
    categories = [{"name": cat, "count": count} for cat, count in result.all()]

    return success_response(data=categories)


@router.get("/tags", response_model=dict)
async def list_tags(
    db: AsyncSession = Depends(get_db)
):
    """获取所有标签"""
    result = await db.execute(select(Tag))
    tags = result.scalars().all()

    return success_response(
        data=[TagResponse.model_validate(t).model_dump() for t in tags]
    )


@router.get("/{tool_id}", response_model=dict)
async def get_tool(
    tool_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """获取工具详情"""
    result = await db.execute(
        select(Tool)
        .options(
            selectinload(Tool.tags),
            selectinload(Tool.current_version),
            selectinload(Tool.versions),
            selectinload(Tool.owner)
        )
        .where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    # 非管理员不能查看未发布的工具
    is_admin = current_user and current_user.role.value == "admin"
    is_owner = current_user and tool.owner_id == current_user.id
    if tool.status != ToolStatus.PUBLISHED and not is_admin and not is_owner:
        raise NotFoundException("工具不存在")

    # 增加查看次数
    tool.view_count += 1
    await db.commit()

    # 检查是否收藏
    is_favorited = False
    if current_user:
        fav_result = await db.execute(
            select(ToolFavorite).where(
                ToolFavorite.user_id == current_user.id,
                ToolFavorite.tool_id == tool_id
            )
        )
        is_favorited = fav_result.scalar_one_or_none() is not None

    tool_data = ToolResponse.model_validate(tool).model_dump()
    tool_data["is_favorited"] = is_favorited

    return success_response(data=tool_data)


@router.post("", response_model=dict)
async def create_tool(
    tool_data: ToolCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """创建工具（管理员）"""
    # 检查slug是否重复
    result = await db.execute(
        select(Tool).where(Tool.slug == tool_data.slug)
    )
    if result.scalar_one_or_none():
        raise ConflictException("工具标识已存在")

    # 处理标签
    tags = []
    if tool_data.tag_ids:
        result = await db.execute(
            select(Tag).where(Tag.id.in_(tool_data.tag_ids))
        )
        tags = list(result.scalars().all())

    # 创建工具
    tool = Tool(
        name=tool_data.name,
        slug=tool_data.slug,
        description=tool_data.description,
        category=tool_data.category,
        icon=tool_data.icon,
        owner_id=current_user.id,
        status=ToolStatus.DRAFT,
        tags=tags
    )

    db.add(tool)
    await db.commit()
    await db.refresh(tool)

    return success_response(
        data=ToolResponse.model_validate(tool).model_dump(),
        message="工具创建成功"
    )


@router.put("/{tool_id}", response_model=dict)
async def update_tool(
    tool_id: str,
    tool_data: ToolUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """更新工具（管理员）"""
    result = await db.execute(
        select(Tool).options(selectinload(Tool.tags)).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    update_data = tool_data.model_dump(exclude_unset=True)

    # 处理标签
    if "tag_ids" in update_data:
        tag_ids = update_data.pop("tag_ids")
        if tag_ids is not None:
            result = await db.execute(
                select(Tag).where(Tag.id.in_(tag_ids))
            )
            tool.tags = list(result.scalars().all())

    # 更新字段
    for field, value in update_data.items():
        setattr(tool, field, value)

    await db.commit()
    await db.refresh(tool)

    return success_response(
        data=ToolResponse.model_validate(tool).model_dump(),
        message="工具更新成功"
    )


@router.delete("/{tool_id}", response_model=dict)
async def delete_tool(
    tool_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """删除工具（管理员）"""
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    await db.delete(tool)
    await db.commit()

    return success_response(message="工具删除成功")


@router.post("/{tool_id}/publish", response_model=dict)
async def publish_tool(
    tool_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """发布工具（管理员）"""
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    if not tool.current_version_id:
        raise ForbiddenException("工具没有可用版本，无法发布")

    tool.status = ToolStatus.PUBLISHED
    await db.commit()

    return success_response(message="工具发布成功")


@router.post("/{tool_id}/favorite", response_model=dict)
async def favorite_tool(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """收藏工具"""
    # 检查工具是否存在
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    # 检查是否已收藏
    result = await db.execute(
        select(ToolFavorite).where(
            ToolFavorite.user_id == current_user.id,
            ToolFavorite.tool_id == tool_id
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise ConflictException("已收藏该工具")

    # 添加收藏
    favorite = ToolFavorite(user_id=current_user.id, tool_id=tool_id)
    tool.favorite_count += 1

    db.add(favorite)
    await db.commit()

    return success_response(message="收藏成功")


@router.delete("/{tool_id}/favorite", response_model=dict)
async def unfavorite_tool(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """取消收藏"""
    result = await db.execute(
        select(ToolFavorite).where(
            ToolFavorite.user_id == current_user.id,
            ToolFavorite.tool_id == tool_id
        )
    )
    favorite = result.scalar_one_or_none()

    if not favorite:
        raise NotFoundException("未收藏该工具")

    # 更新工具收藏数
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()
    if tool and tool.favorite_count > 0:
        tool.favorite_count -= 1

    await db.delete(favorite)
    await db.commit()

    return success_response(message="取消收藏成功")


# ==================== 版本管理 ====================

@router.get("/{tool_id}/versions", response_model=dict)
async def list_tool_versions(
    tool_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取工具版本列表"""
    result = await db.execute(
        select(ToolVersion)
        .where(ToolVersion.tool_id == tool_id)
        .order_by(ToolVersion.created_at.desc())
    )
    versions = result.scalars().all()

    return success_response(
        data=[ToolVersionResponse.model_validate(v).model_dump() for v in versions]
    )


@router.post("/{tool_id}/versions", response_model=dict)
async def create_tool_version(
    tool_id: str,
    version_data: ToolVersionCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """创建工具版本（管理员）"""
    # 检查工具是否存在
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    # 检查版本号是否重复
    result = await db.execute(
        select(ToolVersion).where(
            ToolVersion.tool_id == tool_id,
            ToolVersion.version == version_data.version
        )
    )
    if result.scalar_one_or_none():
        raise ConflictException("版本号已存在")

    # 创建版本
    version = ToolVersion(
        tool_id=tool_id,
        version=version_data.version,
        changelog=version_data.changelog,
        config=version_data.config,
        is_active=version_data.is_active
    )

    db.add(version)
    await db.flush()

    # 如果是激活状态，设置为当前版本
    if version_data.is_active:
        tool.current_version_id = version.id

    await db.commit()
    await db.refresh(version)

    return success_response(
        data=ToolVersionResponse.model_validate(version).model_dump(),
        message="版本创建成功"
    )


# ==================== 标签管理 ====================

@router.post("/tags", response_model=dict)
async def create_tag(
    tag_data: TagCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """创建标签（管理员）"""
    # 检查标签是否存在
    result = await db.execute(
        select(Tag).where(Tag.name == tag_data.name)
    )
    if result.scalar_one_or_none():
        raise ConflictException("标签已存在")

    tag = Tag(
        name=tag_data.name,
        color=tag_data.color,
        description=tag_data.description
    )

    db.add(tag)
    await db.commit()
    await db.refresh(tag)

    return success_response(
        data=TagResponse.model_validate(tag).model_dump(),
        message="标签创建成功"
    )
