"""Administrator registration of published Tool Packages for Kubernetes."""

from __future__ import annotations

import hmac
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.tool_route_utils import (
    load_tool_for_response,
    require_active_tool_category,
    serialize_tool,
    serialize_tool_version,
)
from app.common.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.tasks import Task
from app.models.tools import (
    Tool,
    ToolProviderType,
    ToolReviewStatus,
    ToolStatus,
    ToolVersion,
)
from app.models.tool_packages import ToolPackage, ToolPackageVersion
from app.models.users import User
from app.schemas.tool_packages import ToolPackageKubernetesRegistrationCreate
from app.tasks.resource_profile import list_registered_resource_profile_ids
from app.tool_packages.digests import tool_package_manifest_digest
from app.tool_packages.kubernetes_binding import (
    KubernetesToolBindingError,
    build_kubernetes_tool_config,
)
from app.tool_packages.schemas import AnyToolPackageManifest, ToolPackageV2Manifest
from app.tool_packages.validator import validate_tool_package


_MANIFEST_ADAPTER = TypeAdapter(AnyToolPackageManifest)


async def get_kubernetes_registration_options(
    db: AsyncSession,
    package_id: str,
) -> dict[str, Any]:
    package, version, manifest = await _load_published_v2_package(db, package_id)
    profiles = _resource_profile_ids()
    primary = manifest.runtime.artifacts.primary
    kubernetes_supported = "k8s_job" in manifest.runtime.executor_support
    existing_tool = (
        await db.execute(
            select(Tool)
            .options(selectinload(Tool.current_version))
            .where(Tool.slug == package.slug)
        )
    ).scalar_one_or_none()
    tool_versions = []
    if existing_tool is not None:
        tool_versions = (
            await db.execute(
                select(ToolVersion)
                .where(ToolVersion.tool_id == existing_tool.id)
                .order_by(ToolVersion.created_at.desc(), ToolVersion.id.desc())
            )
        ).scalars().all()
    kubernetes_versions = [
        item
        for item in tool_versions
        if (item.config or {}).get("type") == "k8s_job"
    ]
    latest_smoke_by_version = {}
    if kubernetes_versions:
        smoke_tasks = (
            await db.execute(
                select(Task)
                .where(
                    Task.tool_id == existing_tool.id,
                    Task.tool_version_id.in_([item.id for item in kubernetes_versions]),
                    Task.extra_data["run_kind"].as_string() == "tool_version_smoke",
                )
                .order_by(Task.created_at.desc(), Task.id.desc())
            )
        ).scalars().all()
        for task in smoke_tasks:
            latest_smoke_by_version.setdefault(task.tool_version_id, task)

    return {
        "package_id": package.id,
        "package_version_id": version.id,
        "package_version": version.version,
        "manifest_digest": version.manifest_digest,
        "kubernetes_supported": kubernetes_supported,
        "image": primary.image,
        "image_digest": primary.image_digest,
        "variants": [
            {
                "name": variant.name,
                "accelerator": variant.accelerator.value,
                "entrypoint": list(variant.entrypoint),
                "resources": variant.resources.model_dump(mode="json"),
            }
            for variant in manifest.variants
        ] if kubernetes_supported else [],
        "resource_profiles": profiles,
        "tool_versions": [
            _serialize_tool_version_summary(item, latest_smoke_by_version.get(item.id))
            for item in tool_versions
        ],
        "existing_tool": (
            None
            if existing_tool is None
            else {
                "id": existing_tool.id,
                "name": existing_tool.name,
                "slug": existing_tool.slug,
                "status": existing_tool.status,
                "current_version_id": existing_tool.current_version_id,
                "current_version_type": (
                    (existing_tool.current_version.config or {}).get("type")
                    if existing_tool.current_version is not None
                    else None
                ),
            }
        ),
    }


def _serialize_tool_version_summary(
    version: ToolVersion,
    latest_smoke: Task | None,
) -> dict[str, Any]:
    return {
        "id": version.id,
        "version": version.version,
        "executor_type": (version.config or {}).get("type"),
        "is_active": version.is_active,
        "deprecated": version.deprecated,
        "smoke_status": latest_smoke.status if latest_smoke is not None else None,
        "smoke_task_id": latest_smoke.id if latest_smoke is not None else None,
        "smoke_created_at": (
            latest_smoke.created_at.isoformat() if latest_smoke is not None else None
        ),
    }


