"""Workflow input file validation helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ForbiddenException, NotFoundException
from app.models.files import File as FileModel
from app.models.users import User
from app.services.semantic_types import normalize_semantic_type


async def validate_input_files(
    db: AsyncSession,
    *,
    current_user: User,
    input_files: dict[str, str],
) -> dict[str, str]:
    normalized = {
        normalize_semantic_type(str(semantic_type)): str(file_id)
        for semantic_type, file_id in input_files.items()
        if file_id
    }
    for semantic_type, file_id in normalized.items():
        file_record = await db.get(FileModel, file_id)
        if not file_record:
            raise NotFoundException(f"Workflow input file not found: {semantic_type}")
        if file_record.owner_id != current_user.id and current_user.role != "admin":
            raise ForbiddenException(f"No permission to use workflow input file: {semantic_type}")
    return normalized
