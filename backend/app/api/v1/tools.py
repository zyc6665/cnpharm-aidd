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
    Tool, ToolVersion, Tag, ToolFavorite, ToolStatus,
    ToolProviderType, ToolReviewStatus
)
from app.auth.dependencies import get_current_user, get_current_user_optional, get_admin_user
from app.schemas.tools import (
    ToolCreate, ToolUpdate, ToolResponse, ToolListResponse,
    ToolVersionCreate, ToolVersionResponse, TagCreate, TagResponse,
    ToolReviewRequest, ToolReviewResponse, SetPlatformToolRequest
)
from app.common.responses import success_response, error_response
from app.common.exceptions import NotFoundException, ForbiddenException, ConflictException, ValidationException

router = APIRouter()


def add_provider_label(tool_data: dict) -> dict:
    """添加工具提供者标签"""
    provider_type = tool_data.get("provider_type", "user")
    tool_data["provider_label"] = "官方" if provider_type == "platform" else "社区"
    return tool_data


# ==================== 工具列表接口 ====================

@router.get("", response_model=dict)
async def list_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    provider_type: Optional[str] = Query(None, description="工具来源：platform/user"),
    view: Optional[Literal["public", "my", "favorites"]] = Query(None, description="视图类型"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    获取工具列表

    - **view=public**: 公开工具（默认）
    - **view=my**: 我的工具（需要登录）
    - **view=favorites**: 收藏的工具（需要登录）
    - **provider_type**: 筛选工具来源（platform=官方, user=社区）
    """
    query = select(Tool).options(
        selectinload(Tool.tags),
        selectinload(Tool.current_version),
        joinedload(Tool.statistics)
    )

    is_admin = current_user and current_user.role == "admin"

    # 根据视图类型过滤
    if view == "my":
        if not current_user:
            raise ForbiddenException("请先登录")
        query = query.where(Tool.owner_id == current_user.id)
    elif view == "favorites":
        if not current_user:
            raise ForbiddenException("请先登录")
        # 通过收藏表关联
        query = query.join(ToolFavorite, ToolFavorite.tool_id == Tool.id).where(
            ToolFavorite.user_id == current_user.id
        )
    else:
        # 公开视图：只显示已发布且（官方工具或已审核通过的用户工具）
        if not is_admin:
            query = query.where(
                Tool.status == ToolStatus.PUBLISHED.value,
                or_(
                    Tool.provider_type == ToolProviderType.PLATFORM.value,
                    and_(
                        Tool.provider_type == ToolProviderType.USER.value,
                        Tool.review_status == ToolReviewStatus.APPROVED.value
                    )
                )
            )
        elif status:
            query = query.where(Tool.status == status)

    # 工具来源过滤
    if provider_type:
        query = query.where(Tool.provider_type == provider_type)

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

    # 添加 provider_label
    items = [add_provider_label(ToolListResponse.model_validate(t).model_dump()) for t in tools]

    return success_response(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    )


@router.get("/my", response_model=dict)
async def list_my_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    review_status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取我的工具列表

    - **status**: 筛选工具状态（draft/published/disabled）
    - **review_status**: 筛选审核状态（pending/approved/rejected）
    """
    query = select(Tool).options(
        selectinload(Tool.tags),
        selectinload(Tool.current_version),
        joinedload(Tool.statistics)
    ).where(Tool.owner_id == current_user.id)

    if status:
        query = query.where(Tool.status == status)

    if review_status:
        query = query.where(Tool.review_status == review_status)

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Tool.created_at.desc())

    result = await db.execute(query)
    tools = result.scalars().all()

    items = [add_provider_label(ToolListResponse.model_validate(t).model_dump()) for t in tools]

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
        select(Tool.category, func.count(Tool.id))
        .where(Tool.status == ToolStatus.PUBLISHED.value)
        .where(Tool.category.isnot(None))
        .group_by(Tool.category)
    )
    categories = [{"name": cat, "count": count} for cat, count in result.all() if cat]

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

    # 非管理员、非所有者不能查看未发布或未审核的工具
    if not is_admin and not is_owner:
        if tool.status != ToolStatus.PUBLISHED.value:
            raise NotFoundException("工具不存在")
        if tool.provider_type == ToolProviderType.USER.value and tool.review_status != ToolReviewStatus.APPROVED.value:
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

    tool_data = add_provider_label(ToolResponse.model_validate(tool).model_dump())
    tool_data["is_favorited"] = is_favorited

    return success_response(data=tool_data)


