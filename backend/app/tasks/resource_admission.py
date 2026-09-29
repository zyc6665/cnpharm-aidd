"""任务资源准入决策。"""

from __future__ import annotations

from dataclasses import dataclass

from app.tasks.resource_profile import ResourceRequest


@dataclass(frozen=True)
class WorkerCapability:
    """Worker 声明的静态执行能力和容量。"""

    worker_id: str
    queue: str | None = None
    executor_types: tuple[str, ...] = ()
    tiers: tuple[str, ...] = ()
    cpu_capacity: float | None = None
    memory_capacity_gb: float | None = None
    gpu_count: int | None = None
    gpu_memory_mb: int | None = None
    parallelism: int | None = None
    healthy: bool = True


@dataclass(frozen=True)
class AdmissionDecision:
    """一次资源准入判断结果。"""

    admitted: bool
    worker_id: str
    reason: str | None = None
    queue: str | None = None


class ResourceAdmissionPolicy:
    """使用任务资源请求和 Worker capability 做纯准入判断。"""

    @classmethod
    def select_worker(
        cls,
        request: ResourceRequest,
        capabilities: list[WorkerCapability] | tuple[WorkerCapability, ...],
    ) -> AdmissionDecision:
        for capability in capabilities:
            decision = cls.evaluate(request, capability)
            if decision.admitted:
                return decision
        return AdmissionDecision(False, "", "no_capable_worker")

    @staticmethod
    def evaluate(
        request: ResourceRequest,
        capability: WorkerCapability,
    ) -> AdmissionDecision:
        if not capability.healthy:
            return AdmissionDecision(False, capability.worker_id, "worker_unhealthy")

        if (
            request.executor_type
            and capability.executor_types
            and request.executor_type not in capability.executor_types
        ):
            return AdmissionDecision(False, capability.worker_id, "executor_unsupported")

        if (
            request.tier
            and capability.tiers
            and request.tier not in capability.tiers
        ):
            return AdmissionDecision(False, capability.worker_id, "tier_unsupported")

        if (
            request.cpu_limit is not None
            and capability.cpu_capacity is not None
            and request.cpu_limit > capability.cpu_capacity
        ):
            return AdmissionDecision(False, capability.worker_id, "cpu_capacity_insufficient")

        if (
            request.memory_gb is not None
            and capability.memory_capacity_gb is not None
            and request.memory_gb > capability.memory_capacity_gb
        ):
            return AdmissionDecision(False, capability.worker_id, "memory_capacity_insufficient")

        if (
            capability.parallelism is not None
            and request.parallelism > capability.parallelism
        ):
            return AdmissionDecision(False, capability.worker_id, "parallelism_insufficient")

        if request.gpu_required:
            if (
                capability.gpu_count is not None
                and request.gpu_count > capability.gpu_count
            ):
                return AdmissionDecision(False, capability.worker_id, "gpu_count_insufficient")
            if (
                capability.gpu_memory_mb is not None
                and request.gpu_memory_mb > capability.gpu_memory_mb
            ):
                return AdmissionDecision(False, capability.worker_id, "gpu_memory_insufficient")

        return AdmissionDecision(True, capability.worker_id, queue=capability.queue)
