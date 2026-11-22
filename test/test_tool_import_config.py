"""工具导入配置归一化与校验测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.tool_import_config import (
    ToolImportConfigError,
    normalize_tool_import_config,
    resolve_script_relative_path,
    validate_tool_import_config,
)


def test_normalize_legacy_config_moves_schemas_into_tool_config() -> None:
    """旧配置应自动迁移到 tool_config 内部。"""
    raw_config = {
        "name": "simple-text-tool",
        "slug": "simple-text-tool",
        "description": "示例工具",
        "version": "1.0.0",
        "tool_config": {
            "type": "remote_api",
            "endpoint": "http://simple-text-tool:8000/process",
            "method": "POST",
            "timeout": 30,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "processed_text": {"type": "string"},
            },
        },
        "example_params": {
            "text": "hello",
        },
    }

    normalized = normalize_tool_import_config(raw_config)

    assert "input_schema" not in normalized
    assert "output_schema" not in normalized
    assert "example_params" not in normalized
    assert normalized["tool_config"]["timeout_sec"] == 30
    assert "timeout" not in normalized["tool_config"]
    assert normalized["tool_config"]["input_schema"]["required"] == ["text"]
    assert normalized["tool_config"]["output_schema"]["properties"]["processed_text"]["type"] == "string"
    assert normalized["tool_config"]["example_params"] == {"text": "hello"}


def test_validate_rejects_missing_tool_config() -> None:
    """缺少 tool_config 时应拒绝导入。"""
    with pytest.raises(ToolImportConfigError, match="tool_config"):
        validate_tool_import_config(
            {
                "name": "bad-tool",
                "slug": "bad-tool",
                "version": "1.0.0",
            }
        )


def test_validate_accepts_kubernetes_job_config():
    config = validate_tool_import_config(
        {
            "name": "managed-model",
            "slug": "managed-model",
            "version": "1.0.0",
            "tool_config": {
                "type": "k8s_job",
                "runtime": {"image": f"registry.example/model@sha256:{'a' * 64}"},
                "resource_profile": "gpu-large",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {"type": "object", "properties": {}},
            },
        }
    )

    assert config["tool_config"]["type"] == "k8s_job"


def test_validate_rejects_unregistered_kubernetes_resource_profile():
    with pytest.raises(ToolImportConfigError, match="未登记的资源档位"):
        validate_tool_import_config(
            {
                "name": "managed-model",
                "slug": "managed-model",
                "version": "1.0.0",
                "tool_config": {
                    "type": "k8s_job",
                    "runtime": {"image": f"registry.example/model@sha256:{'a' * 64}"},
                    "resource_profile": "unknown-profile",
                    "input_schema": {"type": "object", "properties": {}},
                    "output_schema": {"type": "object", "properties": {}},
                },
            }
        )


def test_tool_presentation_uses_backend_package_import_for_tool_config() -> None:
    """工具契约校验不应通过修改 sys.path 依赖仓库根目录模块。"""
    source = Path("backend/app/services/tool_presentation.py").read_text(encoding="utf-8")

    assert "sys.path.insert" not in source
    assert "from tool_import_config import" not in source
    assert "from app.services.tool_import_config import" in source


def test_normalize_python_script_aliases_script_to_script_path() -> None:
    """python_script 旧字段 script 应迁移为 script_path。"""
    normalized = normalize_tool_import_config(
        {
            "name": "python-tool",
            "slug": "python-tool",
            "version": "1.0.0",
            "tool_config": {
                "type": "python_script",
                "script": "/app/run.py",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
                "output_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
        }
    )

    assert normalized["tool_config"]["script_path"] == "/app/run.py"
    assert "script" not in normalized["tool_config"]


def test_normalize_docker_command_string_to_list() -> None:
    """docker 命令字符串应归一化为数组。"""
    normalized = normalize_tool_import_config(
        {
            "name": "docker-tool",
            "slug": "docker-tool",
            "version": "1.0.0",
            "tool_config": {
                "type": "docker_image",
                "image": "python:3.11-slim",
                "command": "python /app/main.py --mode prod",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
                "output_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
        }
    )

    assert normalized["tool_config"]["command"] == [
        "python",
        "/app/main.py",
        "--mode",
        "prod",
    ]

def test_resolve_script_relative_path_returns_absolute_repo_path() -> None:
    """脚本相对路径解析应在切换 cwd 后仍指向仓库根目录。"""
    resolved = resolve_script_relative_path(
        "scripts/create_tool.py",
        "../pytest.ini",
    )

    assert resolved.is_absolute()
    assert resolved.name == "pytest.ini"
    assert resolved.exists()
