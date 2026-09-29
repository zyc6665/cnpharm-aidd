"""工具 API 路由共享辅助函数。"""

import hashlib
import base64
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.agents.aidd.registry import upsert_capability_from_config
from app.common.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.common.time import utcnow
from app.files.storage_path import get_file_path
from app.models.files import File as FileModel, FileSourceType
from app.models.tools import (
    Tool,
    ToolCategory,
    ToolProviderType,
    ToolReviewStatus,
    ToolStatus,
    ToolVersion,
)
from app.models.tool_packages import ToolPackage
from app.models.users import User
from app.remote_tools.client import RemoteToolDiscoveryResult
from app.remote_tools.diagnostics import RemoteToolStageDiagnostic
from app.remote_tools.registration import (
    is_remote_tool_v1_config,
    remote_manifest_sha256,
    remote_tool_config,
    remote_tool_publish_errors,
)
from app.remote_tools.schemas import RemoteToolExample
from app.schemas.tasks import TaskCreate
from app.schemas.tools import (
    RemoteToolRegisterRequest,
    ToolImportRequest,
    ToolResponse,
    ToolVersionResponse,
    ToolVersionPublicResponse,
)
from app.services.tool_contracts import (
    build_tool_contract,
    collect_tool_contract_config_validation_errors,
    collect_tool_contract_validation_errors,
)
from app.services.tool_import_config import (
    ToolImportConfigError,
    validate_tool_import_config,
)
from app.tasks.service import create_and_schedule_tool_task


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


def require_tool_read_access(tool: Tool, current_user: Optional[User]) -> None:
    """Hide private and unpublished tools from users other than owner/admin."""
    is_admin = current_user is not None and current_user.role == "admin"
    is_owner = current_user is not None and tool.owner_id == current_user.id
    is_public = (
        tool.status == ToolStatus.PUBLISHED.value and bool(tool.is_public)
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
        elif is_remote_tool_v1_config(config):
            errors.extend(remote_tool_publish_errors(config))
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
        "version": serialize_tool_version(tool_version),
    }


async def create_or_update_remote_tool_from_discovery(
    db: AsyncSession,
    current_user: User,
    register_data: RemoteToolRegisterRequest,
    discovery: RemoteToolDiscoveryResult,
) -> dict:
    """Create or update a remote-tool.v1 draft from validated discovery data."""
    if discovery.manifest is None:
        failing_stage = next(
            (stage for stage in discovery.stages if stage.status == "failure"),
            None,
        )
        message = failing_stage.message if failing_stage else "远程工具 manifest 无效"
        raise ValidationException(message)

    category = await require_active_tool_category(db, register_data.category_id)
    manifest = discovery.manifest
    manifest_payload = manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
    manifest_sha256 = remote_manifest_sha256(manifest_payload)
    metadata = manifest.metadata
    version_value = metadata.version

    tool = (
        await db.execute(select(Tool).where(Tool.slug == metadata.slug))
    ).scalar_one_or_none()
    created_new_tool = tool is None
    if created_new_tool:
        tool = Tool(
            owner_id=current_user.id,
            slug=metadata.slug,
            name=metadata.name,
            description=metadata.description,
            category_id=category.id,
            category=category.name,
            icon=register_data.icon,
            icon_url=register_data.icon_url,
            is_public=register_data.is_public,
            gpu_required=False,
            gpu_memory_mb=0,
            timeout_sec=register_data.timeout_sec,
            status=ToolStatus.DRAFT.value,
            provider_type=ToolProviderType.PLATFORM.value,
            review_status=ToolReviewStatus.NOT_REQUIRED.value,
        )
        db.add(tool)
        await db.flush()
    else:
        tool.name = metadata.name
        tool.description = metadata.description
        tool.category_id = category.id
        tool.category = category.name
        tool.icon = register_data.icon
        tool.icon_url = register_data.icon_url
        tool.is_public = register_data.is_public
        tool.gpu_required = False
        tool.gpu_memory_mb = 0
        tool.timeout_sec = register_data.timeout_sec

    existing_version = (
        await db.execute(
            select(ToolVersion).where(
                ToolVersion.tool_id == tool.id,
                ToolVersion.version == version_value,
            )
        )
    ).scalar_one_or_none()
    if existing_version is not None and tool.status == ToolStatus.PUBLISHED.value:
        raise ConflictException("已发布版本不能覆盖，请发布新的语义版本")

    config = remote_tool_config(
        base_url=register_data.base_url,
        manifest_payload=manifest_payload,
        manifest_sha256=manifest_sha256,
        discovery=discovery,
        publish_on_success=register_data.publish_on_success,
        capacity_policy=register_data.capacity_policy,
    )
    if existing_version is None:
        tool_version = ToolVersion(
            tool_id=tool.id,
            version=version_value,
            changelog="Remote tool manifest registration",
            notes=metadata.description,
            config=config,
            is_active=True,
        )
        db.add(tool_version)
        await db.flush()
    else:
        tool_version = existing_version
        tool_version.config = config
        tool_version.notes = metadata.description
        tool_version.is_active = True

    tool.current_version_id = tool_version.id
    persist_stage = RemoteToolStageDiagnostic(
        name="persist_draft",
        status="success",
        message="Remote tool draft persisted",
    )
    await db.commit()
    stages = [*discovery.stages, persist_stage]
    smoke_test_task_id = await _schedule_remote_smoke_test(
        db=db,
        current_user=current_user,
        register_data=register_data,
        discovery=discovery,
        tool=tool,
        tool_version=tool_version,
        manifest_sha256=manifest_sha256,
        stages=stages,
    )
    return {
        "created_new_tool": created_new_tool,
        "tool": serialize_tool(await load_tool_for_response(db, tool.id)),
        "version": serialize_tool_version(tool_version),
        "manifest_sha256": manifest_sha256,
        "stages": [stage.model_dump() for stage in stages],
        "smoke_test_task_id": smoke_test_task_id,
    }


