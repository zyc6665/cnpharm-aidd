# backend/app/api/v1/files.py
"""文件管理API（本地存储版本）"""

import hashlib
import re
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, or_
from sqlalchemy.orm import joinedload
from typing import Optional, List
from datetime import timedelta

from app.common.time import utcnow
from app.database.session import get_db
from app.models.users import User
from app.models.files import File as FileModel, FileSourceType
from app.auth.dependencies import get_current_user, get_current_user_optional
from app.schemas.files import (
    FileResponse as FileSchema,
    FileUploadResponse,
    FileDownloadUrl,
)
from app.common.responses import paginated_response, success_response
from app.common.exceptions import NotFoundException, ForbiddenException, ValidationException
from app.chemistry.conversion import convert_sdf_to_pdb_with_toolkit as _convert_sdf_to_pdb_with_toolkit
from app.config import settings
from app.logging.audit import AuditAction, AuditResult, get_audit_logger
from app.files.remote_access_tokens import (
    RemoteFileAccessTokenError,
    create_browser_file_access_token,
    validate_browser_file_access_token,
    validate_remote_file_access_token,
)
from app.files.file_records import (
    delete_stored_content,
    file_storage_path,
    is_file_usable,
    user_can_access_file,
    user_can_manage_file,
)
from app.files.upload_staging import stream_upload, validate_upload_content
from app.files.writer import store_file_bytes, store_file_path
from app.services.artifact_file_list import list_user_artifact_files
from app.storage.factory import get_storage_backend

router = APIRouter()


def _audit_file_download(
    *,
    file: FileModel,
    current_user: Optional[User],
    remote_token_claims: Optional[dict],
) -> None:
    actor_id = current_user.id if current_user else "remote-token"
    get_audit_logger().log_file_operation(
        user_id=actor_id,
        action=AuditAction.FILE_DOWNLOAD,
        file_id=file.id,
        file_name=file.filename,
        result=AuditResult.SUCCESS,
        file_size=file.size_bytes,
        project_id=file.project_id,
        remote_token=remote_token_claims is not None,
    )


def _audit_file_download_denied(
    *,
    file: FileModel,
    current_user: Optional[User],
    remote_token: bool,
    reason: str,
) -> None:
    actor_id = current_user.id if current_user else "anonymous"
    get_audit_logger().log_file_operation(
        user_id=actor_id,
        action=AuditAction.FILE_DOWNLOAD,
        file_id=file.id,
        file_name=file.filename,
        result=AuditResult.DENIED,
        file_size=file.size_bytes,
        project_id=file.project_id,
        remote_token=remote_token,
        reason=reason,
    )


def _safe_converted_pdb_filename(filename: str | None) -> str:
    """根据上传文件名生成安全的 PDB 文件名。"""
    raw_name = Path(filename or "ligand.sdf").name
    stem = Path(raw_name).stem or "ligand"
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "ligand"
    return f"{safe_stem}.pdb"


