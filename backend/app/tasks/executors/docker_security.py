"""Docker 执行器的输入安全校验。"""

import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.tasks.executors.errors import TaskExecutionError

_DOCKER_IMAGE_DIGEST_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9./_-]*(?::[0-9]+)?(?:/[a-z0-9][a-z0-9._-]*)*@sha256:[0-9a-f]{64}$"
)
_SHELL_CONTROL_PATTERN = re.compile(r"[;&|`$<>\r\n]")
_SHELL_EXECUTABLES = {"ash", "bash", "dash", "fish", "ksh", "sh", "zsh"}


def contains_shell_control(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_SHELL_CONTROL_PATTERN.search(value))
    if isinstance(value, dict):
        return any(contains_shell_control(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(contains_shell_control(item) for item in value)
    return False


def validate_docker_execution_inputs(image: str, command: list[str], task_params: Any) -> None:
    allowed_images = settings.DOCKER_ALLOWED_IMAGES
    if allowed_images and image not in allowed_images:
        raise TaskExecutionError("Docker image is not in the configured allowlist")
    if (
        settings.ENVIRONMENT in {"staging", "production"}
        and settings.DOCKER_REQUIRE_IMAGE_DIGEST_IN_DEPLOYMENT
        and not _DOCKER_IMAGE_DIGEST_PATTERN.fullmatch(image)
    ):
        raise TaskExecutionError("Docker image must use an immutable digest in deployment")
    if not isinstance(command, list) or not all(isinstance(argument, str) for argument in command):
        raise TaskExecutionError("Docker command must be a string array")
    if any(_SHELL_CONTROL_PATTERN.search(argument) for argument in command):
        raise TaskExecutionError("Docker command contains unsafe shell control characters")
    if command and Path(command[0]).name.lower() in _SHELL_EXECUTABLES:
        raise TaskExecutionError("Docker command contains unsafe shell control executable")
    if contains_shell_control(task_params):
        raise TaskExecutionError("Task parameters contain unsafe shell control characters")
