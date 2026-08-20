"""公开工具查询与用户交互路由。"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.api.v1.tool_route_utils import (
    build_validated_tool_contract,
    load_tool_packages_for_tools,
    load_tool_with_current_version,
    serialize_tool,
)
from app.auth.dependencies import get_current_user, get_current_user_optional
from app.common.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.models.statistics import ToolStatistics
from app.models.tools import (
    Tag,
    Tool,
    ToolCategory,
    ToolFavorite,
    ToolStatus,
    ToolWorkbenchGroup,
    ToolWorkbenchGroupMapping,
)
from app.models.users import User
from app.schemas.tools import (
    TagResponse,
    ToolCategoryResponse,
    ToolContractResponse,
    ToolListResponse,
    ToolResponse,
    ToolWorkbenchGroupPublicResponse,
    ToolWorkbenchGroupToolResponse,
)
from app.services.tool_examples import (
    apply_tool_example_to_user,
    build_tool_example_file_preview,
    build_tool_example_response,
)

router = APIRouter()


def _serialize_category(
    category: ToolCategory, tool_count: Optional[int] = None
) -> dict:
    payload = ToolCategoryResponse.model_validate(category).model_dump()
    if tool_count is not None:
        payload["tool_count"] = tool_count
        payload["count"] = tool_count
    return payload


def _serialize_workbench_tool(
    tool: Tool,
    *,
    is_recommended: bool,
    sort_order: int,
) -> dict:
    contract = build_validated_tool_contract(tool) if tool.current_version else None
    tags = sorted(tool.tags, key=lambda tag: (tag.sort_order, tag.name))
    return ToolWorkbenchGroupToolResponse.model_validate(
        {
            "id": tool.id,
            "name": tool.name,
            "slug": tool.slug,
            "description": tool.description,
            "category_id": tool.category_id,
            "category": (
                tool.tool_category.name if tool.tool_category else tool.category
            ),
            "icon": tool.icon,
            "icon_url": tool.icon_url,
            "status": tool.status,
            "is_public": tool.is_public,
            "is_recommended": is_recommended,
            "sort_order": sort_order,
            "tags": [TagResponse.model_validate(tag).model_dump() for tag in tags],
            "contract": contract,
        }
    ).model_dump()


@router.get("", response_model=dict)
async def list_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    view: Optional[Literal["public", "favorites"]] = Query(
        None, description="视图类型"
    ),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    query = select(Tool).options(
        selectinload(Tool.tags),
        selectinload(Tool.current_version),
        selectinload(Tool.tool_category),
        joinedload(Tool.statistics),
    )
    is_admin = current_user and current_user.role == "admin"
    if view == "favorites":
        if not current_user:
            raise ForbiddenException("请先登录")
        query = query.join(ToolFavorite, ToolFavorite.tool_id == Tool.id).where(
            ToolFavorite.user_id == current_user.id
        )
    elif not is_admin:
        query = query.where(Tool.status == ToolStatus.PUBLISHED.value)
    elif status:
        query = query.where(Tool.status == status)
    if category:
        query = query.where(
            or_(
                Tool.category == category,
                Tool.category_id == category,
                Tool.tool_category.has(ToolCategory.name == category),
                Tool.tool_category.has(ToolCategory.slug == category),
            )
        )
    if tag:
        query = query.where(Tool.tags.any(Tag.name == tag))
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Tool.name.ilike(pattern),
                Tool.description.ilike(pattern),
                Tool.slug.ilike(pattern),
            )
        )
    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar()
    result = await db.execute(
        query.offset((page - 1) * page_size)
        .limit(page_size)
        .order_by(Tool.created_at.desc())
    )
    tools = result.scalars().all()
    package_by_slug = await load_tool_packages_for_tools(db, tools)
    return paginated_response(
        items=[
            serialize_tool(
                tool,
                ToolListResponse,
                tool_package=package_by_slug.get(tool.slug),
            )
            for tool in tools
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/workbench-groups", response_model=dict)
async def list_public_workbench_groups(db: AsyncSession = Depends(get_db)):
    groups = list(
        (
            await db.execute(
                select(ToolWorkbenchGroup)
                .where(ToolWorkbenchGroup.is_enabled.is_(True))
                .order_by(
                    ToolWorkbenchGroup.sort_order.asc(),
                    ToolWorkbenchGroup.created_at.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    if not groups:
        return success_response(data=[])
    mappings = list(
        (
            await db.execute(
                select(ToolWorkbenchGroupMapping)
                .options(
                    joinedload(ToolWorkbenchGroupMapping.tool).joinedload(
                        Tool.tool_category
                    ),
                    joinedload(ToolWorkbenchGroupMapping.tool).joinedload(
                        Tool.current_version
                    ),
                    joinedload(ToolWorkbenchGroupMapping.tool).selectinload(
                        Tool.tags
                    ),
                )
                .join(
                    ToolWorkbenchGroup,
                    ToolWorkbenchGroup.id == ToolWorkbenchGroupMapping.group_id,
                )
                .join(Tool, Tool.id == ToolWorkbenchGroupMapping.tool_id)
                .where(
                    ToolWorkbenchGroupMapping.group_id.in_(
                        [group.id for group in groups]
                    ),
                    ToolWorkbenchGroupMapping.is_enabled.is_(True),
                    Tool.status == ToolStatus.PUBLISHED.value,
                    Tool.is_public.is_(True),
                )
                .order_by(
                    ToolWorkbenchGroup.sort_order.asc(),
                    ToolWorkbenchGroupMapping.sort_order.asc(),
                    ToolWorkbenchGroupMapping.created_at.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    tools_by_group: dict[str, list[dict]] = {group.id: [] for group in groups}
    for mapping in mappings:
        if mapping.tool is not None:
            tools_by_group[mapping.group_id].append(
                _serialize_workbench_tool(
                    mapping.tool,
                    is_recommended=mapping.is_recommended,
                    sort_order=mapping.sort_order,
                )
            )
    payload = [
        ToolWorkbenchGroupPublicResponse.model_validate(
            {
                "id": group.id,
                "name": group.name,
                "slug": group.slug,
                "description": group.description,
                "sort_order": group.sort_order,
                "created_at": group.created_at,
                "updated_at": group.updated_at,
                "tools": tools_by_group.get(group.id, []),
            }
        ).model_dump()
        for group in groups
    ]
    return success_response(data=payload)


@router.get("/categories", response_model=dict)
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ToolCategory, func.count(Tool.id).label("tool_count"))
        .outerjoin(
            Tool,
            and_(
                Tool.category_id == ToolCategory.id,
                Tool.status == ToolStatus.PUBLISHED.value,
            ),
        )
        .where(ToolCategory.is_enabled.is_(True))
        .group_by(ToolCategory.id)
        .order_by(ToolCategory.sort_order.asc(), ToolCategory.created_at.asc())
    )
    return success_response(
        data=[_serialize_category(category, count) for category, count in result.all()]
    )


@router.get("/tags", response_model=dict)
async def list_tags(db: AsyncSession = Depends(get_db)):
    tags = (await db.execute(select(Tag))).scalars().all()
    return success_response(
        data=[TagResponse.model_validate(tag).model_dump() for tag in tags]
    )


@router.get("/{tool_id}/example", response_model=dict)
async def get_tool_example(tool_id: str, db: AsyncSession = Depends(get_db)):
    example = build_tool_example_response(
        await load_tool_with_current_version(db, tool_id)
    )
    return success_response(data=example.model_dump() if example else None)


@router.post("/{tool_id}/example/apply", response_model=dict)
async def apply_tool_example(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await apply_tool_example_to_user(
        db,
        current_user,
        await load_tool_with_current_version(db, tool_id),
    )
    await db.commit()
    return success_response(data=payload.model_dump(), message="示例已应用")


@router.get("/{tool_id}/contract", response_model=dict)
async def get_tool_contract(
    tool_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    tool = (
        await db.execute(
            select(Tool)
            .options(selectinload(Tool.current_version))
            .where(Tool.id == tool_id)
        )
    ).scalar_one_or_none()
    if not tool:
        raise NotFoundException("工具不存在")
    is_admin = current_user and current_user.role == "admin"
    is_owner = current_user and tool.owner_id == current_user.id
    if not is_admin and not is_owner and tool.status != ToolStatus.PUBLISHED.value:
        raise NotFoundException("工具不存在")
    if not tool.current_version:
        raise ValidationException("工具暂无可用版本")
    return success_response(
        data=ToolContractResponse.model_validate(
            build_validated_tool_contract(tool)
        ).model_dump(by_alias=True)
    )


@router.get("/{tool_id}/example/files/{field}/preview", response_model=dict)
async def preview_tool_example_file(
    tool_id: str,
    field: str,
    db: AsyncSession = Depends(get_db),
):
    payload = build_tool_example_file_preview(
        await load_tool_with_current_version(db, tool_id),
        field,
    )
    return success_response(data=payload.model_dump())


@router.get("/{tool_id}", response_model=dict)
async def get_tool(
    tool_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    tool = (
        await db.execute(
            select(Tool)
            .options(
                selectinload(Tool.tags),
                selectinload(Tool.current_version),
                selectinload(Tool.versions),
                selectinload(Tool.owner),
                selectinload(Tool.tool_category),
                selectinload(Tool.statistics),
            )
            .where(Tool.id == tool_id)
        )
    ).scalar_one_or_none()
    if not tool:
        raise NotFoundException("工具不存在")
    is_admin = current_user and current_user.role == "admin"
    is_owner = current_user and tool.owner_id == current_user.id
    if not is_admin and not is_owner and tool.status != ToolStatus.PUBLISHED.value:
        raise NotFoundException("工具不存在")
    if tool.statistics:
        tool.statistics.view_count += 1
        await db.commit()
    is_favorited = False
    if current_user:
        favorite = await db.execute(
            select(ToolFavorite).where(
                ToolFavorite.user_id == current_user.id,
                ToolFavorite.tool_id == tool_id,
            )
        )
        is_favorited = favorite.scalar_one_or_none() is not None
    package_by_slug = await load_tool_packages_for_tools(db, [tool])
    payload = serialize_tool(
        tool,
        ToolResponse,
        tool_package=package_by_slug.get(tool.slug),
    )
    payload["is_favorited"] = is_favorited
    return success_response(data=payload)


@router.post("/{tool_id}/favorite", response_model=dict)
async def favorite_tool(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tool = (
        await db.execute(
            select(Tool)
            .options(selectinload(Tool.statistics))
            .where(Tool.id == tool_id)
        )
    ).scalar_one_or_none()
    if not tool:
        raise NotFoundException("工具不存在")
    existing = await db.execute(
        select(ToolFavorite).where(
            ToolFavorite.user_id == current_user.id,
            ToolFavorite.tool_id == tool_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException("已收藏该工具")
    favorite = ToolFavorite(user_id=current_user.id, tool_id=tool_id)
    if tool.statistics is None:
        tool.statistics = ToolStatistics(tool_id=tool.id, favorite_count=0)
    tool.statistics.favorite_count += 1
    db.add(favorite)
    await db.commit()
    return success_response(message="收藏成功")


@router.delete("/{tool_id}/favorite", response_model=dict)
async def unfavorite_tool(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    favorite = (
        await db.execute(
            select(ToolFavorite).where(
                ToolFavorite.user_id == current_user.id,
                ToolFavorite.tool_id == tool_id,
            )
        )
    ).scalar_one_or_none()
    if not favorite:
        raise NotFoundException("未收藏该工具")
    tool = (
        await db.execute(
            select(Tool)
            .options(selectinload(Tool.statistics))
            .where(Tool.id == tool_id)
        )
    ).scalar_one_or_none()
    if tool and tool.statistics:
        tool.statistics.favorite_count = max(0, tool.statistics.favorite_count - 1)
    await db.delete(favorite)
    await db.commit()
    return success_response(message="取消收藏成功")
