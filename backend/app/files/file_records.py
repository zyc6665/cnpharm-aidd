"""文件记录的通用路径、权限和删除规则。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import UTC, datetime

from app.common.time import utcnow
from app.files.storage_path import get_file_path


def file_storage_path(file_record: Any) -> Path:
    """返回文件记录实际落盘路径，兼容旧记录的路径缺省情况。"""
    if file_record.storage_path:
        return Path(file_record.storage_path)
    return get_file_path(file_record.id, file_record.filename)


def delete_stored_file(file_record: Any) -> None:
    """删除文件记录对应的本地文件；不存在时保持幂等。"""
    file_storage_path(file_record).unlink(missing_ok=True)


def _record_storage_backend(file_record: Any) -> str:
    return str(getattr(file_record, "storage_backend", None) or "local")


def _resolve_storage_backend(file_record: Any, override: Any | None = None) -> Any:
    from app.config import settings
    from app.storage.factory import get_storage_backend

    if override is not None and _record_storage_backend(file_record) == settings.STORAGE_BACKEND:
        return override
    return get_storage_backend(_record_storage_backend(file_record))


async def read_stored_content(file_record: Any, storage_backend: Any | None = None) -> bytes:
    """按文件记录的后端读取内容，支持注入当前配置后端。"""
    backend = _resolve_storage_backend(file_record, storage_backend)
    return await backend.download(file_record.storage_path)


async def delete_stored_content(
    file_record: Any,
    storage_backend: Any | None = None,
) -> None:
    """按文件记录的后端删除内容；不存在时保持幂等。"""
    if _record_storage_backend(file_record) == "local":
        if storage_backend is not None:
            await _resolve_storage_backend(file_record, storage_backend).delete(
                file_record.storage_path
            )
        else:
            delete_stored_file(file_record)
        return
    await _resolve_storage_backend(file_record, storage_backend).delete(file_record.storage_path)


def user_can_access_file(file_record: Any, user: Any | None) -> bool:
    """判断用户是否可以读取文件内容或元数据。"""
    if file_record.is_public:
        return True
    if user is None:
        return False
    return file_record.owner_id == user.id or user.role == "admin"


def user_can_manage_file(file_record: Any, user: Any | None) -> bool:
    """判断用户是否可以删除或管理文件。"""
    if user is None:
        return False
    return file_record.owner_id == user.id or user.role == "admin"


def is_file_usable(file_record: Any, *, now: datetime | None = None) -> bool:
    """Return whether a file may be read or bound to a new task."""
    if getattr(file_record, "deleted_at", None) is not None:
        return False
    if bool(getattr(file_record, "is_corrupted", False)):
        return False
    expires_at = getattr(file_record, "expires_at", None)
    if expires_at is None:
        return True
    current = now if now is not None else utcnow()
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
    if current.tzinfo is not None:
        current = current.astimezone(UTC).replace(tzinfo=None)
    return expires_at > current
