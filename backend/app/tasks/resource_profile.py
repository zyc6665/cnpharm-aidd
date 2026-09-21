"""任务资源画像快照。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ResourceRequest:
    """Canonical task resource request shared by dispatch and executors."""

    executor_type: str | None
    tier: str | None
    cpu: float | None
    memory_gb: float | None
    cpu_limit: float | None
    memory_limit: str | None
    gpu_required: bool
    gpu_count: int
    gpu_memory_mb: int
    timeout_sec: int
    parallelism: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_resource_request(
    config: dict[str, Any] | None,
    *,
    gpu_required: bool | None = None,
    gpu_memory_mb: int | None = None,
    params: dict[str, Any] | None = None,
) -> ResourceRequest:
    """Normalize tool configuration into one runtime resource contract."""
    normalized = dict(config or {})
    profile = normalized.get("resource_profile")
    profile = profile if isinstance(profile, dict) else {}

    explicit_cpu = _requests_cpu(params)
    resolved_gpu_required = (
        bool(gpu_required)
        if gpu_required is not None
        else bool(normalized.get("gpu_required", profile.get("gpu_required", False)))
    )
    resolved_gpu_memory_mb = (
        int(gpu_memory_mb or 0)
        if gpu_memory_mb is not None
        else int(normalized.get("gpu_memory_mb", 0) or 0)
    )
    if not resolved_gpu_memory_mb:
        resolved_gpu_memory_mb = int(float(profile.get("gpu_memory_gb", 0) or 0) * 1024)

    if explicit_cpu:
        resolved_gpu_required = False
        resolved_gpu_memory_mb = 0

    cpu = _positive_float(profile.get("cpu"))
    if cpu is None:
        cpu = _positive_float(normalized.get("cpu_limit"))

    memory_gb = _positive_float(profile.get("memory_gb"))
    memory_limit = _format_memory_limit(memory_gb)
    if memory_limit is None:
        memory_limit = _normalize_memory_limit(normalized.get("memory_limit"))

    gpu_config = normalized.get("gpu_config")
    gpu_count = 0
    if isinstance(gpu_config, dict):
        gpu_count = _positive_int(gpu_config.get("count")) or 0
    if resolved_gpu_required and gpu_count < 1:
        gpu_count = 1

    timeout_sec = int(
        normalized.get("timeout_sec")
        or (float(profile.get("timeout_minutes", 0) or 0) * 60)
        or 600
    )
    parallelism = _positive_int(profile.get("parallelism")) or 1

    return ResourceRequest(
        executor_type=normalized.get("type"),
        tier=str(profile.get("tier") or "").strip() or None,
        cpu=cpu,
        memory_gb=memory_gb,
        cpu_limit=cpu,
        memory_limit=memory_limit,
        gpu_required=resolved_gpu_required,
        gpu_count=gpu_count,
        gpu_memory_mb=resolved_gpu_memory_mb,
        timeout_sec=timeout_sec,
        parallelism=parallelism,
    )


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
    request = build_resource_request(
        normalized,
        gpu_required=gpu_required,
        gpu_memory_mb=gpu_memory_mb,
        params=params,
    )

    return {
        "executor_type": request.executor_type,
        "gpu_required": request.gpu_required,
        "gpu_memory_mb": request.gpu_memory_mb,
        "timeout_sec": request.timeout_sec,
        "resource_request": request.as_dict(),
        "resource_profile": deepcopy(resource_profile) if isinstance(resource_profile, dict) else {},
    }


def apply_resource_request_to_config(
    config: dict[str, Any],
    resource_snapshot: dict[str, Any],
) -> None:
    """Apply a task snapshot to executor runtime settings in place."""
    request = resource_snapshot.get("resource_request")
    if not isinstance(request, dict):
        request = {
            "gpu_required": resource_snapshot.get("gpu_required", False),
            "gpu_memory_mb": resource_snapshot.get("gpu_memory_mb", 0),
            "timeout_sec": resource_snapshot.get("timeout_sec"),
        }

    if request.get("cpu_limit") is not None:
        config["cpu_limit"] = request["cpu_limit"]
    if request.get("memory_limit"):
        config["memory_limit"] = request["memory_limit"]
    if request.get("parallelism") is not None:
        config["parallelism"] = request["parallelism"]
    if request.get("timeout_sec"):
        config["timeout_sec"] = int(request["timeout_sec"])

    config["gpu_required"] = bool(request.get("gpu_required", False))
    config["gpu_memory_required_mb"] = int(request.get("gpu_memory_mb") or 0)
    if config["gpu_required"]:
        gpu_config = dict(config.get("gpu_config") or {})
        gpu_config["count"] = max(int(request.get("gpu_count") or 1), 1)
        config["gpu_config"] = gpu_config


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _format_memory_limit(memory_gb: float | None) -> str | None:
    if memory_gb is None:
        return None
    return f"{memory_gb:g}g"


def _normalize_memory_limit(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


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
