from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.standard_artifact_collection import (  # noqa: E402
    collected_standard_result_payload,
    declared_standard_outputs_from_config,
)


def _tool_package_v2_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "pocket-tool",
            "name": "Pocket Tool",
            "version": "1.0.0",
        },
        "artifacts": {
            "inputs": [],
            "outputs": [
                {
                    "name": "pocket",
                    "type": "binding_pocket@1",
                    "cardinality": "one",
                    "required": True,
                }
            ],
        },
        "parameters_schema": {"type": "object", "properties": {}},
        "runtime": {
            "python": "3.10",
            "executor_support": ["ssh_docker_exec"],
            "selection_policy": "test",
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": "registry.example/pocket:1.0.0",
                },
                "fallback": {
                    "kind": "conda_pack",
                    "uri": "artifacts://envs/pocket.tar.gz",
                    "sha256": "test",
                },
            },
            "weights": {
                "manifest_uri": "artifacts://weights/pocket.json",
                "manifest_sha256": "test",
            },
            "cache_policy": {
                "key_fields": ["metadata.slug", "metadata.version"],
            },
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["cli"],
                "entrypoint": ["python", "run.py"],
            }
        ],
    }


def test_result_payload_accepts_supported_wrappers() -> None:
    payload = {"result_version": "aidd.sciminer/result.v2", "artifacts": {}}

    standard_result = collected_standard_result_payload(
        {"standard_result": payload}
    )
    legacy_result = collected_standard_result_payload({"result": payload})
    direct_result = collected_standard_result_payload(payload)

    assert standard_result is payload
    assert legacy_result is payload
    assert direct_result is payload
    assert collected_standard_result_payload(
        {"result_version": "legacy"}
    ) is None


def test_declared_standard_outputs_from_tool_package_v2_manifest() -> None:
    outputs = declared_standard_outputs_from_config(
        {"tool_package_manifest": _tool_package_v2_manifest()}
    )

    summary = [
        (item.name, item.type, item.cardinality, item.required)
        for item in outputs
    ]

    assert summary == [
        ("pocket", "binding_pocket@1", "one", True),
    ]


def test_declared_standard_outputs_ignore_retired_remote_contract() -> None:
    """交付线移除了 remote_api 执行器，其旧契约不再产出标准输出声明。"""
    outputs = declared_standard_outputs_from_config(
        {
            "type": "remote_api",
            "mode": "remote_tool_v1",
            "artifacts": {
                "outputs": [
                    {
                        "name": "report",
                        "type": "run_report@1",
                        "required": False,
                    }
                ]
            },
        }
    )

    summary = [
        (item.name, item.type, item.cardinality, item.required)
        for item in outputs
    ]

    assert summary == []
