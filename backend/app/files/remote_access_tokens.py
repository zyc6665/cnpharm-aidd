"""Short-lived signed file access tokens for remote tool input downloads."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from jose import JWTError, jwt

from app.common.time import utcnow
from app.config import settings


REMOTE_FILE_ACCESS_TOKEN_TYPE = "remote_file_access"


class RemoteFileAccessTokenError(ValueError):
    """Raised when a remote file access token is invalid."""


def create_remote_file_access_token(
    *,
    file_id: str,
    task_id: str,
    expires_in_seconds: int = 3600,
) -> str:
    """Create a token scoped to one file and one platform task."""
    now = utcnow()
    payload = {
        "type": REMOTE_FILE_ACCESS_TOKEN_TYPE,
        "file_id": str(file_id),
        "task_id": str(task_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in_seconds),
    }
    return jwt.encode(payload, _token_secret(), algorithm=settings.JWT_ALGORITHM)


def validate_remote_file_access_token(
    token: str,
    *,
    file_id: str,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Validate that a token grants access to the requested file and optional task."""
    try:
        payload = jwt.decode(
            token,
            _token_secret(),
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise RemoteFileAccessTokenError("远程文件访问令牌无效或已过期") from exc

    if payload.get("type") != REMOTE_FILE_ACCESS_TOKEN_TYPE:
        raise RemoteFileAccessTokenError("远程文件访问令牌类型无效")
    if str(payload.get("file_id") or "") != str(file_id):
        raise RemoteFileAccessTokenError("远程文件访问令牌文件不匹配")
    if task_id is not None and str(payload.get("task_id") or "") != str(task_id):
        raise RemoteFileAccessTokenError("远程文件访问令牌任务不匹配")
    return payload


def _token_secret() -> str:
    return (
        settings.JWT_SECRET_KEY
        or settings.SETTINGS_ENCRYPTION_KEY
        or "development-remote-file-access-token-secret"
    )

