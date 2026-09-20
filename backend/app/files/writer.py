"""统一的本地文件写入模块。"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.files.storage_path import ensure_storage_dir, get_file_path, safe_storage_filename
from app.models.files import File as FileModel, FileSourceType


async def store_file_bytes(
    db: AsyncSession,
    *,
    content: bytes,
    filename: str,
    content_type: str | None,
    source_type: str | FileSourceType,
    owner_id: str | None = None,
    project_id: str | None = None,
    file_meta: Mapping[str, Any] | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
    is_public: bool = False,
    is_permanent: bool = False,
    expires_at: datetime | None = None,
) -> FileModel:
    """写入本地文件并创建完整的 File 记录。"""
    safe_filename = safe_storage_filename(filename)
    file_id = str(uuid.uuid4())
    ensure_storage_dir()
    storage_path = get_file_path(file_id, safe_filename)
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        storage_path.write_bytes(content)
        file_record = FileModel(
            id=file_id,
            project_id=project_id,
            owner_id=owner_id,
            filename=safe_filename,
            content_type=content_type,
            size_bytes=len(content) if size_bytes is None else size_bytes,
            sha256=sha256 or hashlib.sha256(content).hexdigest(),
            storage_path=str(storage_path),
            source_type=(
                source_type.value
                if isinstance(source_type, FileSourceType)
                else str(source_type)
            ),
            is_public=is_public,
            is_permanent=is_permanent,
            expires_at=expires_at,
            file_meta=dict(file_meta or {}),
        )
        db.add(file_record)
        await db.flush()
        return file_record
    except Exception:
        storage_path.unlink(missing_ok=True)
        raise


async def store_file_path(
    db: AsyncSession,
    *,
    source_path: Path,
    filename: str,
    content_type: str | None,
    source_type: str | FileSourceType,
    owner_id: str | None = None,
    project_id: str | None = None,
    file_meta: Mapping[str, Any] | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
    is_public: bool = False,
    is_permanent: bool = False,
    expires_at: datetime | None = None,
) -> FileModel:
    """复制一个已存在文件并创建完整的 File 记录。"""
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)

    if size_bytes is None or sha256 is None:
        digest = hashlib.sha256()
        measured_size = 0
        with source.open("rb") as file_handle:
            while chunk := file_handle.read(1024 * 1024):
                measured_size += len(chunk)
                digest.update(chunk)
        size_bytes = measured_size if size_bytes is None else size_bytes
        sha256 = digest.hexdigest() if sha256 is None else sha256

    safe_filename = safe_storage_filename(filename)
    file_id = str(uuid.uuid4())
    ensure_storage_dir()
    storage_path = get_file_path(file_id, safe_filename)
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy2(source, storage_path)
        file_record = FileModel(
            id=file_id,
            project_id=project_id,
            owner_id=owner_id,
            filename=safe_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            storage_path=str(storage_path),
            source_type=(
                source_type.value
                if isinstance(source_type, FileSourceType)
                else str(source_type)
            ),
            is_public=is_public,
            is_permanent=is_permanent,
            expires_at=expires_at,
            file_meta=dict(file_meta or {}),
        )
        db.add(file_record)
        await db.flush()
        return file_record
    except Exception:
        storage_path.unlink(missing_ok=True)
        raise
