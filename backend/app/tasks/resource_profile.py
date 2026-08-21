"""任务资源画像快照。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_task_resource_snapshot(
    config: dict[str, Any] | None,
    *,
    gpu_required: bool | None = None,
    gpu_memory_mb: int | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从工具版本配置生成任务级资源快照。"""
    normalized = dict(config or {})
    resource_profile = normalized.get("resource_profile")
    explicit_cpu = _requests_cpu(params)
    resolved_gpu_required = (
        bool(gpu_required)
        if gpu_required is not None
        else bool(normalized.get("gpu_required", False))
    )
    resolved_gpu_memory_mb = (
        int(gpu_memory_mb or 0)
        if gpu_memory_mb is not None
        else int(normalized.get("gpu_memory_mb", 0) or 0)
    )
    if explicit_cpu:
        resolved_gpu_required = False
        resolved_gpu_memory_mb = 0

    return {
        "executor_type": normalized.get("type"),
        "gpu_required": resolved_gpu_required,
        "gpu_memory_mb": resolved_gpu_memory_mb,
        "timeout_sec": int(normalized.get("timeout_sec", 600) or 600),
        "resource_profile": deepcopy(resource_profile) if isinstance(resource_profile, dict) else {},
    }


def _requests_cpu(params: dict[str, Any] | None) -> bool:
    if not isinstance(params, dict):
        return False
    for candidate in (params, params.get("params"), params.get("parameters")):
        if not isinstance(candidate, dict):
            continue
        device = candidate.get("device") or candidate.get("accelerator")
        if isinstance(device, str) and device.strip().lower() == "cpu":
            return True
    return False