async def register_kubernetes_tool_version(
    db: AsyncSession,
    *,
    package_id: str,
    request: ToolPackageKubernetesRegistrationCreate,
    current_user: User,
) -> dict[str, Any]:
    package, package_version, manifest = await _load_published_v2_package(
        db,
        package_id,
        package_version_id=request.package_version_id,
    )
    _ensure_resource_profile_is_registered(request.resource_profile)

    if request.target_tool_id:
        tool = (
            await db.execute(
                select(Tool)
                .options(selectinload(Tool.current_version))
                .where(Tool.id == request.target_tool_id)
            )
        ).scalar_one_or_none()
        if tool is None:
            raise NotFoundException("目标平台工具不存在")
        if tool.slug != package.slug:
            raise ValidationException("目标平台工具标识必须与 Tool Package 标识一致")
    else:
        existing = await db.scalar(select(Tool.id).where(Tool.slug == package.slug))
        if existing:
            raise ConflictException("同标识平台工具已存在，请选择该工具添加候选版本")
        if not request.category_id:
            raise ValidationException("创建新平台工具时必须选择工具分类")
        category = await require_active_tool_category(db, request.category_id)
        tool = Tool(
            owner_id=current_user.id,
            name=package.name,
            slug=package.slug,
            description=package.description,
            category_id=category.id,
            category=category.name,
            status=ToolStatus.DRAFT.value,
            provider_type=ToolProviderType.PLATFORM.value,
            review_status=ToolReviewStatus.NOT_REQUIRED.value,
        )
        db.add(tool)
        await db.flush()

    duplicate_version = await db.scalar(
        select(ToolVersion.id).where(
            ToolVersion.tool_id == tool.id,
            ToolVersion.version == request.tool_version,
        )
    )
    if duplicate_version:
        raise ConflictException("平台工具版本号已存在")

    try:
        config = build_kubernetes_tool_config(
            manifest,
            variant_name=request.variant_name,
            resource_profile=request.resource_profile,
        )
    except KubernetesToolBindingError as exc:
        raise ValidationException(str(exc)) from exc

    config["tool_package_manifest"] = package_version.manifest
    config["tool_package_source"] = {
        "package_id": package.id,
        "package_version_id": package_version.id,
        "manifest_digest": package_version.manifest_digest,
    }
    version = ToolVersion(
        tool_id=tool.id,
        version=request.tool_version,
        changelog=f"Registered from Tool Package {package.slug}@{package_version.version}",
        config=config,
        is_active=False,
    )
    db.add(version)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException("工具或工具版本发生冲突，请刷新后重试") from exc

    await db.refresh(version)
    tool_data = serialize_tool(await load_tool_for_response(db, tool.id))
    return {
        "registration_status": "candidate",
        "tool": tool_data,
        "version": serialize_tool_version(version),
    }


async def _load_published_v2_package(
    db: AsyncSession,
    package_id: str,
    *,
    package_version_id: str | None = None,
) -> tuple[ToolPackage, ToolPackageVersion, ToolPackageV2Manifest]:
    package = (
        await db.execute(
            select(ToolPackage)
            .options(selectinload(ToolPackage.current_version))
            .where(ToolPackage.id == package_id)
        )
    ).scalar_one_or_none()
    if package is None:
        raise NotFoundException("Tool Package 不存在")
    if package.status != "published":
        raise ValidationException("只能注册已发布的 Tool Package")

    selected_version_id = package_version_id or package.current_version_id
    package_version = (
        await db.execute(
            select(ToolPackageVersion).where(
                ToolPackageVersion.id == selected_version_id,
                ToolPackageVersion.package_id == package.id,
            )
        )
    ).scalar_one_or_none()
    if package_version is None:
        raise NotFoundException("Tool Package 版本不存在")
    if package.current_version_id != package_version.id:
        raise ValidationException("只能注册 Tool Package 当前发布版本")
    if package_version.validation_status != "valid":
        raise ValidationException("Tool Package 版本未通过契约校验")
    if not package_version.is_signed or not package_version.signature:
        raise ValidationException("Tool Package 版本缺少签名，不能注册")
    if not hmac.compare_digest(
        package_version.manifest_digest,
        tool_package_manifest_digest(package_version.manifest),
    ):
        raise ValidationException("Tool Package manifest digest 不匹配")

    try:
        manifest = _MANIFEST_ADAPTER.validate_python(package_version.manifest)
    except ValidationError as exc:
        raise ValidationException("Tool Package manifest 格式无效") from exc
    if not isinstance(manifest, ToolPackageV2Manifest):
        raise ValidationException("Kubernetes 注册仅支持 Tool Package v2")
    validation = validate_tool_package(manifest)
    if not validation.is_valid:
        raise ValidationException(
            "Tool Package manifest 校验失败",
            detail=validation.errors,
        )
    return package, package_version, manifest


def _resource_profile_ids() -> list[str]:
    try:
        return list_registered_resource_profile_ids()
    except ValueError as exc:
        raise ValidationException(str(exc)) from exc


def _ensure_resource_profile_is_registered(profile_id: str) -> None:
    if profile_id not in _resource_profile_ids():
        raise ValidationException(f"未登记的资源档位: {profile_id}")