async def _schedule_remote_smoke_test(
    *,
    db: AsyncSession,
    current_user: User,
    register_data: RemoteToolRegisterRequest,
    discovery: RemoteToolDiscoveryResult,
    tool: Tool,
    tool_version: ToolVersion,
    manifest_sha256: str,
    stages: list[RemoteToolStageDiagnostic],
) -> str | None:
    if not register_data.run_smoke_test:
        return None

    smoke_example = _select_remote_smoke_example(discovery)
    if smoke_example is None:
        stages.append(
            RemoteToolStageDiagnostic(
                name="create_smoke_test",
                status="warning",
                message="缺少 smoke test 样例，已仅注册草稿",
            )
        )
        return None

    try:
        file_ids, remote_example_inputs = await _materialize_remote_example_inputs(
            db=db,
            current_user=current_user,
            base_url=register_data.base_url,
            smoke_example=smoke_example,
        )
        task = await create_and_schedule_tool_task(
            db=db,
            current_user=current_user,
            task_data=TaskCreate(
                name=f"Smoke test - {tool.name}",
                tool_id=str(tool.id),
                tool_version_id=str(tool_version.id),
                params=smoke_example.parameters,
                file_ids=file_ids,
                input_bindings={},
                priority="normal",
            ),
            extra_data={
                "smoke_test": True,
                "smoke_test_type": "remote_tool_v1",
                "publish_on_success": register_data.publish_on_success,
                "manifest_sha256": manifest_sha256,
                "tool_version_id": str(tool_version.id),
                "example_name": smoke_example.name,
                "remote_example_inputs": remote_example_inputs,
            },
        )
    except Exception as exc:
        await db.rollback()
        stages.append(
            RemoteToolStageDiagnostic(
                name="create_smoke_test",
                status="failure",
                message=f"Smoke test task creation failed: {exc}",
            )
        )
        return None
    stages.append(
        RemoteToolStageDiagnostic(
            name="create_smoke_test",
            status="success",
            message="Smoke test task scheduled",
            detail={"task_id": str(task.id), "example_name": smoke_example.name},
        )
    )
    config = dict(tool_version.config or {})
    config["last_smoke_test"] = {
        "status": "scheduled",
        "task_id": str(task.id),
        "manifest_sha256": manifest_sha256,
        "example_name": smoke_example.name,
        "scheduled_at": utcnow().isoformat(),
    }
    tool_version.config = config
    await db.commit()
    return str(task.id)


async def _materialize_remote_example_inputs(
    *,
    db: AsyncSession,
    current_user: User,
    base_url: str,
    smoke_example: RemoteToolExample,
) -> tuple[list[str], dict[str, Any]]:
    file_ids: list[str] = []
    remote_inputs: dict[str, Any] = {}
    for input_name, artifact_example in smoke_example.input_artifacts.items():
        files_by_role: dict[str, str] = {}
        for role, file_example in artifact_example.files.items():
            content = await _load_remote_example_file(base_url, file_example.model_dump())
            declared_sha256 = (file_example.sha256 or "").lower()
            actual_sha256 = hashlib.sha256(content).hexdigest()
            if declared_sha256 and actual_sha256 != declared_sha256:
                raise ValidationException(
                    f"smoke example file checksum mismatch: {input_name}.{role}"
                )
            filename = Path(file_example.filename).name
            file_record = FileModel(
                filename=filename,
                content_type=file_example.content_type or "application/octet-stream",
                size_bytes=len(content),
                sha256=actual_sha256,
                storage_path="pending",
                source_type=FileSourceType.SYSTEM.value,
                owner_id=current_user.id,
                is_public=False,
                is_permanent=False,
                file_meta={
                    "remote_smoke_example": True,
                    "example_name": smoke_example.name,
                    "input_name": input_name,
                    "file_role": role,
                },
            )
            db.add(file_record)
            await db.flush()
            storage_path = get_file_path(str(file_record.id), filename)
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            storage_path.write_bytes(content)
            file_record.storage_path = str(storage_path)
            await db.flush()
            file_ids.append(str(file_record.id))
            files_by_role[str(role)] = str(file_record.id)
        remote_inputs[str(input_name)] = {
            "type": artifact_example.type,
            "metadata": dict(artifact_example.metadata or {}),
            "files": files_by_role,
        }
    return file_ids, remote_inputs


async def _load_remote_example_file(base_url: str, file_example: dict[str, Any]) -> bytes:
    content = file_example.get("content")
    encoding = file_example.get("encoding")
    if isinstance(content, str):
        if encoding == "base64":
            return base64.b64decode(content)
        if encoding in {"text", None}:
            return content.encode("utf-8")
        raise ValidationException("smoke example file encoding must be base64 or text")

    url = file_example.get("url")
    if isinstance(url, str) and url.strip():
        fetch_url = url if url.startswith(("http://", "https://")) else urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(fetch_url)
            response.raise_for_status()
            return response.content
    raise ValidationException("smoke example file must include url or content")


def _select_remote_smoke_example(
    discovery: RemoteToolDiscoveryResult,
) -> RemoteToolExample | None:
    examples = []
    if discovery.examples is not None:
        examples.extend(discovery.examples.examples)
    if discovery.manifest is not None:
        examples.extend(discovery.manifest.examples)
    if not examples:
        return None
    return next((example for example in examples if example.smoke), examples[0])
