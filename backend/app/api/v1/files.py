# backend/app/api/v1/files.py
"""文件管理API（本地存储版本）"""

import os
import hashlib
import aiofiles
import re
import tempfile
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
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
    validate_remote_file_access_token,
)
from app.files.storage_path import STORAGE_PATH, ensure_storage_dir, get_file_path
from app.services.artifact_file_list import list_user_artifact_files

router = APIRouter()

UPLOAD_CHUNK_SIZE = 1024 * 1024
UPLOAD_SIGNATURE_BYTES = 16
_ALLOWED_UPLOAD_EXTENSIONS = {
    ".bz2", ".cif", ".csv", ".dat", ".fa", ".faa", ".fasta", ".fastq", ".fna",
    ".fq", ".gz", ".jpeg", ".jpg", ".json", ".log", ".mol", ".mol2", ".mmcif",
    ".out", ".pdb", ".pdbqt", ".pdf", ".png", ".sdf", ".smi", ".smiles", ".tar",
    ".tgz", ".tsv", ".txt", ".xml", ".xyz", ".xz", ".yaml", ".yml", ".zip",
}
_EXPECTED_FILE_SIGNATURES = {
    ".bz2": (b"BZh",),
    ".gz": (b"\x1f\x8b",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".jpg": (b"\xff\xd8\xff",),
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".xz": (b"\xfd7zXZ\x00",),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}
_EXECUTABLE_SIGNATURES = (b"\x7fELF", b"MZ", b"#!", b"\xfe\xed\xfa\xce", b"\xcf\xfa\xed\xfe")


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


async def _stream_upload_to_staging(
    file: UploadFile,
    *,
    max_size: int,
) -> tuple[Path, int, str, bytes]:
    """分块暂存上传文件，并在单次读取中计算大小与 SHA-256。"""
    STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix=".upload-", dir=STORAGE_PATH)
    os.close(descriptor)
    staged_path = Path(raw_path)
    sha256_hash = hashlib.sha256()
    file_size = 0
    header = bytearray()

    try:
        await file.seek(0)
        async with aiofiles.open(staged_path, "wb") as staged_file:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > max_size:
                    raise ValidationException(f"文件大小超过限制 ({settings.MAX_FILE_SIZE_MB}MB)")
                sha256_hash.update(chunk)
                if len(header) < UPLOAD_SIGNATURE_BYTES:
                    header.extend(chunk[: UPLOAD_SIGNATURE_BYTES - len(header)])
                await staged_file.write(chunk)
        await file.seek(0)
        return staged_path, file_size, sha256_hash.hexdigest(), bytes(header)
    except Exception:
        staged_path.unlink(missing_ok=True)
        raise


def _validate_upload_content(filename: str, header: bytes) -> None:
    """校验上传扩展名与可识别二进制文件头。"""
    extension = Path(filename).suffix.lower()
    if extension not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationException(f"不支持的上传文件类型: {extension or '无扩展名'}")

    if any(header.startswith(signature) for signature in _EXECUTABLE_SIGNATURES):
        raise ValidationException("禁止上传可执行文件")

    expected_signatures = _EXPECTED_FILE_SIGNATURES.get(extension)
    if expected_signatures and not any(header.startswith(signature) for signature in expected_signatures):
        raise ValidationException("文件内容与扩展名不匹配")


async def calculate_sha256(file: UploadFile) -> str:
    """计算文件SHA256哈希"""
    sha256_hash = hashlib.sha256()
    await file.seek(0)
    while chunk := await file.read(8192):
        sha256_hash.update(chunk)
    await file.seek(0)
    return sha256_hash.hexdigest()


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
    ensure_storage_dir()
    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    filename = Path(file.filename or "upload").name
    staged_path, file_size, sha256, header = await _stream_upload_to_staging(
        file,
        max_size=max_size,
    )

    try:
        _validate_upload_content(filename, header)

        result = await db.execute(
            select(FileModel).where(
                FileModel.sha256 == sha256,
                FileModel.owner_id == current_user.id
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
        file_record = FileModel(
            filename=filename,
            content_type=file.content_type,
            size_bytes=file_size,
            sha256=sha256,
            source_type=FileSourceType.UPLOAD,
            is_public=is_public,
            expires_at=expires_at,
            owner_id=current_user.id
        )

        db.add(file_record)
        await db.flush()

        file_path = get_file_path(file_record.id, filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged_path, file_path)
        file_record.storage_path = str(file_path)

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

    # 排除已过期文件
    query = query.where(
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
    ensure_storage_dir()

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
    file_id = str(uuid.uuid4())
    file_path = get_file_path(file_id, output_filename)

    file_record = FileModel(
        id=file_id,
        filename=output_filename,
        content_type="chemical/x-pdb",
        size_bytes=len(output_content),
        sha256=sha256,
        storage_path=str(file_path),
        source_type=FileSourceType.UPLOAD.value,
        is_public=False,
        owner_id=current_user.id,
        file_meta={
            "original_name": output_filename,
            "converted_from": file.filename,
            "conversion": "sdf-to-pdb",
            "converter": converter,
        },
    )
    db.add(file_record)

    file_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(file_path, "wb") as converted_file:
        await converted_file.write(output_content)

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
    if not file.is_public and file.owner_id != current_user.id:
        is_admin = current_user.role == "admin"
        if not is_admin:
            raise ForbiddenException("无权访问此文件")

    # 检查是否过期
    if file.expires_at and file.expires_at < utcnow():
        raise NotFoundException("文件已过期")

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
        if file.owner_id != current_user.id and current_user.role != "admin":
            _audit_file_download_denied(
                file=file,
                current_user=current_user,
                remote_token=False,
                reason="forbidden",
            )
            raise ForbiddenException("无权下载此文件")

    # 检查是否过期
    if file.expires_at and file.expires_at < utcnow():
        _audit_file_download_denied(
            file=file,
            current_user=current_user,
            remote_token=remote_token_claims is not None,
            reason="expired",
        )
        raise NotFoundException("文件已过期")

    # 检查文件是否存在
    file_path = Path(file.storage_path) if file.storage_path else get_file_path(file.id, file.filename)
    if not file_path.exists():
        raise NotFoundException("文件已被删除")

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

    return FileResponse(
        path=str(file_path),
        filename=file.filename,
        media_type=file.content_type
    )


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
    if not file.is_public and file.owner_id != current_user.id:
        is_admin = current_user.role == "admin"
        if not is_admin:
            raise ForbiddenException("无权访问此文件")

    # 对于本地存储，直接返回下载API路径
    download_url = f"/api/v1/files/{file_id}/download"

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
    is_admin = current_user.role == "admin"
    if file.owner_id != current_user.id and not is_admin:
        raise ForbiddenException("无权删除此文件")

    # 删除本地文件
    file_path = Path(file.storage_path) if file.storage_path else get_file_path(file.id, file.filename)
    if file_path.exists():
        os.remove(file_path)

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
        is_admin = current_user.role == "admin"
        if file.owner_id != current_user.id and not is_admin:
            failed_ids.append(file_id)
            continue

        # 删除本地文件
        file_path = Path(file.storage_path) if file.storage_path else get_file_path(file.id, file.filename)
        if file_path.exists():
            os.remove(file_path)

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
