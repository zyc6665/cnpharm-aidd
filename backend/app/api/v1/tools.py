# backend/app/api/v1/tools.py
"""工具管理API"""

from datetime import datetime
from pathlib import Path
import sys
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List, Literal

from app.database.session import get_db
from app.models.users import User
from app.models.tools import (
    Tool, ToolCategory, ToolVersion, Tag, ToolFavorite, ToolStatus,
    ToolWorkbenchGroup, ToolWorkbenchGroupMapping,
    ToolProviderType, ToolReviewStatus
)
from app.auth.dependencies import get_current_user, get_current_user_optional, get_admin_user
from app.schemas.tools import (
    ToolCreate, ToolUpdate, ToolResponse, ToolListResponse,
    ToolVersionCreate, ToolVersionResponse, TagCreate, TagResponse,
    ToolCategoryCreate, ToolCategoryUpdate, ToolCategoryResponse,
    ToolCategoryStatusUpdate, ToolCategoryReorderRequest, ToolImportRequest,
    ToolWorkbenchGroupCreate, ToolWorkbenchGroupUpdate, ToolWorkbenchGroupResponse,
    ToolWorkbenchGroupReorderRequest, ToolWorkbenchGroupMappingCreate,
    ToolWorkbenchGroupMappingUpdate, ToolWorkbenchGroupMappingResponse,
    ToolWorkbenchGroupToolResponse, ToolWorkbenchGroupPublicResponse,
    ToolContractResponse,
)
from app.common.responses import success_response, error_response
from app.common.exceptions import NotFoundException, ForbiddenException, ConflictException, ValidationException
from app.services.tool_examples import (
    apply_tool_example_to_user,
    build_tool_example_file_preview,
    build_tool_example_response,
)
from app.services.tool_contracts import (
    build_tool_contract,
    collect_tool_contract_config_validation_errors,
    collect_tool_contract_validation_errors,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tool_import_config import ToolImportConfigError, validate_tool_import_config

router = APIRouter()
admin_category_router = APIRouter(prefix="/admin/tool-categories", tags=["工具分类管理"])
admin_workbench_group_router = APIRouter(prefix="/admin/workbench-groups", tags=["工具工作台分组管理"])
admin_workbench_group_mapping_router = APIRouter(
    prefix="/admin/workbench-group-mappings",
    tags=["工具工作台分组映射管理"],
)


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


def serialize_workbench_group(group: ToolWorkbenchGroup) -> dict:
    """统一序列化工作台分组响应。"""
    return ToolWorkbenchGroupResponse.model_validate(group).model_dump()


def serialize_workbench_group_mapping(mapping: ToolWorkbenchGroupMapping) -> dict:
    """统一序列化工作台分组映射响应。"""
    return ToolWorkbenchGroupMappingResponse.model_validate(mapping).model_dump()


def serialize_public_workbench_group_tool(
    tool: Tool,
    *,
    is_recommended: bool,
    sort_order: int,
) -> dict:
    """统一序列化公开工作台分组中的工具摘要。"""
    contract = build_validated_tool_contract(tool) if tool.current_version else None
    return ToolWorkbenchGroupToolResponse.model_validate(
        {
            "id": tool.id,
            "name": tool.name,
            "slug": tool.slug,
            "description": tool.description,
            "category_id": tool.category_id,
            "category": tool.tool_category.name if tool.tool_category else tool.category,
            "icon": tool.icon,
            "icon_url": tool.icon_url,
            "status": tool.status,
            "is_public": tool.is_public,
            "is_recommended": is_recommended,
            "sort_order": sort_order,
            "contract": contract,
        }
    ).model_dump()


def serialize_public_workbench_group(group: ToolWorkbenchGroup, tools: List[dict]) -> dict:
    """统一序列化公开工作台分组响应。"""
    group_data = ToolWorkbenchGroupPublicResponse.model_validate(
        {
            "id": group.id,
            "name": group.name,
            "slug": group.slug,
            "description": group.description,
            "sort_order": group.sort_order,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
            "tools": tools,
        }
    ).model_dump()
    return group_data


async def load_tool_with_current_version(db: AsyncSession, tool_id: str) -> Tool:
    """加载工具及当前版本。"""
    result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.current_version))
        .where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise NotFoundException("工具不存在")
    if not tool.current_version:
        raise ValidationException("工具暂无可用版本")
    return tool


