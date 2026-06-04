# backend/app/api/v1/files.py
"""文件管理API（本地存储版本）"""

import os
import hashlib
import aiofiles
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, or_
from sqlalchemy.orm import joinedload
from typing import Optional, List
from datetime import datetime, timedelta

from app.database.session import get_db
from app.models.users import User
from app.models.files import File as FileModel, FileSourceType
from app.models.tasks import Task
from app.auth.dependencies import get_current_user, get_admin_user, get_current_user_optional
from app.schemas.files import (
    FileResponse as FileSchema,
    FileUploadResponse,
    FileDownloadUrl,
    ArtifactFileResponse,
)
from app.common.responses import success_response, error_response
from app.common.exceptions import NotFoundException, ForbiddenException, ValidationException
from app.config import settings

router = APIRouter()

# 存储目录
STORAGE_PATH = Path(settings.STORAGE_PATH)


def ensure_storage_dir():
    """确保存储目录存在"""
    STORAGE_PATH.mkdir(parents=True, exist_ok=True)


async def calculate_sha256(file: UploadFile) -> str:
    """计算文件SHA256哈希"""
    sha256_hash = hashlib.sha256()
    await file.seek(0)
    while chunk := await file.read(8192):
        sha256_hash.update(chunk)
    await file.seek(0)
    return sha256_hash.hexdigest()


def get_file_path(file_id: str, filename: str) -> Path:
    """获取文件存储路径"""
    # 使用文件ID的前两位作为子目录，避免单目录文件过多
    subdir = file_id[:2]
    return STORAGE_PATH / subdir / f"{file_id}_{filename}"


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

    # 检查文件大小
    file_content = await file.read()
    file_size = len(file_content)
    await file.seek(0)

    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_size:
        raise ValidationException(f"文件大小超过限制 ({settings.MAX_FILE_SIZE_MB}MB)")

    # 计算SHA256
    sha256 = await calculate_sha256(file)

    # 检查文件是否已存在（去重）
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
        # 返回已存在的文件
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

    # 创建文件记录
    expires_at = None
    if expires_hours:
        expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

    file_record = FileModel(
        filename=file.filename,
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

    # 保存文件到本地
    file_path = get_file_path(file_record.id, file.filename)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(file_path, "wb") as f:
        await file.seek(0)
        content = await file.read()
        await f.write(content)

    # 更新存储路径
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
        (FileModel.expires_at > datetime.utcnow())
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

    return success_response(
        data={
            "items": [FileSchema.model_validate(f).model_dump() for f in files],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
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
    task_result = await db.execute(
        select(Task)
        .options(
            joinedload(Task.tool),
            joinedload(Task.outputs),
        )
        .where(Task.user_id == current_user.id)
        .order_by(Task.created_at.desc(), Task.id.desc())
    )
    tasks = list(task_result.scalars().all())

    artifact_sources: dict[str, tuple[Task, object]] = {}
    for task in tasks:
        if not task.outputs or not task.outputs.file_ids or not task.tool:
            continue
        for file_id in task.outputs.file_ids:
            normalized_file_id = str(file_id)
            artifact_sources.setdefault(normalized_file_id, (task, task.tool))

    if not artifact_sources:
        return success_response(
            data={
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
            }
        )

    query = select(FileModel).where(
        FileModel.id.in_(list(artifact_sources.keys())),
        FileModel.owner_id == current_user.id,
        FileModel.source_type == FileSourceType.TOOL_OUTPUT.value,
        FileModel.deleted_at.is_(None),
        or_(FileModel.expires_at.is_(None), FileModel.expires_at > datetime.utcnow()),
    )

    if search:
        search_pattern = f"%{search}%"
        query = query.where(FileModel.filename.ilike(search_pattern))

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(FileModel.created_at.desc(), FileModel.id.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    files = list(result.scalars().all())

    items = []
    for file_record in files:
        source = artifact_sources.get(file_record.id)
        if not source:
            continue
        task, tool = source
        items.append(
            ArtifactFileResponse(
                id=file_record.id,
                filename=file_record.filename,
                content_type=file_record.content_type,
                size_bytes=file_record.size_bytes,
                source_type=file_record.source_type,
                created_at=file_record.created_at,
                updated_at=file_record.updated_at,
                download_url=f"/api/v1/files/{file_record.id}/download",
                task_id=task.id,
                task_name=task.name,
                tool_id=tool.id,
                tool_name=tool.name,
                tool_slug=tool.slug,
            ).model_dump()
        )

    return success_response(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }
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
    if file.expires_at and file.expires_at < datetime.utcnow():
        raise NotFoundException("文件已过期")

    return success_response(data=FileSchema.model_validate(file).model_dump())


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
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

    # 权限检查：公开文件允许匿名访问
    if not file.is_public:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="需要登录才能访问此文件"
            )
        if file.owner_id != current_user.id and current_user.role != "admin":
            raise ForbiddenException("无权下载此文件")

    # 检查是否过期
    if file.expires_at and file.expires_at < datetime.utcnow():
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
    file.statistics.last_downloaded_at = datetime.utcnow()
    await db.commit()

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