# ==================== 工具创建/更新/删除 ====================

@router.post("", response_model=dict)
async def create_tool(
    tool_data: ToolCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    创建工具

    - 注册用户可创建工具（默认为用户工具，需审核）
    - 管理员可创建平台官方工具（无需审核）
    """
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

    # 确定工具提供者类型和审核状态
    is_admin = current_user.role == "admin"

    if tool_data.provider_type == "platform":
        if not is_admin:
            raise ForbiddenException("只有管理员可以创建平台官方工具")
        provider_type = ToolProviderType.PLATFORM.value
        review_status = ToolReviewStatus.NOT_REQUIRED.value
    else:
        provider_type = ToolProviderType.USER.value
        review_status = ToolReviewStatus.PENDING.value

    # 创建工具
    tool = Tool(
        name=tool_data.name,
        slug=tool_data.slug,
        description=tool_data.description,
        category=tool_data.category,
        icon=tool_data.icon,
        icon_url=tool_data.icon_url,
        is_public=tool_data.is_public,
        gpu_required=tool_data.gpu_required,
        gpu_memory_mb=tool_data.gpu_memory_mb,
        timeout_sec=tool_data.timeout_sec,
        owner_id=current_user.id,
        status=ToolStatus.DRAFT.value,
        provider_type=provider_type,
        review_status=review_status,
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
    await db.refresh(tool)

    return success_response(
        data=add_provider_label(ToolResponse.model_validate(tool).model_dump()),
        message="工具创建成功"
    )


@router.put("/{tool_id}", response_model=dict)
async def update_tool(
    tool_id: str,
    tool_data: ToolUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新工具

    - 工具所有者可编辑自己的工具
    - 管理员可编辑所有工具
    """
    result = await db.execute(
        select(Tool).options(
            selectinload(Tool.tags),
            joinedload(Tool.statistics)
        ).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    # 权限检查
    is_admin = current_user.role == "admin"
    is_owner = tool.owner_id == current_user.id
    if not is_admin and not is_owner:
        raise ForbiddenException("无权编辑此工具")

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
        data=add_provider_label(ToolResponse.model_validate(tool).model_dump()),
        message="工具更新成功"
    )


@router.delete("/{tool_id}", response_model=dict)
async def delete_tool(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    删除工具

    - 工具所有者可删除自己的草稿或被拒绝的工具
    - 管理员可删除任何工具
    """
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    is_admin = current_user.role == "admin"
    is_owner = tool.owner_id == current_user.id

    if not is_admin:
        if not is_owner:
            raise ForbiddenException("无权删除此工具")
        # 普通用户只能删除草稿或被拒绝的工具
        if tool.status not in [ToolStatus.DRAFT.value] and tool.review_status not in [ToolReviewStatus.REJECTED.value]:
            raise ForbiddenException("只能删除草稿或被拒绝的工具")

    await db.delete(tool)
    await db.commit()

    return success_response(message="工具删除成功")


# ==================== 工具发布与审核 ====================

@router.post("/{tool_id}/publish", response_model=dict)
async def publish_tool(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    发布工具

    - 工具所有者或管理员可发布工具
    - 工具需要有可用版本才能发布
    """
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    is_admin = current_user.role == "admin"
    is_owner = tool.owner_id == current_user.id
    if not is_admin and not is_owner:
        raise ForbiddenException("无权发布此工具")

    if not tool.current_version_id:
        raise ForbiddenException("工具没有可用版本，无法发布")

    tool.status = ToolStatus.PUBLISHED.value
    await db.commit()

    return success_response(message="工具发布成功")


@router.post("/{tool_id}/submit-review", response_model=dict)
async def submit_tool_review(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    提交工具审核

    - 仅工具所有者可提交审核
    - 工具需要有可用版本
    - 审核状态必须为 pending 或 rejected
    """
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    if tool.owner_id != current_user.id:
        raise ForbiddenException("只有工具所有者可以提交审核")

    if tool.provider_type == ToolProviderType.PLATFORM.value:
        raise ValidationException("平台官方工具无需审核")

    if tool.review_status not in [ToolReviewStatus.PENDING.value, ToolReviewStatus.REJECTED.value]:
        raise ValidationException("当前状态不允许提交审核")

    if not tool.current_version_id:
        raise ValidationException("工具没有可用版本，无法提交审核")

    # 更新审核状态
    tool.review_status = ToolReviewStatus.PENDING.value
    tool.reject_reason = None
    await db.commit()

    return success_response(
        data={
            "id": tool.id,
            "review_status": tool.review_status
        },
        message="审核申请已提交"
    )


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    创建工具版本

    - 工具所有者或管理员可创建版本
    """
    # 检查工具是否存在
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    is_admin = current_user.role == "admin"
    is_owner = tool.owner_id == current_user.id
    if not is_admin and not is_owner:
        raise ForbiddenException("无权创建版本")

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


# ==================== 管理员接口 ====================

@router.post("/admin/{tool_id}/review", response_model=dict)
async def admin_review_tool(
    tool_id: str,
    review_data: ToolReviewRequest,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    审核工具（管理员）

    - **action**: approve（通过）或 reject（拒绝）
    - **reject_reason**: 拒绝时必填
    """
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    if tool.provider_type == ToolProviderType.PLATFORM.value:
        raise ValidationException("平台官方工具无需审核")

    if tool.review_status != ToolReviewStatus.PENDING.value:
        raise ValidationException("该工具不在待审核状态")

    if review_data.action == "approve":
        tool.review_status = ToolReviewStatus.APPROVED.value
        tool.reject_reason = None
    else:
        if not review_data.reject_reason:
            raise ValidationException("拒绝时必须填写拒绝原因")
        tool.review_status = ToolReviewStatus.REJECTED.value
        tool.reject_reason = review_data.reject_reason

    tool.reviewed_at = datetime.utcnow()
    tool.reviewed_by = current_user.id

    await db.commit()

    return success_response(
        data=ToolReviewResponse(
            id=tool.id,
            review_status=tool.review_status,
            reviewed_at=tool.reviewed_at,
            reject_reason=tool.reject_reason
        ).model_dump(),
        message="审核完成"
    )


@router.post("/admin/{tool_id}/set-platform", response_model=dict)
async def admin_set_platform_tool(
    tool_id: str,
    data: SetPlatformToolRequest,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    设置为平台官方工具（管理员）

    - **is_platform**: true=设为官方, false=取消官方
    """
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    if data.is_platform:
        tool.provider_type = ToolProviderType.PLATFORM.value
        tool.review_status = ToolReviewStatus.NOT_REQUIRED.value
        tool.reject_reason = None
    else:
        tool.provider_type = ToolProviderType.USER.value
        # 取消官方后，如果之前是审核通过的，保持通过状态
        if tool.review_status == ToolReviewStatus.NOT_REQUIRED.value:
            tool.review_status = ToolReviewStatus.APPROVED.value

    await db.commit()

    return success_response(
        data={
            "id": tool.id,
            "provider_type": tool.provider_type,
            "review_status": tool.review_status
        },
        message="设置成功"
    )


@router.get("/admin/pending-reviews", response_model=dict)
async def admin_list_pending_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取待审核工具列表（管理员）"""
    query = select(Tool).options(
        selectinload(Tool.tags),
        selectinload(Tool.current_version),
        selectinload(Tool.owner)
    ).where(
        Tool.provider_type == ToolProviderType.USER.value,
        Tool.review_status == ToolReviewStatus.PENDING.value
    )

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Tool.created_at.asc())  # 按提交时间升序，先提交先审核

    result = await db.execute(query)
    tools = result.scalars().all()

    items = [add_provider_label(ToolListResponse.model_validate(t).model_dump()) for t in tools]

    return success_response(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    )