def build_validated_tool_contract(tool: Tool) -> dict:
    """构建带校验状态的工具契约。"""
    errors: list[str] = []
    current_version = tool.current_version
    config = current_version.config if current_version is not None else None

    if current_version is not None and isinstance(config, dict):
        validation_payload = {
            "name": tool.name,
            "slug": tool.slug,
            "description": tool.description or "",
            "version": current_version.version,
            "tool_config": config,
        }
        try:
            validate_tool_import_config(validation_payload)
        except ToolImportConfigError as exc:
            errors.append(str(exc))

    errors.extend(collect_tool_contract_validation_errors(tool))
    errors = list(dict.fromkeys(errors))
    contract = build_tool_contract(tool)
    contract["validation"] = {
        "status": "invalid" if errors else "valid",
        "errors": errors,
    }
    return ToolContractResponse.model_validate(contract).model_dump(by_alias=True)


async def commit_or_raise_conflict(db: AsyncSession, message: str) -> None:
    """提交事务并将唯一约束冲突转换为业务异常。"""
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(message) from exc


async def list_workbench_groups_in_order(db: AsyncSession) -> List[ToolWorkbenchGroup]:
    """按排序读取全部工作台分组。"""
    result = await db.execute(
        select(ToolWorkbenchGroup)
        .order_by(ToolWorkbenchGroup.sort_order.asc(), ToolWorkbenchGroup.created_at.asc())
    )
    return list(result.scalars().all())


def resequence_workbench_groups(groups: List[ToolWorkbenchGroup]) -> None:
    """将工作台分组排序重排为连续值。"""
    for index, group in enumerate(groups):
        group.sort_order = index


async def move_workbench_group_to_position(
    db: AsyncSession,
    group: ToolWorkbenchGroup,
    target_position: int,
) -> List[ToolWorkbenchGroup]:
    """将工作台分组移动到指定位置并重排全部分组。"""
    groups = await list_workbench_groups_in_order(db)
    ordered_groups = [item for item in groups if item.id != group.id]
    if target_position > len(ordered_groups):
        raise ValidationException("工作台分组排序值超出范围")

    ordered_groups.insert(target_position, group)
    resequence_workbench_groups(ordered_groups)
    return ordered_groups


async def list_group_mappings_in_order(
    db: AsyncSession,
    group_id: str,
    exclude_mapping_id: Optional[str] = None,
) -> List[ToolWorkbenchGroupMapping]:
    """按排序读取指定分组内映射。"""
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


def resequence_group_mappings(mappings: List[ToolWorkbenchGroupMapping]) -> None:
    """将分组内映射排序重排为连续值。"""
    for index, mapping in enumerate(mappings):
        mapping.sort_order = index


async def move_mapping_between_groups(
    db: AsyncSession,
    mapping: ToolWorkbenchGroupMapping,
    target_group_id: str,
    target_position: int,
) -> None:
    """移动映射并维护受影响分组的顺序。"""
    source_group_id = mapping.group_id

    if source_group_id == target_group_id:
        ordered_mappings = await list_group_mappings_in_order(db, source_group_id, exclude_mapping_id=mapping.id)
        if target_position > len(ordered_mappings):
            raise ValidationException("工作台分组映射排序值超出范围")
        if len(ordered_mappings) == 0:
            mapping.sort_order = target_position
            return
        ordered_mappings.insert(target_position, mapping)
        resequence_group_mappings(ordered_mappings)
        return

    source_mappings = await list_group_mappings_in_order(db, source_group_id, exclude_mapping_id=mapping.id)
    target_mappings = await list_group_mappings_in_order(db, target_group_id)

    if target_position > len(target_mappings):
        raise ValidationException("工作台分组映射排序值超出范围")

    if len(target_mappings) == 0:
        mapping.group_id = target_group_id
        mapping.sort_order = target_position
        resequence_group_mappings(source_mappings)
        return

    mapping.group_id = target_group_id
    target_mappings.insert(target_position, mapping)
    resequence_group_mappings(source_mappings)
    resequence_group_mappings(target_mappings)


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


