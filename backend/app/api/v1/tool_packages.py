"""Administrator API for validated and signed Tool Packages."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_admin_user
from app.common.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.models.tool_packages import ToolPackage, ToolPackageVersion
from app.models.users import User
from app.schemas.tool_packages import (
    ToolPackageCreate,
    ToolPackageKubernetesRegistrationCreate,
    ToolPackageValidate,
)
from app.tool_packages.digests import tool_package_manifest_digest
from app.tool_packages.kubernetes_registration import (
    get_kubernetes_registration_options,
    register_kubernetes_tool_version,
)
from app.tool_packages.validator import validate_tool_package


router = APIRouter(
    dependencies=[Depends(require_feature_flag("TOOL_PACKAGE_V1_ENABLED"))]
)


@router.post("", response_model=dict)
async def create_tool_package(
    request: ToolPackageCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    manifest = request.manifest
    validation = validate_tool_package(manifest)
    if not validation.is_valid:
        raise ValidationException(
            "；".join(validation.errors), detail=validation.errors
        )
    duplicate = await db.execute(
        select(ToolPackage.id).where(ToolPackage.slug == manifest.metadata.slug)
    )
    if duplicate.scalar_one_or_none():
        raise ConflictException("Tool Package 标识已存在")

    package = ToolPackage(
        owner_id=current_user.id,
        slug=manifest.metadata.slug,
        name=manifest.metadata.name,
        description=manifest.metadata.description,
        status="draft",
    )
    db.add(package)
    await db.flush()
    manifest_data = manifest.model_dump(mode="json")
    version = ToolPackageVersion(
        package_id=package.id,
        version=manifest.metadata.version,
        manifest=manifest_data,
        manifest_digest=tool_package_manifest_digest(manifest_data),
        signature=request.signature,
        is_signed=bool(request.signature),
        validation_status="valid",
        validation_errors=[],
    )
    db.add(version)
    await db.flush()
    package.current_version_id = version.id
    await db.commit()
    return success_response(
        data=_serialize_package(await _load_package(db, package.id))
    )


@router.get("", response_model=dict)
async def list_tool_packages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    base_query = select(ToolPackage)
    total = await db.scalar(select(func.count()).select_from(base_query.subquery()))
    result = await db.execute(
        base_query
        .options(selectinload(ToolPackage.current_version))
        .order_by(ToolPackage.created_at.desc(), ToolPackage.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return paginated_response(
        items=[_serialize_package(package) for package in result.scalars().all()],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.post("/validate", response_model=dict)
async def validate_tool_package_manifest(
    request: ToolPackageValidate,
    current_user: User = Depends(get_admin_user),
):
    validation = validate_tool_package(request.manifest)
    return success_response(
        data={"isValid": validation.is_valid, "errors": validation.errors}
    )


@router.get("/{package_id}", response_model=dict)
async def get_tool_package(
    package_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return success_response(
        data=_serialize_package(await _load_package(db, package_id))
    )


@router.post("/{package_id}/publish", response_model=dict)
async def publish_tool_package(
    package_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    package = await _load_package(db, package_id)
    version = package.current_version
    if version is None or version.validation_status != "valid":
        raise ValidationException("Tool Package 当前版本未通过契约校验")
    if not version.is_signed or not version.signature:
        raise ValidationException("Tool Package 当前版本缺少签名，不能发布")
    package.status = "published"
    await db.commit()
    return success_response(
        data=_serialize_package(package), message="Tool Package 发布成功"
    )


@router.get("/{package_id}/kubernetes-options", response_model=dict)
async def get_tool_package_kubernetes_options(
    package_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return success_response(
        data=await get_kubernetes_registration_options(db, package_id)
    )


@router.post("/{package_id}/kubernetes-registrations", response_model=dict)
async def register_tool_package_as_kubernetes_tool(
    package_id: str,
    request: ToolPackageKubernetesRegistrationCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await register_kubernetes_tool_version(
        db,
        package_id=package_id,
        request=request,
        current_user=current_user,
    )
    return success_response(data=result, message="Kubernetes 候选工具版本已注册")


async def _load_package(db: AsyncSession, package_id: str) -> ToolPackage:
    package = (
        await db.execute(
            select(ToolPackage)
            .options(selectinload(ToolPackage.current_version))
            .where(ToolPackage.id == package_id)
        )
    ).scalar_one_or_none()
    if package is None:
        raise NotFoundException("Tool Package 不存在")
    return package


def _serialize_package(package: ToolPackage) -> dict[str, Any]:
    version = package.current_version
    return {
        "id": package.id,
        "slug": package.slug,
        "name": package.name,
        "description": package.description,
        "status": package.status,
        "owner_id": package.owner_id,
        "current_version": (
            None
            if version is None
            else {
                "id": version.id,
                "version": version.version,
                "manifest": version.manifest,
                "manifest_digest": version.manifest_digest,
                "signature": version.signature,
                "is_signed": version.is_signed,
                "validation_status": version.validation_status,
                "validation_errors": list(version.validation_errors or []),
            }
        ),
        "created_at": package.created_at.isoformat(),
        "updated_at": package.updated_at.isoformat(),
    }
