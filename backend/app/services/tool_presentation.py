"""工具领域的序列化、契约拼装与只读查询。

这些函数原先散落在 `app.api.v1.tool_route_utils`，被 `app.tool_packages`
等非 API 层反向导入，形成「下层依赖路由层」的架构违规。下沉到服务层后，
API 路由模块只做编排，领域读取与序列化由本模块承担。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.models.tools import (
    Tool,
    ToolCategory,
    ToolProviderType,
    ToolStatus,
    ToolVersion,
)
from app.models.tool_packages import ToolPackage
from app.models.users import User
from app.schemas.tools import (
    ToolResponse,
    ToolVersionResponse,
    ToolVersionPublicResponse,
)
from app.services.tool_contracts import (
    build_tool_contract,
    collect_tool_contract_validation_errors,
)
from app.services.tool_import_config import (
    ToolImportConfigError,
    validate_tool_import_config,
)


def serialize_tool(
    tool: Tool,
    schema_class=ToolResponse,
    *,
    tool_package: ToolPackage | None = None,
    expose_runtime_config: bool = True,
) -> dict:
    tool_data = schema_class.model_validate(tool).model_dump()
    tool_data["category_id"] = tool.category_id
    tool_data["category"] = (
        tool.tool_category.name if tool.tool_category else tool.category
    )
    tool_data["contract"] = (
        sanitize_public_tool_contract(build_validated_tool_contract(tool))
        if tool.current_version and not expose_runtime_config
        else build_validated_tool_contract(tool)
        if tool.current_version
        else None
    )
    tool_data["deployment"] = build_tool_deployment(tool, tool_data["contract"])
    if not expose_runtime_config and tool.current_version is not None:
        public_version = serialize_public_tool_version(tool.current_version)
        if tool_package is not None:
            public_version["tool_package"] = _serialize_tool_package_summary(
                tool_package,
                expose_runtime_config=False,
            )
        tool_data["current_version"] = public_version
    elif tool_package is not None and tool_data.get("current_version"):
        version_data = tool_data["current_version"]
        config = version_data.get("config") or {}
        config = (
            sanitize_public_tool_config(config)
            if not expose_runtime_config
            else dict(config)
        )
        config["tool_package"] = _serialize_tool_package_summary(
            tool_package,
            expose_runtime_config=expose_runtime_config,
        )
        version_data["config"] = config
    return tool_data


def serialize_tool_version(
    version: ToolVersion,
    *,
    expose_runtime_config: bool = True,
) -> dict:
    """Serialize a ToolVersion with an explicit public/internal config contract."""
    payload = ToolVersionResponse.model_validate(version).model_dump()
    if not expose_runtime_config:
        payload["config"] = sanitize_public_tool_config(payload.get("config") or {})
    return payload


def serialize_public_tool_version(
    version: ToolVersion,
) -> dict:
    """Serialize only the public metadata contract for a tool version."""
    return ToolVersionPublicResponse.model_validate(version).model_dump()


_PUBLIC_SCHEMA_KEYS = {
    "input_schema",
    "output_schema",
    "parameter_schema",
    "parameters_schema",
    "artifact_schema",
}
_SENSITIVE_RUNTIME_KEYS = {
    "authorization",
    "auth_ref",
    "api_key",
    "apikey",
    "base_url",
    "command",
    "credentials",
    "docker_args",
    "endpoint",
    "entrypoint",
    "env",
    "headers",
    "host",
    "image",
    "password",
    "password_ref",
    "remote_base_dir",
    "remote_base_url",
    "runtime_config",
    "script",
    "script_content",
    "script_path",
    "secret",
    "token",
    "username",
    "variants",
    "volume_mounts",
    "workdir",
    "working_dir",
}
_SENSITIVE_RUNTIME_FRAGMENTS = (
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
)


def _is_sensitive_runtime_key(key: str) -> bool:
    normalized = key.strip().casefold().replace("-", "_")
    return normalized in _SENSITIVE_RUNTIME_KEYS or any(
        fragment in normalized for fragment in _SENSITIVE_RUNTIME_FRAGMENTS
    )


def sanitize_public_tool_config(value: Any) -> Any:
    """Remove runtime secrets while preserving user-facing input/output schemas."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_runtime_key(key_text):
                continue
            if key_text.casefold() in _PUBLIC_SCHEMA_KEYS or key_text == "schema":
                sanitized[key] = _sanitize_public_schema(item)
            else:
                sanitized[key] = sanitize_public_tool_config(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_public_tool_config(item) for item in value]
    return value


_SCHEMA_MAP_KEYS = {"properties", "patternProperties", "$defs", "definitions"}
_SCHEMA_SINGLE_KEYS = {
    "additionalProperties",
    "contains",
    "else",
    "if",
    "items",
    "not",
    "propertyNames",
    "then",
}
_SCHEMA_LIST_KEYS = {"allOf", "anyOf", "oneOf", "prefixItems"}


