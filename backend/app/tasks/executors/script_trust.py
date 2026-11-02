"""Python 脚本信任校验。"""

import hashlib
from pathlib import Path

from app.config import settings
from app.tasks.executors.errors import TaskExecutionError


def validate_script_trust(script_content: str | None, script_path: str | None) -> None:
    trusted_hashes = set(settings.TRUSTED_PYTHON_SCRIPT_SHA256)
    if settings.ENVIRONMENT not in {"staging", "production"} and not trusted_hashes:
        return
    if script_content is not None:
        content = script_content.encode("utf-8")
    elif script_path:
        try:
            content = Path(script_path).read_bytes()
        except OSError as exc:
            raise TaskExecutionError(f"无法读取 Python 脚本：{script_path}") from exc
    else:
        raise TaskExecutionError("缺少 Python 脚本内容")
    if hashlib.sha256(content).hexdigest() not in trusted_hashes:
        raise TaskExecutionError("Python 脚本不在可信 SHA-256 允许列表中")