@router.post("/upload", response_model=dict)
async def upload_file(
    file: UploadFile = File(...),
    is_public: bool = False,
    expires_hours: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """上传文件"""
    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    filename = Path(file.filename or "upload").name
    staged_path, file_size, sha256, header = await stream_upload(
        file,
        max_size=max_size,
    )

    try:
        validate_upload_content(filename, header)

        result = await db.execute(
            select(FileModel).where(
                FileModel.sha256 == sha256,
                FileModel.owner_id == current_user.id,
                FileModel.deleted_at.is_(None),
                or_(FileModel.is_corrupted.is_(False), FileModel.is_corrupted.is_(None)),
                (FileModel.expires_at.is_(None)) |
                (FileModel.expires_at > utcnow()),
            ).order_by(
                case(
                    (FileModel.source_type == FileSourceType.UPLOAD.value, 0),
                    else_=1,
                ),
                FileModel.created_at.desc(),
                FileModel.updated_at.desc(),
                FileModel.id.desc(),
            ).limit(1)
        )
        existing_file = result.scalar_one_or_none()

        if existing_file:
            return success_response(
                data=FileUploadResponse(
                    id=existing_file.id,
                    filename=existing_file.filename,
                    size_bytes=existing_file.size_bytes,
                    content_type=existing_file.content_type,
                    sha256=existing_file.sha256
                ).model_dump(),
                message="文件已存在（去重）"
            )

        expires_at = utcnow() + timedelta(hours=expires_hours) if expires_hours else None
        file_record = await store_file_path(
            db,
            source_path=staged_path,
            filename=filename,
            content_type=file.content_type,
            source_type=FileSourceType.UPLOAD,
            owner_id=current_user.id,
            size_bytes=file_size,
            sha256=sha256,
            is_public=is_public,
            expires_at=expires_at,
        )

        await db.commit()
        await db.refresh(file_record)

        return success_response(
            data=FileUploadResponse(
                id=file_record.id,
                filename=file_record.filename,
                size_bytes=file_record.size_bytes,
                content_type=file_record.content_type,
                sha256=file_record.sha256
            ).model_dump(),
            message="上传成功"
        )
    finally:
        staged_path.unlink(missing_ok=True)


@router.get("", response_model=dict)
async def list_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取文件列表"""
    query = select(FileModel).options(
        joinedload(FileModel.statistics)
    ).where(FileModel.owner_id == current_user.id)

    if source_type:
        query = query.where(FileModel.source_type == source_type)

    # 仅展示仍可使用的文件
    query = query.where(
        FileModel.deleted_at.is_(None),
        or_(FileModel.is_corrupted.is_(False), FileModel.is_corrupted.is_(None)),
        (FileModel.expires_at.is_(None)) |
        (FileModel.expires_at > utcnow())
    )

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(FileModel.created_at.desc())

    result = await db.execute(query)
    files = result.scalars().all()

    return paginated_response(
        items=[FileSchema.model_validate(f).model_dump() for f in files],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/artifacts", response_model=dict)
async def list_artifact_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户可复用的工具输出文件。"""
    result = await list_user_artifact_files(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        search=search,
    )
    return paginated_response(
        items=result.items,
        total=result.total,
        page=page,
        page_size=page_size,
    )


@router.post("/convert/sdf-to-pdb", response_model=dict)
async def convert_sdf_to_pdb(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传 SDF 并转换为 ligand PDB 文件。"""
    file_content = await file.read()
    file_size = len(file_content)
    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_size:
        raise ValidationException(f"文件大小超过限制 ({settings.MAX_FILE_SIZE_MB}MB)")

    lower_name = (file.filename or "").lower()
    lower_type = (file.content_type or "").lower()
    if not lower_name.endswith(".sdf") and lower_type not in {
        "chemical/x-mdl-sdfile",
        "chemical/x-sdf",
        "application/sdf",
        "application/octet-stream",
    }:
        raise ValidationException("请上传 SDF 文件")

    pdb_text, converter = _convert_sdf_to_pdb_with_toolkit(file_content)
    output_filename = _safe_converted_pdb_filename(file.filename)
    output_content = pdb_text.encode("utf-8")
    sha256 = hashlib.sha256(output_content).hexdigest()
    file_record = await store_file_bytes(
        db,
        content=output_content,
        filename=output_filename,
        content_type="chemical/x-pdb",
        source_type=FileSourceType.UPLOAD,
        owner_id=current_user.id,
        sha256=sha256,
        file_meta={
            "original_name": output_filename,
            "converted_from": file.filename,
            "conversion": "sdf-to-pdb",
            "converter": converter,
        },
    )

    await db.commit()
    await db.refresh(file_record)

    return success_response(
        data=FileUploadResponse(
            id=file_record.id,
            filename=file_record.filename,
            size_bytes=file_record.size_bytes,
            content_type=file_record.content_type,
            sha256=file_record.sha256,
        ).model_dump(),
        message="SDF 已转换为 PDB"
    )


@router.get("/{file_id}", response_model=dict)
async def get_file_info(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取文件信息"""
    result = await db.execute(
        select(FileModel).options(
            joinedload(FileModel.statistics)
        ).where(FileModel.id == file_id)
    )
    file = result.scalar_one_or_none()

    if not file:
        raise NotFoundException("文件不存在")

    # 权限检查
    if not user_can_access_file(file, current_user):
        raise ForbiddenException("无权访问此文件")

    if not is_file_usable(file):
        raise NotFoundException("文件不存在")

    return success_response(data=FileSchema.model_validate(file).model_dump())


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    token: Optional[str] = Query(default=None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """下载文件（公开文件支持匿名访问）"""
    result = await db.execute(
        select(FileModel).options(
            joinedload(FileModel.statistics)
        ).where(FileModel.id == file_id)
    )
    file = result.scalar_one_or_none()

    if not file:
        raise NotFoundException("文件不存在")

    remote_token_claims = None
    if token:
        try:
            remote_token_claims = validate_remote_file_access_token(token, file_id=file_id)
        except RemoteFileAccessTokenError:
            try:
                remote_token_claims = validate_browser_file_access_token(token, file_id=file_id)
            except RemoteFileAccessTokenError as exc:
                _audit_file_download_denied(
                    file=file,
                    current_user=current_user,
                    remote_token=True,
                    reason="invalid_remote_token",
                )
                raise ForbiddenException(str(exc)) from exc

    # 权限检查：公开文件允许匿名访问
    if not file.is_public and remote_token_claims is None:
        if not current_user:
            _audit_file_download_denied(
                file=file,
                current_user=None,
                remote_token=False,
                reason="authentication_required",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="需要登录才能访问此文件"
            )
        if not user_can_access_file(file, current_user):
            _audit_file_download_denied(
                file=file,
                current_user=current_user,
                remote_token=False,
                reason="forbidden",
            )
            raise ForbiddenException("无权下载此文件")

    if not is_file_usable(file):
        _audit_file_download_denied(
            file=file,
            current_user=current_user,
            remote_token=remote_token_claims is not None,
            reason="unusable",
        )
        raise NotFoundException("文件不存在")

    if file.storage_backend == "minio":
        storage = get_storage_backend("minio")
        if not await storage.exists(file.storage_path):
            raise NotFoundException("文件已被删除")
        content = await storage.download(file.storage_path)
        response = Response(
            content=content,
            media_type=file.content_type,
            headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
        )
    else:
        file_path = file_storage_path(file)
        if not file_path.exists():
            raise NotFoundException("文件已被删除")
        response = FileResponse(
            path=str(file_path),
            filename=file.filename,
            media_type=file.content_type,
        )

    # 更新下载计数（通过statistics表）
    if not file.statistics:
        from app.models.statistics import FileStatistics
        file.statistics = FileStatistics(file_id=file.id)
        db.add(file.statistics)
    # 处理None值
    if file.statistics.download_count is None:
        file.statistics.download_count = 0
    file.statistics.download_count += 1
    file.statistics.last_downloaded_at = utcnow()
    await db.commit()
    _audit_file_download(
        file=file,
        current_user=current_user,
        remote_token_claims=remote_token_claims,
    )

    return response


@router.get("/{file_id}/download-url", response_model=dict)
async def get_download_url(
    file_id: str,
    expires_in: int = Query(3600, ge=60, le=86400),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取文件下载URL（本地存储直接返回下载接口）"""
    result = await db.execute(
        select(FileModel).options(
            joinedload(FileModel.statistics)
        ).where(FileModel.id == file_id)
    )
    file = result.scalar_one_or_none()

    if not file:
        raise NotFoundException("文件不存在")

    # 权限检查
    if not user_can_access_file(file, current_user):
        raise ForbiddenException("无权访问此文件")
    if not is_file_usable(file):
        raise NotFoundException("文件不存在")

    token = create_browser_file_access_token(
        file_id=file_id,
        user_id=current_user.id,
        expires_in_seconds=expires_in,
    )
    download_url = f"/api/v1/files/{file_id}/download?token={quote(token)}"

    return success_response(
        data=FileDownloadUrl(
            url=download_url,
            expires_in=expires_in
        ).model_dump()
    )


@router.delete("/{file_id}", response_model=dict)
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除文件"""
    result = await db.execute(
        select(FileModel).where(FileModel.id == file_id)
    )
    file = result.scalar_one_or_none()

    if not file:
        raise NotFoundException("文件不存在")

    # 权限检查
    if not user_can_manage_file(file, current_user):
        raise ForbiddenException("无权删除此文件")

    await delete_stored_content(file)

    # 删除数据库记录
    await db.delete(file)
    await db.commit()

    return success_response(message="文件删除成功")


@router.post("/batch-delete", response_model=dict)
async def batch_delete_files(
    file_ids: List[str],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """批量删除文件"""
    deleted_count = 0
    failed_ids = []

    for file_id in file_ids:
        result = await db.execute(
            select(FileModel).where(FileModel.id == file_id)
        )
        file = result.scalar_one_or_none()

        if not file:
            failed_ids.append(file_id)
            continue

        # 权限检查
        if not user_can_manage_file(file, current_user):
            failed_ids.append(file_id)
            continue

        await delete_stored_content(file)

        await db.delete(file)
        deleted_count += 1

    await db.commit()

    return success_response(
        data={
            "deleted_count": deleted_count,
            "failed_ids": failed_ids
        },
        message=f"成功删除 {deleted_count} 个文件"
    )