def _sanitize_public_schema(value: Any, *, sensitive_value: bool = False) -> Any:
    if isinstance(value, list):
        return [
            _sanitize_public_schema(item, sensitive_value=sensitive_value)
            for item in value
        ]
    if not isinstance(value, dict):
        return value

    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if sensitive_value and key_text in {"default", "example", "examples"}:
            continue
        if _is_sensitive_runtime_key(key_text):
            continue
        if key_text in _SCHEMA_MAP_KEYS and isinstance(item, dict):
            sanitized[key] = {
                name: _sanitize_public_schema(
                    schema,
                    sensitive_value=_is_sensitive_runtime_key(str(name)),
                )
                for name, schema in item.items()
            }
        elif key_text in {"input", "output"}:
            sanitized[key] = _sanitize_public_schema(item)
        elif key_text in _SCHEMA_SINGLE_KEYS:
            sanitized[key] = _sanitize_public_schema(item)
        elif key_text in _SCHEMA_LIST_KEYS:
            sanitized[key] = _sanitize_public_schema(item)
        else:
            sanitized[key] = sanitize_public_tool_config(item)
    return sanitized


def sanitize_public_tool_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Return the user-facing Tool Contract without executor deployment details."""
    return sanitize_public_tool_config(contract)


def build_tool_deployment(
    tool: Tool,
    contract: dict[str, Any] | None = None,
) -> dict[str, str | None]:
    """Return a safe deployment summary shared by tool surfaces."""
    current_version = getattr(tool, "current_version", None)
    config = getattr(current_version, "config", None)
    config = config if isinstance(config, dict) else {}
    contract_executor = contract.get("executor") if isinstance(contract, dict) else None
    contract_executor = contract_executor if isinstance(contract_executor, dict) else {}
    executor_type = contract_executor.get("type") or config.get("type")
    return {
        "kind": (
            "platform_builtin"
            if config.get("type") == "builtin"
            else "external_service"
        ),
        "executor_type": str(executor_type) if executor_type else None,
    }


def require_tool_read_access(tool: Tool, current_user: Optional[User]) -> None:
    """Hide private and unpublished tools from users other than owner/admin."""
    is_admin = current_user is not None and current_user.role == "admin"
    is_owner = current_user is not None and tool.owner_id == current_user.id
    is_public = tool.status == ToolStatus.PUBLISHED.value and (
        bool(tool.is_public) or tool.provider_type == ToolProviderType.PLATFORM.value
    )
    if not (is_admin or is_owner or is_public):
        raise NotFoundException("工具不存在")


async def load_tool_packages_for_tools(
    db: AsyncSession,
    tools: Iterable[Tool],
) -> dict[str, ToolPackage]:
    """按旧工具 slug 读取当前 Tool Package 摘要，供列表/详情响应复用。"""
    slugs = sorted({tool.slug for tool in tools if tool.slug})
    if not slugs:
        return {}
    packages = (
        (
            await db.execute(
                select(ToolPackage)
                .options(selectinload(ToolPackage.current_version))
                .where(ToolPackage.slug.in_(slugs))
            )
        )
        .scalars()
        .all()
    )
    return {package.slug: package for package in packages}


def _serialize_tool_package_summary(
    package: ToolPackage,
    *,
    expose_runtime_config: bool = True,
) -> dict[str, Any]:
    version = package.current_version
    return {
        "id": package.id,
        "slug": package.slug,
        "name": package.name,
        "status": package.status,
        "current_version_id": package.current_version_id,
        "version": version.version if version else None,
        "version_id": version.id if version else None,
        "validation_status": version.validation_status if version else None,
        "validation_errors": list(version.validation_errors or []) if version else [],
        "manifest": (
            version.manifest
            if expose_runtime_config and version
            else sanitize_public_tool_config(version.manifest)
            if version
            else None
        ),
    }


async def load_tool_with_current_version(db: AsyncSession, tool_id: str) -> Tool:
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


async def load_readable_tool_with_current_version(
    db: AsyncSession,
    tool_id: str,
    current_user: Optional[User],
) -> Tool:
    tool = await load_tool_with_current_version(db, tool_id)
    require_tool_read_access(tool, current_user)
    return tool


def build_validated_tool_contract(tool: Tool) -> dict:
    errors: list[str] = []
    current_version = tool.current_version
    config = current_version.config if current_version is not None else None
    if current_version is not None and isinstance(config, dict):
        if config.get("type") == "builtin":
            pass
        else:
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


async def require_active_tool_category(
    db: AsyncSession, category_id: str
) -> ToolCategory:
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