async def create_or_update_tool_from_import(
    db: AsyncSession,
    current_user: User,
    import_data: ToolImportRequest,
) -> dict:
    """根据导入配置创建工具或追加版本。"""
    try:
        normalized_config = validate_tool_import_config(import_data.config)
    except ToolImportConfigError as exc:
        raise ValidationException(str(exc)) from exc

    contract_errors = collect_tool_contract_config_validation_errors(
        tool_slug=normalized_config["slug"],
        config=normalized_config["tool_config"],
        current_version_active=True,
    )
    if contract_errors:
        raise ValidationException("；".join(contract_errors))

    category = None
    if import_data.category_id:
        category = await require_active_tool_category(db, import_data.category_id)

    result = await db.execute(select(Tool).where(Tool.slug == normalized_config["slug"]))
    tool = result.scalar_one_or_none()
    created_new_tool = tool is None

    tool_fields = {
        "name": normalized_config["name"],
        "description": normalized_config.get("description", ""),
        "icon": normalized_config.get("icon", "🔧"),
        "icon_url": normalized_config.get("icon_url"),
        "is_public": normalized_config.get("is_public", True),
        "gpu_required": normalized_config.get("gpu_required", False),
        "gpu_memory_mb": normalized_config.get("gpu_memory_mb", 0),
        "timeout_sec": normalized_config.get(
            "timeout_sec",
            normalized_config["tool_config"].get("timeout_sec", 600),
        ),
    }

    if created_new_tool:
        tool = Tool(
            owner_id=current_user.id,
            slug=normalized_config["slug"],
            category=normalized_config.get("category", "imported"),
            status=ToolStatus.DRAFT.value,
            provider_type=ToolProviderType.PLATFORM.value,
            review_status=ToolReviewStatus.NOT_REQUIRED.value,
            **tool_fields,
        )
        db.add(tool)
        await db.flush()
    else:
        for field, value in tool_fields.items():
            setattr(tool, field, value)

    if category:
        tool.category_id = category.id
        tool.category = category.name
    elif normalized_config.get("category"):
        tool.category = normalized_config["category"]

    version_value = normalized_config["version"]
    result = await db.execute(
        select(ToolVersion).where(
            ToolVersion.tool_id == tool.id,
            ToolVersion.version == version_value,
        )
    )
    if result.scalar_one_or_none():
        raise ConflictException("版本号已存在")

    tool_version = ToolVersion(
        tool_id=tool.id,
        version=version_value,
        changelog=normalized_config.get("changelog", "Initial version"),
        notes=normalized_config.get("notes"),
        config=normalized_config["tool_config"],
        is_active=True,
    )
    db.add(tool_version)
    await db.flush()

    tool.current_version_id = tool_version.id
    if import_data.publish:
        tool.status = ToolStatus.PUBLISHED.value

    await db.commit()
    tool_response = await load_tool_for_response(db, tool.id)

    return {
        "created_new_tool": created_new_tool,
        "tool": serialize_tool(tool_response),
        "version": ToolVersionResponse.model_validate(tool_version).model_dump(),
    }


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


