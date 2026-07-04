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


def test_validate_rejects_invalid_http_method() -> None:
    """remote_api 仅允许 GET 和 POST。"""
    with pytest.raises(ToolImportConfigError, match="method"):
        validate_tool_import_config(
            {
                "name": "bad-tool",
                "slug": "bad-tool",
                "version": "1.0.0",
                "tool_config": {
                    "type": "remote_api",
                    "endpoint": "http://tool-service:8000/predict",
                    "method": "PUT",
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


def test_tools_api_uses_backend_package_import_for_tool_config() -> None:
    """工具 API 不应通过修改 sys.path 依赖仓库根目录模块。"""
    source = Path("backend/app/api/v1/tools.py").read_text(encoding="utf-8")

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


def test_validate_accepts_template_platform_tool_config() -> None:
    """新模板生成的 platform_tool.json 应通过校验。"""
    config = {
        "name": "Remote API Tool Template",
        "slug": "remote-api-tool-template",
        "description": "通用模板",
        "version": "0.1.0",
        "tool_config": {
            "type": "remote_api",
            "endpoint": "http://remote-api-tool-template:8000/predict",
            "method": "POST",
            "timeout_sec": 600,
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["task_id", "params"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "task_id": {"type": "string"},
                },
                "required": ["success", "task_id"],
            },
        },
    }

    validated = validate_tool_import_config(config)

    assert validated["tool_config"]["method"] == "POST"
    assert validated["tool_config"]["timeout_sec"] == 600


def test_validate_accepts_ssh_job_config() -> None:
    """ssh_job 配置应通过基础校验。"""
    config = {
        "name": "TargetDiff SSH",
        "slug": "targetdiff-ssh",
        "description": "通过 SSH 调用远端容器",
        "version": "1.0.0",
        "tool_config": {
            "type": "ssh_job",
            "host": "gpu-node-01.internal",
            "port": 22,
            "username": "runner",
            "auth_ref": "ssh_gpu_node_01",
            "runner_mode": "docker_exec",
            "remote_base_dir": "/srv/platform-jobs",
            "container_base_dir": "/workspace/platform-jobs",
            "entrypoint": "/app/platform_run.sh",
            "container_name": "targetdiff-prod",
            "timeout_sec": 3600,
            "cleanup_remote": True,
            "strict_host_key_checking": True,
            "output_globs": [
                "output/result.json",
                "output/logs/run.log",
                "output/artifacts/**/*",
            ],
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

    validated = validate_tool_import_config(config)

    assert validated["tool_config"]["type"] == "ssh_job"
    assert validated["tool_config"]["runner_mode"] == "docker_exec"
    assert validated["tool_config"]["container_base_dir"] == "/workspace/platform-jobs"


def test_validate_rejects_ssh_job_without_container_name_for_docker_exec() -> None:
    """docker_exec 模式缺少容器名时应拒绝。"""
    with pytest.raises(ToolImportConfigError, match="container_name"):
        validate_tool_import_config(
            {
                "name": "TargetDiff SSH",
                "slug": "targetdiff-ssh",
                "version": "1.0.0",
                "tool_config": {
                    "type": "ssh_job",
                    "host": "gpu-node-01.internal",
                    "username": "runner",
                    "auth_ref": "ssh_gpu_node_01",
                    "runner_mode": "docker_exec",
                    "remote_base_dir": "/srv/platform-jobs",
                    "entrypoint": "/app/platform_run.sh",
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


def test_validate_accepts_ssh_job_password_auth_config() -> None:
    """ssh_job 应支持基于 password_ref 的密码认证配置。"""
    config = {
        "name": "GCDM SSH Password",
        "slug": "gcdm-ssh-password",
        "version": "1.0.0",
        "tool_config": {
            "type": "ssh_job",
            "host": "4090",
            "port": 22,
            "username": "zhouyc",
            "auth_type": "password",
            "password_ref": "ssh_4090_password",
            "runner_mode": "docker_exec",
            "remote_base_dir": "/srv/platform-jobs",
            "entrypoint": "/app/platform_run.sh",
            "container_name": "kaiwu",
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

    validated = validate_tool_import_config(config)

    assert validated["tool_config"]["auth_type"] == "password"
    assert validated["tool_config"]["password_ref"] == "ssh_4090_password"


def test_validate_rejects_ssh_job_password_auth_without_password_ref() -> None:
    """密码认证缺少 password_ref 时应拒绝。"""
    with pytest.raises(ToolImportConfigError, match="password_ref"):
        validate_tool_import_config(
            {
                "name": "GCDM SSH Password",
                "slug": "gcdm-ssh-password",
                "version": "1.0.0",
                "tool_config": {
                    "type": "ssh_job",
                    "host": "4090",
                    "username": "zhouyc",
                    "auth_type": "password",
                    "runner_mode": "shell",
                    "remote_base_dir": "/srv/platform-jobs",
                    "entrypoint": "/app/platform_run.sh",
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


def test_resolve_script_relative_path_returns_absolute_repo_path() -> None:
    """脚本相对路径解析应在切换 cwd 后仍指向仓库根目录。"""
    resolved = resolve_script_relative_path(
        "create_tool.py",
        "example/remote-api-tool-template/platform_tool.json",
    )

    assert resolved.is_absolute()
    assert resolved.name == "platform_tool.json"
    assert resolved.exists()


def test_validate_accepts_ssh_job_template_platform_tool_json() -> None:
    """ssh_job 模板配置文件应可直接通过校验。"""
    template_path = Path("example/ssh-job-tool-template/platform_tool.json")
    assert template_path.exists()

    with template_path.open("r", encoding="utf-8") as template_file:
        raw_config = json.load(template_file)

    validated = validate_tool_import_config(raw_config)

    assert validated["tool_config"]["type"] == "ssh_job"
    assert validated["tool_config"]["runner_mode"] == "docker_exec"


def test_ssh_job_templates_mark_platform_managed_fields_as_hidden() -> None:
    """ssh_job 模板和示例中的平台字段不应直接暴露给最终用户。"""
    template_paths = [
        Path("example/ssh-job-tool-template/platform_tool.json"),
        Path("example/platform_tool.ssh_job.json"),
    ]

    for template_path in template_paths:
        with template_path.open("r", encoding="utf-8") as template_file:
            raw_config = json.load(template_file)

        input_schema = raw_config["tool_config"]["input_schema"]
        properties = input_schema["properties"]
        task_id = properties["task_id"]
        task_name = properties["task_name"]
        pocket_pdb = properties["input_files"]["properties"]["pocket_pdb"]

        assert task_id.get("hidden") is True
        assert task_name.get("hidden") is True
        assert pocket_pdb.get("format") == "file"
        assert pocket_pdb.get("accept") == ".pdb"


def test_therapainter_exposes_single_seed_sequence_field() -> None:
    """TheraPainter 不应同时暴露单条和多条种子肽序列入口。"""
    template_path = Path("example/therapainter/platform_tool.therapainter_evolve.ssh_job.json")
    with template_path.open("r", encoding="utf-8") as template_file:
        raw_config = json.load(template_file)

    input_schema = raw_config["tool_config"]["input_schema"]
    properties = input_schema["properties"]
    seed_like_fields = [
        key
        for key, value in properties.items()
        if "seed peptide" in str(value.get("title", "")).lower()
    ]

    assert "sequence" not in properties
    assert seed_like_fields == ["sequences"]
    assert properties["sequences"]["title"] == "Seed peptide sequence"
    assert input_schema["anyOf"] == [
        {"required": ["sequences"]},
        {"required": ["sequences_file"]},
    ]


def test_dualpep_exposes_single_peptide_sequence_field() -> None:
    """DualPep 不应同时暴露单条和多条肽序列入口。"""
    template_path = Path("example/therapainter/platform_tool.dualpep_predict.ssh_job.json")
    with template_path.open("r", encoding="utf-8") as template_file:
        raw_config = json.load(template_file)

    input_schema = raw_config["tool_config"]["input_schema"]
    properties = input_schema["properties"]
    peptide_sequence_fields = [
        key
        for key, value in properties.items()
        if "peptide sequence" in str(value.get("title", "")).lower()
    ]

    assert "sequence" not in properties
    assert peptide_sequence_fields == ["sequences"]
    assert properties["sequences"]["title"] == "Peptide sequence"
    assert input_schema["anyOf"] == [
        {"required": ["sequences"]},
        {"required": ["sequences_file"]},
    ]
