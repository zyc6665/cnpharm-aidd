from __future__ import annotations

from app.tasks.resource_profile import build_task_resource_snapshot


def test_build_task_resource_snapshot_preserves_profile_and_dispatch_limits() -> None:
    snapshot = build_task_resource_snapshot(
        {
            "type": "docker_image",
            "gpu_required": True,
            "gpu_memory_mb": 16384,
            "timeout_sec": 86400,
            "resource_profile": {
                "tier": "heavy",
                "cpu": 16,
                "memory_gb": 64,
                "gpu_required": True,
                "gpu_memory_gb": 16,
                "expected_minutes": 240,
            },
        }
    )

    assert snapshot == {
        "executor_type": "docker_image",
        "gpu_required": True,
        "gpu_memory_mb": 16384,
        "timeout_sec": 86400,
        "resource_request": {
            "executor_type": "docker_image",
            "tier": "heavy",
            "cpu": 16.0,
            "memory_gb": 64.0,
            "cpu_limit": 16.0,
            "memory_limit": "64g",
            "gpu_required": True,
            "gpu_count": 1,
            "gpu_memory_mb": 16384,
            "timeout_sec": 86400,
            "parallelism": 1,
        },
        "resource_profile": {
            "tier": "heavy",
            "cpu": 16,
            "memory_gb": 64,
            "gpu_required": True,
            "gpu_memory_gb": 16,
            "expected_minutes": 240,
        },
    }


def test_build_task_resource_snapshot_defaults_missing_profile_without_sharing_input() -> None:
    config = {"type": "ssh_job", "timeout_sec": 3600}

    snapshot = build_task_resource_snapshot(config)
    snapshot["resource_profile"]["tier"] = "medium"

    assert snapshot == {
        "executor_type": "ssh_job",
        "gpu_required": False,
        "gpu_memory_mb": 0,
        "timeout_sec": 3600,
        "resource_request": {
            "executor_type": "ssh_job",
            "tier": None,
            "cpu": None,
            "memory_gb": None,
            "cpu_limit": None,
            "memory_limit": None,
            "gpu_required": False,
            "gpu_count": 0,
            "gpu_memory_mb": 0,
            "timeout_sec": 3600,
            "parallelism": 1,
        },
        "resource_profile": {"tier": "medium"},
    }
    assert "resource_profile" not in config


def test_build_task_resource_snapshot_uses_tool_gpu_fields_as_runtime_source_of_truth() -> None:
    snapshot = build_task_resource_snapshot(
        {"type": "ssh_job", "gpu_required": False, "gpu_memory_mb": 0},
        gpu_required=True,
        gpu_memory_mb=8192,
    )

    assert snapshot["gpu_required"] is True
    assert snapshot["gpu_memory_mb"] == 8192


def test_build_task_resource_snapshot_resolves_approved_profile_id():
    snapshot = build_task_resource_snapshot(
        {"type": "k8s_job", "resource_profile": "gpu-large", "gpu_required": False}
    )

    assert snapshot["resource_profile"]["id"] == "gpu-large"
    assert snapshot["resource_request"]["gpu_required"] is True
    assert snapshot["resource_request"]["cpu"] == 16.0