@router.get("/workbench-groups", response_model=dict)
async def list_public_workbench_groups(
    db: AsyncSession = Depends(get_db),
):
    """获取公开工具工作台分组。"""
    group_result = await db.execute(
        select(ToolWorkbenchGroup)
        .where(ToolWorkbenchGroup.is_enabled.is_(True))
        .order_by(ToolWorkbenchGroup.sort_order.asc(), ToolWorkbenchGroup.created_at.asc())
    )
    groups = list(group_result.scalars().all())
    if not groups:
        return success_response(data=[])

    group_ids = [group.id for group in groups]
    mapping_result = await db.execute(
        select(ToolWorkbenchGroupMapping)
        .options(
            joinedload(ToolWorkbenchGroupMapping.tool).joinedload(Tool.tool_category),
            joinedload(ToolWorkbenchGroupMapping.tool).joinedload(Tool.current_version),
        )
        .join(ToolWorkbenchGroup, ToolWorkbenchGroup.id == ToolWorkbenchGroupMapping.group_id)
        .join(Tool, Tool.id == ToolWorkbenchGroupMapping.tool_id)
        .where(
            ToolWorkbenchGroupMapping.group_id.in_(group_ids),
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
    mappings = list(mapping_result.scalars().all())

    tools_by_group_id: dict[str, List[dict]] = {group.id: [] for group in groups}
    for mapping in mappings:
        if mapping.tool is None:
            continue
        tools_by_group_id[mapping.group_id].append(
            serialize_public_workbench_group_tool(
                mapping.tool,
                is_recommended=mapping.is_recommended,
                sort_order=mapping.sort_order,
            )
        )

    payload = [
        serialize_public_workbench_group(group, tools_by_group_id.get(group.id, []))
        for group in groups
    ]
    return success_response(data=payload)


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


@router.get("/{tool_id}/example", response_model=dict)
async def get_tool_example(
    tool_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取工具默认示例。"""
    tool = await load_tool_with_current_version(db, tool_id)
    example = build_tool_example_response(tool)
    return success_response(data=example.model_dump() if example else None)


@router.post("/{tool_id}/example/apply", response_model=dict)
async def apply_tool_example(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """将工具默认示例应用到当前用户文件空间。"""
    tool = await load_tool_with_current_version(db, tool_id)
    payload = await apply_tool_example_to_user(db, current_user, tool)
    await db.commit()
    return success_response(data=payload.model_dump(), message="示例已应用")


@router.get("/{tool_id}/contract", response_model=dict)
async def get_tool_contract(
    tool_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """获取工具标准契约。"""
    result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.current_version))
        .where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise NotFoundException("工具不存在")

    is_admin = current_user and current_user.role == "admin"
    is_owner = current_user and tool.owner_id == current_user.id
    if not is_admin and not is_owner and tool.status != ToolStatus.PUBLISHED.value:
        raise NotFoundException("工具不存在")

    if not tool.current_version:
        raise ValidationException("工具暂无可用版本")

    return success_response(data=build_validated_tool_contract(tool))


@router.get("/{tool_id}/example/files/{field}/preview", response_model=dict)
async def preview_tool_example_file(
    tool_id: str,
    field: str,
    db: AsyncSession = Depends(get_db),
):
    """预览工具示例文件。"""
    tool = await load_tool_with_current_version(db, tool_id)
    payload = build_tool_example_file_preview(tool, field)
    return success_response(data=payload.model_dump())


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

@router.post("/import-config", response_model=dict)
async def import_tool_config(
    import_data: ToolImportRequest,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员导入 platform_tool 配置。"""
    result = await create_or_update_tool_from_import(db, current_user, import_data)
    return success_response(data=result, message="工具配置导入成功")

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

    if "slug" in update_data and update_data["slug"] != tool.slug:
        slug_conflict = await db.execute(
            select(Tool.id).where(Tool.slug == update_data["slug"], Tool.id != tool.id)
        )
        if slug_conflict.scalar_one_or_none():
            raise ConflictException("工具标识已存在")

    # 更新字段
    for field, value in update_data.items():
        setattr(tool, field, value)

    await commit_or_raise_conflict(db, "工具标识已存在")
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
    tool = await load_tool_with_current_version(db, tool_id)

    errors = build_validated_tool_contract(tool)["validation"]["errors"]
    if errors:
        raise ValidationException("；".join(str(error) for error in errors))

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


@admin_workbench_group_router.get("", response_model=dict)
async def admin_list_workbench_groups(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员获取全部工作台分组。"""
    groups = [serialize_workbench_group(group) for group in await list_workbench_groups_in_order(db)]
    return success_response(data=groups)


@admin_workbench_group_router.post("", response_model=dict)
async def admin_create_workbench_group(
    group_data: ToolWorkbenchGroupCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员创建工作台分组。"""
    existing = await db.execute(
        select(ToolWorkbenchGroup).where(
            or_(ToolWorkbenchGroup.name == group_data.name, ToolWorkbenchGroup.slug == group_data.slug)
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException("工作台分组名称或标识已存在")

    sort_order = group_data.sort_order
    if "sort_order" not in group_data.model_fields_set:
        max_sort_result = await db.execute(select(func.max(ToolWorkbenchGroup.sort_order)))
        sort_order = (max_sort_result.scalar() or 0) + 1

    group = ToolWorkbenchGroup(
        name=group_data.name,
        slug=group_data.slug,
        description=group_data.description,
        sort_order=sort_order,
        is_enabled=group_data.is_enabled,
    )
    db.add(group)
    await commit_or_raise_conflict(db, "工作台分组名称或标识已存在")
    await db.refresh(group)
    return success_response(data=serialize_workbench_group(group), message="工作台分组创建成功")


@admin_workbench_group_router.post("/reorder", response_model=dict)
async def admin_reorder_workbench_groups(
    reorder_data: ToolWorkbenchGroupReorderRequest,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员重排工作台分组。"""
    all_groups = await list_workbench_groups_in_order(db)
    all_group_ids = [group.id for group in all_groups]
    if (
        len(reorder_data.group_ids) != len(all_group_ids)
        or len(set(reorder_data.group_ids)) != len(reorder_data.group_ids)
        or set(reorder_data.group_ids) != set(all_group_ids)
    ):
        raise ValidationException("工作台分组重排必须包含全部且唯一的分组ID")

    groups = {group.id: group for group in all_groups}
    resequence_workbench_groups([groups[group_id] for group_id in reorder_data.group_ids])

    await db.commit()
    ordered_groups = [serialize_workbench_group(groups[group_id]) for group_id in reorder_data.group_ids]
    return success_response(data=ordered_groups, message="工作台分组排序更新成功")


@admin_workbench_group_router.put("/{group_id}", response_model=dict)
async def admin_update_workbench_group(
    group_id: str,
    group_data: ToolWorkbenchGroupUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员更新工作台分组。"""
    result = await db.execute(select(ToolWorkbenchGroup).where(ToolWorkbenchGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise NotFoundException("工作台分组不存在")

    update_data = group_data.model_dump(exclude_unset=True)
    sort_order = update_data.pop("sort_order", None)
    if "name" in update_data or "slug" in update_data:
        conflict_conditions = []
        if "name" in update_data:
            conflict_conditions.append(ToolWorkbenchGroup.name == update_data["name"])
        if "slug" in update_data:
            conflict_conditions.append(ToolWorkbenchGroup.slug == update_data["slug"])
        conflict_result = await db.execute(
            select(ToolWorkbenchGroup).where(
                ToolWorkbenchGroup.id != group_id,
                or_(*conflict_conditions)
            )
        )
        if conflict_result.scalar_one_or_none():
            raise ConflictException("工作台分组名称或标识已存在")

    for field, value in update_data.items():
        setattr(group, field, value)

    if sort_order is not None and sort_order != group.sort_order:
        await move_workbench_group_to_position(db, group, sort_order)

    await commit_or_raise_conflict(db, "工作台分组名称或标识已存在")
    await db.refresh(group)
    return success_response(data=serialize_workbench_group(group), message="工作台分组更新成功")


@admin_workbench_group_router.delete("/{group_id}", response_model=dict)
async def admin_delete_workbench_group(
    group_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员删除工作台分组。"""
    group = await db.get(ToolWorkbenchGroup, group_id)
    if not group:
        raise NotFoundException("工作台分组不存在")

    mapping_count_result = await db.execute(
        select(func.count(ToolWorkbenchGroupMapping.id)).where(
            ToolWorkbenchGroupMapping.group_id == group_id
        )
    )
    if (mapping_count_result.scalar() or 0) > 0:
        raise ConflictException("工作台分组下仍有关联工具，无法删除")

    await db.delete(group)
    await db.flush()
    remaining_groups = await list_workbench_groups_in_order(db)
    resequence_workbench_groups(remaining_groups)
    await db.commit()
    return success_response(message="工作台分组删除成功")


@admin_workbench_group_mapping_router.get("", response_model=dict)
async def admin_list_workbench_group_mappings(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员获取全部工作台分组映射。"""
    result = await db.execute(
        select(ToolWorkbenchGroupMapping)
        .join(ToolWorkbenchGroup, ToolWorkbenchGroup.id == ToolWorkbenchGroupMapping.group_id)
        .order_by(
            ToolWorkbenchGroup.sort_order.asc(),
            ToolWorkbenchGroupMapping.sort_order.asc(),
            ToolWorkbenchGroupMapping.created_at.asc(),
        )
    )
    mappings = [serialize_workbench_group_mapping(mapping) for mapping in result.scalars().all()]
    return success_response(data=mappings)


@admin_workbench_group_mapping_router.post("", response_model=dict)
async def admin_create_workbench_group_mapping(
    mapping_data: ToolWorkbenchGroupMappingCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员创建工作台分组映射。"""
    tool = await db.get(Tool, mapping_data.tool_id)
    if not tool:
        raise ValidationException("工具不存在")

    group = await db.get(ToolWorkbenchGroup, mapping_data.group_id)
    if not group:
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
    await commit_or_raise_conflict(db, "工具与工作台分组映射已存在")
    await db.refresh(mapping)
    return success_response(data=serialize_workbench_group_mapping(mapping), message="工作台分组映射创建成功")


@admin_workbench_group_mapping_router.put("/{mapping_id}", response_model=dict)
async def admin_update_workbench_group_mapping(
    mapping_id: str,
    mapping_data: ToolWorkbenchGroupMappingUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员更新工作台分组映射。"""
    mapping = await db.get(ToolWorkbenchGroupMapping, mapping_id)
    if not mapping:
        raise NotFoundException("工作台分组映射不存在")

    update_data = mapping_data.model_dump(exclude_unset=True)
    requested_sort_order = update_data.pop("sort_order", None)
    new_tool_id = update_data.get("tool_id", mapping.tool_id)
    new_group_id = update_data.get("group_id", mapping.group_id)

    if "tool_id" in update_data:
        tool = await db.get(Tool, new_tool_id)
        if not tool:
            raise ValidationException("工具不存在")

    if "group_id" in update_data:
        group = await db.get(ToolWorkbenchGroup, new_group_id)
        if not group:
            raise ValidationException("工作台分组不存在")

    if new_tool_id != mapping.tool_id or new_group_id != mapping.group_id:
        conflict_result = await db.execute(
            select(ToolWorkbenchGroupMapping).where(
                ToolWorkbenchGroupMapping.id != mapping_id,
                ToolWorkbenchGroupMapping.tool_id == new_tool_id,
                ToolWorkbenchGroupMapping.group_id == new_group_id,
            )
        )
        if conflict_result.scalar_one_or_none():
            raise ConflictException("工具与工作台分组映射已存在")

    if requested_sort_order is not None:
        if new_group_id != mapping.group_id or requested_sort_order != mapping.sort_order:
            await move_mapping_between_groups(db, mapping, new_group_id, requested_sort_order)
        update_data["group_id"] = mapping.group_id
        update_data["sort_order"] = mapping.sort_order
    elif new_group_id != mapping.group_id:
        current_group_mappings = await list_group_mappings_in_order(db, new_group_id)
        await move_mapping_between_groups(db, mapping, new_group_id, len(current_group_mappings))
        update_data["group_id"] = mapping.group_id
        update_data["sort_order"] = mapping.sort_order

    for field, value in update_data.items():
        setattr(mapping, field, value)

    await commit_or_raise_conflict(db, "工具与工作台分组映射已存在")
    await db.refresh(mapping)
    return success_response(data=serialize_workbench_group_mapping(mapping), message="工作台分组映射更新成功")


@admin_workbench_group_mapping_router.delete("/{mapping_id}", response_model=dict)
async def admin_delete_workbench_group_mapping(
    mapping_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员删除工作台分组映射。"""
    mapping = await db.get(ToolWorkbenchGroupMapping, mapping_id)
    if not mapping:
        raise NotFoundException("工作台分组映射不存在")

    group_id = mapping.group_id
    await db.delete(mapping)
    await db.flush()
    remaining_mappings = await list_group_mappings_in_order(db, group_id, exclude_mapping_id=mapping_id)
    resequence_group_mappings(remaining_mappings)
    await db.commit()
    return success_response(message="工作台分组映射删除成功")
