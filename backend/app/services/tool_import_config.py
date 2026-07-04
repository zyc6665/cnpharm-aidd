"""工具导入配置归一化与校验。"""

from __future__ import annotations

import copy
import json
import shlex
from pathlib import Path
from typing import Any, Dict

try:
    from jsonschema import Draft7Validator

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover - 兜底分支
    HAS_JSONSCHEMA = False


class ToolImportConfigError(ValueError):
    """工具导入配置错误。"""


SUPPORTED_TOOL_TYPES = {"remote_api", "docker_image", "python_script", "ssh_job"}
SUPPORTED_REMOTE_METHODS = {"GET", "POST"}
SUPPORTED_SSH_RUNNER_MODES = {"docker_exec", "shell"}
SUPPORTED_SSH_AUTH_TYPES = {"key", "password"}


def resolve_script_relative_path(script_file: str | Path, target_path: str | Path) -> Path:
    """基于脚本文件位置解析目标路径。"""
    return Path(script_file).resolve().parent / Path(target_path)


def load_tool_import_config(config_path: str | Path) -> Dict[str, Any]:
    """从 JSON 文件读取并校验工具导入配置。"""
    path = Path(config_path)
    with open(path, "r", encoding="utf-8") as config_file:
        raw_config = json.load(config_file)

    normalized_config = normalize_tool_import_config(raw_config)
    return validate_tool_import_config(normalized_config)


def normalize_tool_import_config(raw_config: Dict[str, Any]) -> Dict[str, Any]:
    """将历史配置归一化为当前平台导入格式。"""
    config = copy.deepcopy(raw_config)

    if "display_name" in config and not config.get("name"):
        config["name"] = config["display_name"]

    tool_config = config.get("tool_config")
    if not isinstance(tool_config, dict):
        return config

    _move_root_schema_to_tool_config(config, tool_config, "input_schema")
    _move_root_schema_to_tool_config(config, tool_config, "output_schema")
    _move_root_schema_to_tool_config(config, tool_config, "example_params")

    if "timeout" in tool_config and "timeout_sec" not in tool_config:
        tool_config["timeout_sec"] = tool_config.pop("timeout")

    tool_type = tool_config.get("type")
    if tool_type == "remote_api":
        method = tool_config.get("method", "POST")
        tool_config["method"] = str(method).upper()
    elif tool_type == "python_script":
        if "script" in tool_config and "script_path" not in tool_config:
            tool_config["script_path"] = tool_config.pop("script")
    elif tool_type == "docker_image":
        command = tool_config.get("command")
        if isinstance(command, str):
            tool_config["command"] = shlex.split(command)

    return config


def validate_tool_import_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """校验工具导入配置。"""
    normalized_config = normalize_tool_import_config(config)

    _require_non_empty_string(normalized_config, "name")
    _require_non_empty_string(normalized_config, "slug")
    _require_non_empty_string(normalized_config, "version")

    tool_config = normalized_config.get("tool_config")
    if not isinstance(tool_config, dict):
        raise ToolImportConfigError("tool_config is required and must be an object")

    tool_type = tool_config.get("type")
    if tool_type not in SUPPORTED_TOOL_TYPES:
        raise ToolImportConfigError(
            f"tool_config.type must be one of {sorted(SUPPORTED_TOOL_TYPES)}"
        )

    if tool_type == "remote_api":
        _validate_remote_api_tool_config(tool_config)
    elif tool_type == "docker_image":
        _validate_docker_tool_config(tool_config)
    elif tool_type == "python_script":
        _validate_python_script_tool_config(tool_config)
    elif tool_type == "ssh_job":
        _validate_ssh_job_tool_config(tool_config)

    _validate_schema_object(tool_config, "input_schema")
    _validate_schema_object(tool_config, "output_schema")

    return normalized_config


def _move_root_schema_to_tool_config(
    root_config: Dict[str, Any],
    tool_config: Dict[str, Any],
    field_name: str,
) -> None:
    """将旧版顶层字段迁移到 tool_config 内部。"""
    if field_name in root_config and field_name not in tool_config:
        tool_config[field_name] = root_config.pop(field_name)
    elif field_name in root_config:
        root_config.pop(field_name)


def _require_non_empty_string(config: Dict[str, Any], field_name: str) -> None:
    """要求字段为非空字符串。"""
    value = config.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ToolImportConfigError(f"{field_name} is required and must be a non-empty string")


def _validate_remote_api_tool_config(tool_config: Dict[str, Any]) -> None:
    """校验 remote_api 配置。"""
    endpoint = tool_config.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ToolImportConfigError("tool_config.endpoint is required for remote_api")

    method = str(tool_config.get("method", "POST")).upper()
    if method not in SUPPORTED_REMOTE_METHODS:
        raise ToolImportConfigError(
            f"tool_config.method must be one of {sorted(SUPPORTED_REMOTE_METHODS)}"
        )
    tool_config["method"] = method

    timeout_sec = tool_config.get("timeout_sec", 600)
    if not isinstance(timeout_sec, int) or timeout_sec <= 0:
        raise ToolImportConfigError("tool_config.timeout_sec must be a positive integer")
    tool_config["timeout_sec"] = timeout_sec


