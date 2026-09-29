"""Worker capability 在线注册表。"""

from __future__ import annotations

from typing import Any

from app.cache.base import CacheBackend
from app.common.time import utcnow
from app.tasks.resource_admission import (
    AdmissionDecision,
    ResourceAdmissionPolicy,
    WorkerCapability,
)
from app.tasks.resource_lease import WorkerResourceLeaseManager
from app.tasks.resource_profile import ResourceRequest


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
        # Keep the heartbeat from recreating a key that expired or was
        # unregistered after the read above.
        return await self.cache.set_json_if_exists(
            key,
            payload,
            expire=self.ttl_seconds,
        )

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

    async def select_available_worker(
        self,
        request: ResourceRequest,
    ) -> AdmissionDecision:
        """选择静态能力匹配且当前动态容量可用的 Worker。"""
        capabilities = await self.list_active()
        if not capabilities:
            return AdmissionDecision(False, "", "no_registered_workers")

        lease_manager = WorkerResourceLeaseManager(cache=self.cache)
        dynamic_rejection_reason: str | None = None
        candidates = await self._ordered_candidates(
            request,
            capabilities,
            lease_manager,
        )
        for _, capability, static_decision in candidates:

            dynamic_rejection_reason = await lease_manager.capacity_failure_reason(
                capability=capability,
                request=request,
            )
            if dynamic_rejection_reason is None:
                return static_decision

        return AdmissionDecision(
            False,
            "",
            dynamic_rejection_reason or "no_capable_worker",
        )

    async def reserve_worker(
        self,
        request: ResourceRequest,
        *,
        reservation_id: str,
        ttl_seconds: int,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> AdmissionDecision:
        """原子预留第一个静态匹配且动态容量可用的 Worker。"""
        capabilities = await self.list_active()
        if not capabilities:
            return AdmissionDecision(False, "", "no_registered_workers")

        lease_manager = WorkerResourceLeaseManager(cache=self.cache)
        dynamic_rejection_reason: str | None = None
        candidates = await self._ordered_candidates(
            request,
            capabilities,
            lease_manager,
        )
        for _, capability, static_decision in candidates:

            lease_decision = await lease_manager.acquire(
                capability=capability,
                request=request,
                lease_id=reservation_id,
                ttl_seconds=ttl_seconds,
                lease_phase="reserved",
                user_id=user_id,
                project_id=project_id,
            )
            if lease_decision.acquired:
                return static_decision
            dynamic_rejection_reason = lease_decision.reason or dynamic_rejection_reason

        return AdmissionDecision(
            False,
            "",
            dynamic_rejection_reason or "no_capable_worker",
        )

    async def _ordered_candidates(
        self,
        request: ResourceRequest,
        capabilities: list[WorkerCapability],
        lease_manager: WorkerResourceLeaseManager,
    ) -> list[tuple[float, WorkerCapability, AdmissionDecision]]:
        """按当前资源负载升序排列静态匹配的 Worker。"""
        candidates: list[tuple[float, WorkerCapability, AdmissionDecision]] = []
        for capability in capabilities:
            decision = ResourceAdmissionPolicy.evaluate(request, capability)
            if not decision.admitted:
                continue
            usage = await lease_manager.current_usage_summary(capability.worker_id)
            candidates.append(
                (
                    self._load_score(capability, usage),
                    capability,
                    decision,
                )
            )
        return sorted(candidates, key=lambda item: (item[0], item[1].worker_id))

    @staticmethod
    def _load_score(
        capability: WorkerCapability,
        usage: dict[str, float | int],
    ) -> float:
        ratios: list[float] = []
        if capability.cpu_capacity and capability.cpu_capacity > 0:
            ratios.append(float(usage["cpu"]) / capability.cpu_capacity)
        if capability.memory_capacity_gb and capability.memory_capacity_gb > 0:
            ratios.append(float(usage["memory_gb"]) / capability.memory_capacity_gb)
        if capability.parallelism and capability.parallelism > 0:
            ratios.append(float(usage["parallelism"]) / capability.parallelism)
        return max(ratios, default=0.0)

    @classmethod
    def _key(cls, worker_id: str) -> str:
        return f"{cls.KEY_PREFIX}{worker_id}"

    def _serialize(self, capability: WorkerCapability) -> dict[str, Any]:
        return {
            "worker_id": capability.worker_id,
            "queue": capability.queue,
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
            queue=_optional_string(payload.get("queue")),
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


def _optional_string(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
