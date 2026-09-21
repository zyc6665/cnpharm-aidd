"""Worker capability 在线注册表。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.cache.base import CacheBackend
from app.common.time import utcnow
from app.tasks.resource_admission import (
    AdmissionDecision,
    ResourceAdmissionPolicy,
    WorkerCapability,
)


class WorkerCapabilityRegistry:
    """基于统一缓存后端维护 Worker capability 和 TTL 心跳。"""

    KEY_PREFIX = "worker:capability:"

    def __init__(
        self,
        *,
        cache: CacheBackend,
        ttl_seconds: int = 90,
        clock=utcnow,
    ) -> None:
        self.cache = cache
        self.ttl_seconds = max(int(ttl_seconds), 1)
        self.clock = clock

    async def register(self, capability: WorkerCapability) -> None:
        """注册或刷新一个 Worker capability。"""
        await self.cache.set_json(
            self._key(capability.worker_id),
            self._serialize(capability),
            expire=self.ttl_seconds,
        )

    async def heartbeat(self, worker_id: str) -> bool:
        """刷新已注册 Worker 的 TTL，找不到时返回 False。"""
        key = self._key(worker_id)
        payload = await self.cache.get_json(key)
        if not isinstance(payload, dict):
            return False

        payload["last_seen_at"] = self.clock().isoformat()
        await self.cache.set_json(key, payload, expire=self.ttl_seconds)
        return True

    async def unregister(self, worker_id: str) -> bool:
        """注销 Worker capability。"""
        return await self.cache.delete(self._key(worker_id))

    async def list_active(self) -> list[WorkerCapability]:
        """读取当前 TTL 内仍在线的 Worker capability。"""
        capabilities: list[WorkerCapability] = []
        for key in await self.cache.keys(f"{self.KEY_PREFIX}*"):
            payload = await self.cache.get_json(key)
            capability = self._deserialize(payload)
            if capability is not None:
                capabilities.append(capability)
        return sorted(capabilities, key=lambda item: item.worker_id)

    async def select_worker(self, request) -> AdmissionDecision:
        """从当前在线 Worker 中选择第一个满足请求的 Worker。""" 
        capabilities = await self.list_active()
        return ResourceAdmissionPolicy.select_worker(request, capabilities)

    @classmethod
    def _key(cls, worker_id: str) -> str:
        return f"{cls.KEY_PREFIX}{worker_id}"

    def _serialize(self, capability: WorkerCapability) -> dict[str, Any]:
        return {
            "worker_id": capability.worker_id,
            "executor_types": list(capability.executor_types),
            "tiers": list(capability.tiers),
            "cpu_capacity": capability.cpu_capacity,
            "memory_capacity_gb": capability.memory_capacity_gb,
            "gpu_count": capability.gpu_count,
            "gpu_memory_mb": capability.gpu_memory_mb,
            "parallelism": capability.parallelism,
            "healthy": capability.healthy,
            "last_seen_at": self.clock().isoformat(),
        }

    @staticmethod
    def _deserialize(payload: Any) -> WorkerCapability | None:
        if not isinstance(payload, dict):
            return None
        worker_id = str(payload.get("worker_id") or "").strip()
        if not worker_id:
            return None
        return WorkerCapability(
            worker_id=worker_id,
            executor_types=tuple(payload.get("executor_types") or ()),
            tiers=tuple(payload.get("tiers") or ()),
            cpu_capacity=_optional_float(payload.get("cpu_capacity")),
            memory_capacity_gb=_optional_float(payload.get("memory_capacity_gb")),
            gpu_count=_optional_int(payload.get("gpu_count")),
            gpu_memory_mb=_optional_int(payload.get("gpu_memory_mb")),
            parallelism=_optional_int(payload.get("parallelism")),
            healthy=bool(payload.get("healthy", True)),
        )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
