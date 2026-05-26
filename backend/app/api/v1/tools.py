# backend/app/api/v1/tools.py
"""工具管理API"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List, Literal

from app.database.session import get_db
from app.models.users import User
from app.models.tools import (
    Tool, ToolCategory, ToolVersion, Tag, ToolFavorite, ToolStatus,
    ToolProviderType, ToolReviewStatus
)
from app.auth.dependencies import get_current_user, get_current_user_optional, get_admin_user
from app.schemas.tools import (
    ToolCreate, ToolUpdate, ToolResponse, ToolListResponse,
    ToolVersionCreate, ToolVersionResponse, TagCreate, TagResponse,
    ToolCategoryCreate, ToolCategoryUpdate, ToolCategoryResponse,
    ToolCategoryStatusUpdate, ToolCategoryReorderRequest
)
from app.common.responses import success_response, error_response
from app.common.exceptions import NotFoundException, ForbiddenException, ConflictException, ValidationException

router = APIRouter()
admin_category_router = APIRouter(prefix="/admin/tool-categories", tags=["工具分类管理"])


def serialize_tool(tool: Tool, schema_class=ToolResponse) -> dict:
    """统一序列化工具响应。"""
    tool_data = schema_class.model_validate(tool).model_dump()
    tool_data["category_id"] = tool.category_id
    tool_data["category"] = tool.tool_category.name if tool.tool_category else tool.category
    return tool_data


def serialize_category(category: ToolCategory, tool_count: Optional[int] = None) -> dict:
    """统一序列化分类响应。"""
    category_data = ToolCategoryResponse.model_validate(category).model_dump()
    if tool_count is not None:
        category_data["tool_count"] = tool_count
        category_data["count"] = tool_count
    return category_data


async def require_active_tool_category(db: AsyncSession, category_id: str) -> ToolCategory:
    """校验工具分类存在且已启用。"""
    if not category_id:
        raise ValidationException("工具分类不能为空")

    result = await db.execute(
        select(ToolCategory).where(
            ToolCategory.id == category_id,
            ToolCategory.is_enabled.is_(True)
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise ValidationException("工具分类不存在或已停用")
    return category


async def load_tool_for_response(db: AsyncSession, tool_id: str) -> Tool:
    """加载用于响应的完整工具对象。"""
    result = await db.execute(
        select(Tool)
        .options(
            selectinload(Tool.tags),
            selectinload(Tool.current_version),
            selectinload(Tool.tool_category),
            joinedload(Tool.statistics)
        )
        .where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise NotFoundException("工具不存在")
    return tool


# ==================== 工具列表接口 ====================

@router.get("", response_model=dict)
async def list_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    view: Optional[Literal["public", "favorites"]] = Query(None, description="视图类型"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    获取工具列表

    - **view=public**: 公开工具（默认）
    - **view=favorites**: 收藏的工具（需要登录）
    """
    query = select(Tool).options(
        selectinload(Tool.tags),
        selectinload(Tool.current_version),
        selectinload(Tool.tool_category),
        joinedload(Tool.statistics)
    )

    is_admin = current_user and current_user.role == "admin"

    # 根据视图类型过滤
    if view == "favorites":
        if not current_user:
            raise ForbiddenException("请先登录")
        # 通过收藏表关联
        query = query.join(ToolFavorite, ToolFavorite.tool_id == Tool.id).where(
            ToolFavorite.user_id == current_user.id
        )
    else:
        # 公开视图：只显示已发布工具
        if not is_admin:
            query = query.where(Tool.status == ToolStatus.PUBLISHED.value)
        elif status:
            query = query.where(Tool.status == status)

    # 分类过滤
    if category:
        query = query.where(
            or_(
                Tool.category == category,
                Tool.category_id == category,
                Tool.tool_category.has(ToolCategory.name == category),
                Tool.tool_category.has(ToolCategory.slug == category)
            )
        )

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

    items = [serialize_tool(t, ToolListResponse) for t in tools]

    return success_response(
        data={
            "items": items,
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
        select(ToolCategory, func.count(Tool.id).label("tool_count"))
        .outerjoin(
            Tool,
            and_(
                Tool.category_id == ToolCategory.id,
                Tool.status == ToolStatus.PUBLISHED.value
            )
        )
        .where(ToolCategory.is_enabled.is_(True))
        .group_by(ToolCategory.id)
        .order_by(ToolCategory.sort_order.asc(), ToolCategory.created_at.asc())
    )
    categories = [
        serialize_category(category, tool_count)
        for category, tool_count in result.all()
    ]

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
            selectinload(Tool.owner),
            selectinload(Tool.tool_category),
            selectinload(Tool.statistics)
        )
        .where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    # 权限检查
    is_admin = current_user and current_user.role == "admin"
    is_owner = current_user and tool.owner_id == current_user.id

    # 非管理员不能查看未发布工具
    if not is_admin and not is_owner:
        if tool.status != ToolStatus.PUBLISHED.value:
            raise NotFoundException("工具不存在")

    # 增加查看次数
    if tool.statistics:
        tool.statistics.view_count += 1
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

    tool_data = serialize_tool(tool)
    tool_data["is_favorited"] = is_favorited

    return success_response(data=tool_data)


