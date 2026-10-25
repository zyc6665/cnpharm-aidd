"""Execution executor type mapping tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.execution.executor_types import (  # noqa: E402
    execution_types_for_tool_type,
    execution_type_for_tool_type,
)
from app.execution.contracts import ExecutionRequest  # noqa: E402


def test_execution_type_mapping_matches_tool_package_migration_contract():
    assert execution_types_for_tool_type("docker_image") == ("container",)
    assert execution_types_for_tool_type("python_script") == ("cli",)
    assert execution_types_for_tool_type("ssh_job") == ("remote_job",)
    assert execution_types_for_tool_type("k8s_job") == ("k8s_job",)


def test_remote_api_tool_type_is_no_longer_supported():
    """交付线移除了远程 API 工具类型，映射必须明确拒绝。"""
    assert execution_types_for_tool_type("remote_api") is None
    with pytest.raises(ValueError):
        execution_type_for_tool_type("remote_api")


def test_execution_type_mapping_rejects_builtin_and_unknown_types():
    with pytest.raises(ValueError, match="builtin"):
        execution_type_for_tool_type("builtin")
    with pytest.raises(ValueError, match="unsupported"):
        execution_type_for_tool_type("unknown")


def test_execution_request_can_be_built_from_legacy_tool_config():
    request = ExecutionRequest.from_tool_config(
        idempotency_key="task-1:attempt-1",
        project_id="project-1",
        requested_by="user-1",
        tool_package_version_id="package-version-1",
        variant="cpu",
        tool_config={"type": "ssh_job"},
        parameters={"threshold": 0.5},
        resources={"gpu_required": False},
    )

    assert request.executor_type == "remote_job"
    assert request.parameters == {"threshold": 0.5}
    assert request.resources == {"gpu_required": False}


def test_execution_request_can_be_built_from_k8s_tool_config():
    request = ExecutionRequest.from_tool_config(
        idempotency_key="task-2:attempt-1",
        project_id="project-1",
        requested_by="user-1",
        tool_package_version_id="package-version-1",
        variant="gpu",
        tool_config={"type": "k8s_job"},
    )

    assert request.executor_type == "k8s_job"