def _validate_docker_tool_config(tool_config: Dict[str, Any]) -> None:
    """校验 docker_image 配置。"""
    image = tool_config.get("image")
    if not isinstance(image, str) or not image.strip():
        raise ToolImportConfigError("tool_config.image is required for docker_image")

    command = tool_config.get("command", [])
    if isinstance(command, str):
        command = shlex.split(command)
        tool_config["command"] = command

    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise ToolImportConfigError("tool_config.command must be a string array for docker_image")


def _validate_python_script_tool_config(tool_config: Dict[str, Any]) -> None:
    """校验 python_script 配置。"""
    script_path = tool_config.get("script_path")
    script_content = tool_config.get("script_content")
    if not isinstance(script_path, str) and not isinstance(script_content, str):
        raise ToolImportConfigError(
            "tool_config.script_path or tool_config.script_content is required for python_script"
        )


def _validate_ssh_job_tool_config(tool_config: Dict[str, Any]) -> None:
    """校验 ssh_job 配置。"""
    for field_name in ("host", "username", "remote_base_dir", "entrypoint"):
        value = tool_config.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ToolImportConfigError(f"tool_config.{field_name} is required for ssh_job")

    auth_type = str(tool_config.get("auth_type", "key")).lower()
    if auth_type not in SUPPORTED_SSH_AUTH_TYPES:
        raise ToolImportConfigError(
            f"tool_config.auth_type must be one of {sorted(SUPPORTED_SSH_AUTH_TYPES)}"
        )
    tool_config["auth_type"] = auth_type

    if auth_type == "key":
        auth_ref = tool_config.get("auth_ref")
        if not isinstance(auth_ref, str) or not auth_ref.strip():
            raise ToolImportConfigError("tool_config.auth_ref is required for ssh_job key auth")
    else:
        password_ref = tool_config.get("password_ref")
        if not isinstance(password_ref, str) or not password_ref.strip():
            raise ToolImportConfigError(
                "tool_config.password_ref is required for ssh_job password auth"
            )

    runner_mode = tool_config.get("runner_mode", "shell")
    if not isinstance(runner_mode, str) or runner_mode not in SUPPORTED_SSH_RUNNER_MODES:
        raise ToolImportConfigError(
            f"tool_config.runner_mode must be one of {sorted(SUPPORTED_SSH_RUNNER_MODES)}"
        )
    tool_config["runner_mode"] = runner_mode

    if runner_mode == "docker_exec":
        container_name = tool_config.get("container_name")
        if not isinstance(container_name, str) or not container_name.strip():
            raise ToolImportConfigError(
                "tool_config.container_name is required for ssh_job docker_exec mode"
            )

    timeout_sec = tool_config.get("timeout_sec", 3600)
    if not isinstance(timeout_sec, int) or timeout_sec <= 0:
        raise ToolImportConfigError("tool_config.timeout_sec must be a positive integer")
    tool_config["timeout_sec"] = timeout_sec

    port = tool_config.get("port", 22)
    if not isinstance(port, int) or port <= 0:
        raise ToolImportConfigError("tool_config.port must be a positive integer")
    tool_config["port"] = port

    output_globs = tool_config.get("output_globs")
    if output_globs is not None:
        if not isinstance(output_globs, list) or not all(isinstance(item, str) for item in output_globs):
            raise ToolImportConfigError("tool_config.output_globs must be a string array")

        for pattern in output_globs:
            normalized = Path(pattern).as_posix()
            if normalized.startswith("/") or ".." in normalized.split("/"):
                raise ToolImportConfigError(
                    "tool_config.output_globs may only reference files under output/"
                )
            if not normalized.startswith("output/"):
                raise ToolImportConfigError(
                    "tool_config.output_globs may only reference files under output/"
                )


def _validate_schema_object(tool_config: Dict[str, Any], field_name: str) -> None:
    """校验 JSON Schema 对象。"""
    schema = tool_config.get(field_name)
    if not isinstance(schema, dict):
        raise ToolImportConfigError(f"tool_config.{field_name} is required and must be an object")

    schema_type = schema.get("type")
    if schema_type != "object":
        raise ToolImportConfigError(f"tool_config.{field_name}.type must be 'object'")

    if HAS_JSONSCHEMA:
        try:
            Draft7Validator.check_schema(schema)
        except Exception as exc:  # pragma: no cover - 依赖库错误包装
            raise ToolImportConfigError(
                f"tool_config.{field_name} is not a valid JSON Schema: {exc}"
            ) from exc
