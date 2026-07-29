"""工具 API 路由共享辅助函数。"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.agents.aidd.registry import upsert_capability_from_config
from app.common.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.tools import (
    Tool,
    ToolCategory,
    ToolProviderType,
    ToolReviewStatus,
    ToolStatus,
    ToolVersion,
)
from app.models.users import User
from app.schemas.tools import ToolImportRequest, ToolResponse, ToolVersionResponse
from app.services.tool_contracts import (
    build_tool_contract,
    collect_tool_contract_config_validation_errors,
    collect_tool_contract_validation_errors,
)
from app.services.tool_import_config import ToolImportConfigError, validate_tool_import_config


def serialize_tool(tool: Tool, schema_class=ToolResponse) -> dict:
    tool_data = schema_class.model_validate(tool).model_dump()
    tool_data["category_id"] = tool.category_id
    tool_data["category"] = tool.tool_category.name if tool.tool_category else tool.category
    return tool_data


async def load_tool_with_current_version(db: AsyncSession, tool_id: str) -> Tool:
    result = await db.execute(
        select(Tool).options(selectinload(Tool.current_version)).where(Tool.id == tool_id)
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise NotFoundException("工具不存在")
    if not tool.current_version:
        raise ValidationException("工具暂无可用版本")
    return tool


def build_validated_tool_contract(tool: Tool) -> dict:
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
    return contract


async def commit_or_raise_conflict(db: AsyncSession, message: str) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(message) from exc


async def require_active_tool_category(db: AsyncSession, category_id: str) -> ToolCategory:
    if not category_id:
        raise ValidationException("工具分类不能为空")
    result = await db.execute(
        select(ToolCategory).where(
            ToolCategory.id == category_id,
            ToolCategory.is_enabled.is_(True),
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise ValidationException("工具分类不存在或已停用")
    return category


async def load_tool_for_response(db: AsyncSession, tool_id: str) -> Tool:
    result = await db.execute(
        select(Tool)
        .options(
            selectinload(Tool.tags),
            selectinload(Tool.current_version),
            selectinload(Tool.tool_category),
            joinedload(Tool.statistics),
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
    try:
        normalized = validate_tool_import_config(import_data.config)
    except ToolImportConfigError as exc:
        raise ValidationException(str(exc)) from exc
    contract_errors = collect_tool_contract_config_validation_errors(
        tool_slug=normalized["slug"],
        config=normalized["tool_config"],
        current_version_active=True,
    )
    if contract_errors:
        raise ValidationException("；".join(contract_errors))

    category: Optional[ToolCategory] = None
    if import_data.category_id:
        category = await require_active_tool_category(db, import_data.category_id)
    tool = (
        await db.execute(select(Tool).where(Tool.slug == normalized["slug"]))
    ).scalar_one_or_none()
    created_new_tool = tool is None
    tool_fields = {
        "name": normalized["name"],
        "description": normalized.get("description", ""),
        "icon": normalized.get("icon", "🔧"),
        "icon_url": normalized.get("icon_url"),
        "is_public": normalized.get("is_public", True),
        "gpu_required": normalized.get("gpu_required", False),
        "gpu_memory_mb": normalized.get("gpu_memory_mb", 0),
        "timeout_sec": normalized.get(
            "timeout_sec",
            normalized["tool_config"].get("timeout_sec", 600),
        ),
    }
    if created_new_tool:
        tool = Tool(
            owner_id=current_user.id,
            slug=normalized["slug"],
            category=normalized.get("category", "imported"),
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
    elif normalized.get("category"):
        tool.category = normalized["category"]

    version_value = normalized["version"]
    existing_version = await db.execute(
        select(ToolVersion).where(
            ToolVersion.tool_id == tool.id,
            ToolVersion.version == version_value,
        )
    )
    if existing_version.scalar_one_or_none():
        raise ConflictException("版本号已存在")
    tool_version = ToolVersion(
        tool_id=tool.id,
        version=version_value,
        changelog=normalized.get("changelog", "Initial version"),
        notes=normalized.get("notes"),
        config=normalized["tool_config"],
        is_active=True,
    )
    db.add(tool_version)
    await db.flush()
    tool.current_version_id = tool_version.id
    if import_data.publish:
        tool.status = ToolStatus.PUBLISHED.value
    await upsert_capability_from_config(db, tool)
    await db.commit()
    return {
        "created_new_tool": created_new_tool,
        "tool": serialize_tool(await load_tool_for_response(db, tool.id)),
        "version": ToolVersionResponse.model_validate(tool_version).model_dump(),
    }
