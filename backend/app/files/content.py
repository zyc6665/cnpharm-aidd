"""Storage-agnostic access to persisted file content."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from app.files.file_records import file_storage_path
from app.storage.factory import get_storage_backend


def _storage_backend_name(file_record: Any) -> str:
    return str(getattr(file_record, "storage_backend", None) or "local")


def _require_storage_path(file_record: Any) -> str:
    storage_path = getattr(file_record, "storage_path", None)
    if not storage_path:
        raise FileNotFoundError(f"File {getattr(file_record, 'id', '')} has no storage path")
    return str(storage_path)


async def file_exists(file_record: Any) -> bool:
    """Check whether a persisted file is available in its configured backend."""
    try:
        storage_path = _require_storage_path(file_record)
    except FileNotFoundError:
        return False

    if _storage_backend_name(file_record) == "minio":
        return await get_storage_backend("minio").exists(storage_path)
    return await asyncio.to_thread(file_storage_path(file_record).is_file)


async def read_file_bytes(file_record: Any) -> bytes:
    """Read persisted file content without exposing backend-specific paths."""
    storage_path = _require_storage_path(file_record)
    if _storage_backend_name(file_record) == "minio":
        return await get_storage_backend("minio").download(storage_path)

    path = file_storage_path(file_record)
    return await asyncio.to_thread(path.read_bytes)


async def ensure_local_file(file_record: Any, destination: Path) -> Path:
    """Make a file available at a local path for a legacy/tool runtime."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if _storage_backend_name(file_record) == "minio":
        content = await read_file_bytes(file_record)
        await asyncio.to_thread(destination.write_bytes, content)
        return destination

    source = file_storage_path(file_record)
    if not await asyncio.to_thread(source.is_file):
        raise FileNotFoundError(source)
    if source != destination:
        await asyncio.to_thread(shutil.copy2, source, destination)
    return destination
