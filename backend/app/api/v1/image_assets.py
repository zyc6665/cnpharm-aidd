"""管理员镜像资产导入与 ToolVersion 绑定接口。"""

import hashlib
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_admin_user
from app.common.exceptions import NotFoundException, ValidationException
from app.common.responses import success_response
from app.config import settings
from app.database.session import get_db
from app.models.image_assets import ImageAsset, ImageImport, ImageImportStatus
from app.models.tools import ToolVersion
from app.models.users import User
from app.schemas.image_assets import ImageAssetBindingRequest, ImageAssetResponse
from app.services.image_asset_import import ImageArchiveError, import_image_archive
from app.tasks.resource_profile import resolve_registered_resource_profile


router = APIRouter()


def _serialize(asset: ImageAsset) -> dict:
    return ImageAssetResponse.model_validate(asset).model_dump()


@router.post("", response_model=dict)
async def import_image_asset(
    archive: UploadFile = File(...),
    repository: str = Form(...),
    tag: str = Form(...),
    expected_archive_sha256: str | None = Form(None),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员上传 Docker save 或 OCI 归档并导入内部 Registry。"""
    max_size = settings.IMAGE_IMPORT_MAX_SIZE_MB * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(prefix="sciminer-image-", suffix=".tar", delete=False) as staged:
        staged_path = Path(staged.name)
        try:
            while chunk := await archive.read(1024 * 1024):
                size += len(chunk)
                if size > max_size:
                    raise ValidationException("镜像归档超过平台大小限制")
                digest.update(chunk)
                staged.write(chunk)
        finally:
            await archive.close()
    archive_sha256 = digest.hexdigest()
    if expected_archive_sha256 and expected_archive_sha256.removeprefix("sha256:") != archive_sha256:
        staged_path.unlink(missing_ok=True)
        raise ValidationException("镜像归档 SHA-256 校验失败")

    image_import = ImageImport(
        owner_id=current_user.id,
        filename=archive.filename or "image.tar",
        size_bytes=size,
        archive_sha256=archive_sha256,
        requested_repository=repository,
        requested_tag=tag,
        status=ImageImportStatus.PENDING.value,
    )
    db.add(image_import)
    await db.flush()

    try:
        imported = await import_image_archive(
            staged_path,
            repository=repository,
            tag=tag,
            archive_sha256=archive_sha256,
            archive_size_bytes=size,
        )
    except ImageArchiveError as exc:
        image_import.status = ImageImportStatus.FAILED.value
        image_import.error_message = str(exc)
        await db.commit()
        staged_path.unlink(missing_ok=True)
        raise ValidationException(str(exc)) from exc
    finally:
        staged_path.unlink(missing_ok=True)

    image_import.status = ImageImportStatus.SUCCEEDED.value
    asset = ImageAsset(
        import_id=image_import.id,
        created_by=current_user.id,
        status="ready",
        **imported,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return success_response(data=_serialize(asset), message="镜像导入成功")


@router.get("", response_model=dict)
async def list_image_assets(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    assets = (
        await db.execute(select(ImageAsset).order_by(ImageAsset.created_at.desc()))
    ).scalars().all()
    return success_response(data=[_serialize(asset) for asset in assets])


@router.get("/{asset_id}", response_model=dict)
async def get_image_asset(
    asset_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(ImageAsset, asset_id)
    if asset is None:
        raise NotFoundException("镜像资产不存在")
    return success_response(data=_serialize(asset))


@router.post("/{asset_id}/bind-tool-version", response_model=dict)
async def bind_image_asset(
    asset_id: str,
    binding: ImageAssetBindingRequest,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(ImageAsset, asset_id)
    if asset is None:
        raise NotFoundException("镜像资产不存在")
    if asset.status != "ready" or not re.fullmatch(r"sha256:[0-9a-f]{64}", asset.manifest_digest):
        raise ValidationException("镜像资产尚未处于可绑定状态")
    tool_version = await db.get(ToolVersion, binding.tool_version_id)
    if tool_version is None:
        raise NotFoundException("工具版本不存在")
    try:
        resolve_registered_resource_profile(binding.resource_profile)
    except ValueError as exc:
        raise ValidationException(str(exc)) from exc
    old_config = dict(tool_version.config or {})
    old_runtime = dict(old_config.get("runtime") or {})
    old_config["type"] = "k8s_job"
    old_config["runtime"] = {
        **old_runtime,
        "image": asset.image_reference,
        "entrypoint": binding.entrypoint,
        "args": binding.args,
    }
    old_config["resource_profile"] = binding.resource_profile
    old_config["image_asset_id"] = asset.id
    tool_version.config = old_config
    await db.commit()
    await db.refresh(tool_version)
    return success_response(data={"tool_version_id": tool_version.id, "config": tool_version.config}, message="镜像已绑定工具版本")
