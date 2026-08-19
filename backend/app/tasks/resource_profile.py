"""任务资源画像快照。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_task_resource_snapshot(
    config: dict[str, Any] | None,
    *,
    gpu_required: bool | None = None,
    gpu_memory_mb: int | None = None,
) -> dict[str, Any]:
    """从工具版本配置生成任务级资源快照。"""
    normalized = dict(config or {})
    resource_profile = normalized.get("resource_profile")

    return {
        "executor_type": normalized.get("type"),
        "gpu_required": (
            bool(gpu_required)
            if gpu_required is not None
            else bool(normalized.get("gpu_required", False))
        ),
        "gpu_memory_mb": (
            int(gpu_memory_mb or 0)
            if gpu_memory_mb is not None
            else int(normalized.get("gpu_memory_mb", 0) or 0)
        ),
        "timeout_sec": int(normalized.get("timeout_sec", 600) or 600),
        "resource_profile": deepcopy(resource_profile) if isinstance(resource_profile, dict) else {},
    }
