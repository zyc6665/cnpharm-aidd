"""Remote tool input file payload helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.config import settings
from app.files.remote_access_tokens import create_remote_file_access_token


def remote_file_download_url(
    *,
    file_id: str,
    task_id: str,
    config: dict[str, Any],
) -> str:
    expires_in = int(config.get("input_url_expires_in_sec", 3600))
    token = create_remote_file_access_token(
        file_id=file_id,
        task_id=task_id,
        expires_in_seconds=expires_in,
    )
    base_url = str(
        config.get("platform_base_url")
        or getattr(settings, "PUBLIC_API_BASE_URL", "")
        or ""
    ).rstrip("/")
    return f"{base_url}/api/v1/files/{file_id}/download?token={quote(token)}"


def remote_file_payload(file_record: Any, *, download_url: str) -> dict[str, Any]:
    return {
        "url": download_url,
        "filename": file_record.filename,
        "sha256": str(file_record.sha256).lower(),
        "content_type": file_record.content_type,
    }
