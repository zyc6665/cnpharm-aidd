"""资源等待原因的统一分类。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceWaitDescriptor:
    """供任务状态、日志和前端展示复用的资源等待描述。"""

    reason: str
    category: str
    scope: str | None = None
    dimension: str | None = None


def describe_resource_wait(reason: str | None) -> ResourceWaitDescriptor:
    """将底层资源拒绝码归一为稳定的展示分类。"""
    normalized = str(reason or "resource_unavailable").strip() or "resource_unavailable"

    if normalized == "gpu_unavailable":
        return ResourceWaitDescriptor(normalized, "gpu", dimension="gpu")

    quota_parts = normalized.split("_")
    if (
        len(quota_parts) >= 4
        and quota_parts[0] in {"user", "project"}
        and quota_parts[-2:] == ["quota", "exhausted"]
    ):
        dimension = "_".join(quota_parts[1:-2]) or None
        return ResourceWaitDescriptor(
            normalized,
            "quota",
            scope=quota_parts[0],
            dimension="memory" if dimension == "memory_gb" else dimension,
        )

    capacity_dimensions = {
        "cpu_capacity_exhausted": "cpu",
        "memory_capacity_exhausted": "memory",
        "parallelism_capacity_exhausted": "parallelism",
    }
    if normalized in capacity_dimensions:
        return ResourceWaitDescriptor(
            normalized,
            "worker_capacity",
            dimension=capacity_dimensions[normalized],
        )

    if normalized in {"quota_lock_busy", "resource_lock_busy"}:
        return ResourceWaitDescriptor(normalized, "scheduler")

    return ResourceWaitDescriptor(normalized, "resource")


def resource_wait_metadata(
    reason: str | None,
    *,
    legacy_reason: str,
) -> dict[str, str]:
    """构建资源等待元数据，同时保留旧版 reason 字段。"""
    descriptor = describe_resource_wait(reason)
    metadata = {
        "resource_wait_reason": legacy_reason,
        "resource_wait_code": descriptor.reason,
        "resource_wait_category": descriptor.category,
    }
    if descriptor.scope:
        metadata["resource_wait_scope"] = descriptor.scope
    if descriptor.dimension:
        metadata["resource_wait_dimension"] = descriptor.dimension
    return metadata