# ==================== 工具创建/更新/删除 ====================

@router.post("", response_model=dict)
async def create_tool(
    tool_data: ToolCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    创建工具

    - 仅管理员可创建工具
    """
    # 检查slug是否重复
    result = await db.execute(
        select(Tool).where(Tool.slug == tool_data.slug)
    )
    if result.scalar_one_or_none():
        raise ConflictException("工具标识已存在")

    category = await require_active_tool_category(db, tool_data.category_id)

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
        tags=tags
    )

    db.add(tool)
    await db.flush()  # 获取 tool.id

    # 处理初始版本
    if tool_data.initial_version:
        version = ToolVersion(
            tool_id=tool.id,
            version=tool_data.initial_version.version,
            changelog=tool_data.initial_version.changelog,
            notes=tool_data.initial_version.notes,
            config=tool_data.initial_version.config,
            is_active=True
        )
        db.add(version)
        await db.flush()

        # 设置为当前版本
        tool.current_version_id = version.id

    await db.commit()
    tool_response = await load_tool_for_response(db, tool.id)

    return success_response(data=serialize_tool(tool_response), message="工具创建成功")


@router.put("/{tool_id}", response_model=dict)
async def update_tool(
    tool_id: str,
    tool_data: ToolUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新工具

    - 仅管理员可编辑工具
    """
    result = await db.execute(
        select(Tool).options(
            selectinload(Tool.tags),
            selectinload(Tool.current_version),
            selectinload(Tool.tool_category),
            joinedload(Tool.statistics)
        ).where(Tool.id == tool_id)
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

    if "category_id" in update_data:
        category_id = update_data.pop("category_id")
        category = await require_active_tool_category(db, category_id)
        tool.category_id = category.id
        tool.category = category.name

    update_data.pop("category", None)

    # 更新字段
    for field, value in update_data.items():
        setattr(tool, field, value)

    await db.commit()
    tool_response = await load_tool_for_response(db, tool.id)

    return success_response(data=serialize_tool(tool_response), message="工具更新成功")


@router.delete("/{tool_id}", response_model=dict)
async def delete_tool(
    tool_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    删除工具

    - 仅管理员可删除工具
    """
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    await db.delete(tool)
    await db.commit()

    return success_response(message="工具删除成功")


# ==================== 工具发布与审核 ====================

@router.post("/{tool_id}/publish", response_model=dict)
async def publish_tool(
    tool_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    发布工具

    - 仅管理员可发布工具
    - 工具需要有可用版本才能发布
    """
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    if not tool.current_version_id:
        raise ForbiddenException("工具没有可用版本，无法发布")

    tool.status = ToolStatus.PUBLISHED.value
    await db.commit()

    return success_response(message="工具发布成功")


# ==================== 收藏功能 ====================

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
    """
    创建工具版本

    - 仅管理员可创建版本
    """
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
        notes=version_data.notes,
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


@admin_category_router.get("", response_model=dict)
async def admin_list_tool_categories(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员获取全部工具分类。"""
    result = await db.execute(
        select(ToolCategory, func.count(Tool.id).label("tool_count"))
        .outerjoin(Tool, Tool.category_id == ToolCategory.id)
        .group_by(ToolCategory.id)
        .order_by(ToolCategory.sort_order.asc(), ToolCategory.created_at.asc())
    )
    categories = [serialize_category(category, tool_count) for category, tool_count in result.all()]
    return success_response(data=categories)


@admin_category_router.post("", response_model=dict)
async def admin_create_tool_category(
    category_data: ToolCategoryCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
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
    return success_response(data=serialize_category(category), message="工具分类创建成功")


@admin_category_router.put("/{category_id}", response_model=dict)
async def admin_update_tool_category(
    category_id: str,
    category_data: ToolCategoryUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
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
                or_(*conflict_conditions)
            )
        )
        if conflict_result.scalar_one_or_none():
            raise ConflictException("工具分类名称或标识已存在")

    for field, value in update_data.items():
        setattr(category, field, value)

    await db.commit()
    await db.refresh(category)
    return success_response(data=serialize_category(category), message="工具分类更新成功")


@admin_category_router.patch("/{category_id}/status", response_model=dict)
async def admin_update_tool_category_status(
    category_id: str,
    status_data: ToolCategoryStatusUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员更新工具分类启用状态。"""
    result = await db.execute(select(ToolCategory).where(ToolCategory.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise NotFoundException("工具分类不存在")

    category.is_enabled = status_data.is_enabled
    await db.commit()
    await db.refresh(category)
    return success_response(data=serialize_category(category), message="工具分类状态更新成功")


@admin_category_router.post("/reorder", response_model=dict)
async def admin_reorder_tool_categories(
    reorder_data: ToolCategoryReorderRequest,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
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
    ordered_categories = [serialize_category(categories[category_id]) for category_id in reorder_data.category_ids]
    return success_response(data=ordered_categories, message="工具分类排序更新成功")


@admin_category_router.delete("/{category_id}", response_model=dict)
async def admin_delete_tool_category(
    category_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
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
