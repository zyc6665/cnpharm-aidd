"""Worker capability 配置加载。"""

from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.tasks.resource_admission import WorkerCapability


def load_worker_capability() -> WorkerCapability | None:
    """从配置加载当前 Worker 的静态 capability 声明。"""
    raw = settings.WORKER_CAPABILITY_JSON
    if not raw or not raw.strip():
        return None

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("WORKER_CAPABILITY_JSON must be a JSON object")

    worker_id = str(payload.get("worker_id") or "").strip()
    if not worker_id:
        raise ValueError("WORKER_CAPABILITY_JSON.worker_id is required")

    return WorkerCapability(
        worker_id=worker_id,
        executor_types=_string_tuple(payload.get("executor_types")),
        tiers=_string_tuple(payload.get("tiers")),
        cpu_capacity=_optional_float(payload.get("cpu_capacity")),
        memory_capacity_gb=_optional_float(payload.get("memory_capacity_gb")),
        gpu_count=_optional_int(payload.get("gpu_count")),
        gpu_memory_mb=_optional_int(payload.get("gpu_memory_mb")),
        parallelism=_optional_int(payload.get("parallelism")),
        healthy=bool(payload.get("healthy", True)),
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid worker capability float: {value!r}") from exc


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid worker capability integer: {value!r}") from exc
