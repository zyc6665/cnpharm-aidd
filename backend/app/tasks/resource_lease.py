"""基于缓存的 Worker 动态资源租约。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any
from uuid import uuid4

from app.cache.base import CacheBackend
from app.common.time import utcnow
from app.tasks.resource_admission import WorkerCapability
from app.tasks.resource_quota import (
    ResourceQuotaManager,
    build_resource_quota_manager,
)
from app.tasks.resource_profile import ResourceRequest


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResourceLeaseDecision:
    """一次动态资源租约申请结果。"""

    acquired: bool
    worker_id: str
    lease_id: str
    reason: str | None = None


class WorkerResourceLeaseManager:
    """使用带 TTL 的缓存租约限制 Worker 的动态资源占用。"""

    LEASE_KEY_PREFIX = "worker:resource:lease:"
    LOCK_KEY_PREFIX = "worker:resource:lock:"
    LOCK_TTL_SECONDS = 10
    MIN_LEASE_TTL_SECONDS = 60
    HEARTBEAT_INTERVAL_SECONDS = 30

    def __init__(
        self,
        *,
        cache: CacheBackend,
        lock_ttl_seconds: int = LOCK_TTL_SECONDS,
        clock=utcnow,
        quota_manager: ResourceQuotaManager | None = None,
    ) -> None:
        self.cache = cache
        self.lock_ttl_seconds = max(int(lock_ttl_seconds), 1)
        self.clock = clock
        self.quota_manager = (
            quota_manager
            if quota_manager is not None
            else build_resource_quota_manager(cache)
        )

    async def acquire(
        self,
        *,
        capability: WorkerCapability,
        request: ResourceRequest,
        lease_id: str,
        ttl_seconds: int | None = None,
        lease_phase: str = "running",
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> ResourceLeaseDecision:
        """在 Worker 当前容量允许时创建或刷新一个租约。"""
        worker_id = str(capability.worker_id or "").strip()
        normalized_lease_id = str(lease_id or "").strip()
        normalized_phase = _normalize_lease_phase(lease_phase)
        normalized_user_id = _normalize_scope_id(user_id)
        normalized_project_id = _normalize_scope_id(project_id)
        if not worker_id or not normalized_lease_id:
            return ResourceLeaseDecision(
                acquired=False,
                worker_id=worker_id,
                lease_id=normalized_lease_id,
                reason="invalid_lease_identity",
            )

        lease_key = self._lease_key(worker_id, normalized_lease_id)
        lease_ttl = self.lease_ttl_seconds(request, ttl_seconds)
        existing = await self.cache.get_json(lease_key)
        if isinstance(existing, dict):
            await self._refresh_existing_lease(
                lease_key,
                existing,
                lease_ttl,
                normalized_phase,
                normalized_user_id,
                normalized_project_id,
            )
            return ResourceLeaseDecision(
                acquired=True,
                worker_id=worker_id,
                lease_id=normalized_lease_id,
            )

        quota_locks: list[tuple[str, str]] = []
        if self.quota_manager is not None:
            acquired_quota_locks = await self.quota_manager.acquire_scope_locks(
                user_id=normalized_user_id,
                project_id=normalized_project_id,
            )
            if acquired_quota_locks is None:
                return ResourceLeaseDecision(
                    acquired=False,
                    worker_id=worker_id,
                    lease_id=normalized_lease_id,
                    reason="quota_lock_busy",
                )
            quota_locks = acquired_quota_locks

        lock_key = self._lock_key(worker_id)
        lock_token = uuid4().hex
        try:
            if not await self.cache.set(
                lock_key,
                lock_token,
                ex=self.lock_ttl_seconds,
                nx=True,
            ):
                return ResourceLeaseDecision(
                    acquired=False,
                    worker_id=worker_id,
                    lease_id=normalized_lease_id,
                    reason="resource_lock_busy",
                )

            existing = await self.cache.get_json(lease_key)
            if isinstance(existing, dict):
                await self._refresh_existing_lease(
                    lease_key,
                    existing,
                    lease_ttl,
                    normalized_phase,
                    normalized_user_id,
                    normalized_project_id,
                )
                return ResourceLeaseDecision(
                    acquired=True,
                    worker_id=worker_id,
                    lease_id=normalized_lease_id,
                )

            usage = await self.current_usage(worker_id)
            requested = self._requested_capacity(request)
            reason = self._capacity_failure_reason(
                capability=capability,
                usage=usage,
                requested=requested,
            )
            if reason is not None:
                return ResourceLeaseDecision(
                    acquired=False,
                    worker_id=worker_id,
                    lease_id=normalized_lease_id,
                    reason=reason,
                )

            if self.quota_manager is not None:
                quota_reason = await self.quota_manager.capacity_failure_reason(
                    user_id=normalized_user_id,
                    project_id=normalized_project_id,
                    requested_cpu=float(requested["cpu"]),
                    requested_memory_gb=float(requested["memory_gb"]),
                    requested_parallelism=int(requested["parallelism"]),
                )
                if quota_reason is not None:
                    return ResourceLeaseDecision(
                        acquired=False,
                        worker_id=worker_id,
                        lease_id=normalized_lease_id,
                        reason=quota_reason,
                    )

            payload: dict[str, Any] = {
                "worker_id": worker_id,
                "lease_id": normalized_lease_id,
                "cpu": requested["cpu"],
                "memory_gb": requested["memory_gb"],
                "parallelism": requested["parallelism"],
                "gpu_count": requested["gpu_count"],
                "gpu_memory_mb": requested["gpu_memory_mb"],
                "phase": normalized_phase,
                "created_at": self.clock().isoformat(),
            }
            if normalized_user_id is not None:
                payload["user_id"] = normalized_user_id
            if normalized_project_id is not None:
                payload["project_id"] = normalized_project_id
            await self.cache.set_json(lease_key, payload, expire=lease_ttl)
            return ResourceLeaseDecision(
                acquired=True,
                worker_id=worker_id,
                lease_id=normalized_lease_id,
            )
        finally:
            await self.cache.delete_if_value(lock_key, lock_token)
            if self.quota_manager is not None:
                await self.quota_manager.release_scope_locks(quota_locks)

    async def _refresh_existing_lease(
        self,
        lease_key: str,
        payload: dict[str, Any],
        lease_ttl: int,
        requested_phase: str,
        user_id: str | None,
        project_id: str | None,
    ) -> None:
        """刷新租约并允许 reservation 单向转为 running。"""
        current_phase = _normalize_lease_phase(payload.get("phase"))
        effective_phase = (
            "running"
            if current_phase == "running" or requested_phase == "running"
            else requested_phase
        )
        if payload.get("phase") != effective_phase:
            updated_payload = {**payload, "phase": effective_phase}
            if effective_phase == "running" and current_phase != "running":
                updated_payload["claimed_at"] = self.clock().isoformat()
            if user_id is not None:
                updated_payload["user_id"] = user_id
            if project_id is not None:
                updated_payload["project_id"] = project_id
            await self.cache.set_json(lease_key, updated_payload, expire=lease_ttl)
            return
        if user_id is not None or project_id is not None:
            updated_payload = dict(payload)
            if user_id is not None:
                updated_payload["user_id"] = user_id
            if project_id is not None:
                updated_payload["project_id"] = project_id
            await self.cache.set_json(lease_key, updated_payload, expire=lease_ttl)
            return
        await self.cache.expire(lease_key, lease_ttl)

    async def release(self, *, worker_id: str, lease_id: str) -> bool:
        """释放一个动态资源租约。"""
        return await self.cache.delete(self._lease_key(worker_id, lease_id))

    async def heartbeat(
        self,
        *,
        worker_id: str,
        lease_id: str,
        ttl_seconds: int,
    ) -> bool:
        """刷新租约 TTL，不在心跳时重建已释放的租约。"""
        return await self.cache.expire(
            self._lease_key(worker_id, lease_id),
            max(int(ttl_seconds), self.MIN_LEASE_TTL_SECONDS),
        )

    async def current_usage(self, worker_id: str) -> dict[str, float | int]:
        """汇总 Worker 当前未过期租约的资源占用。"""
        summary = await self.current_usage_summary(worker_id)
        return {
            "cpu": summary["cpu"],
            "memory_gb": summary["memory_gb"],
            "parallelism": summary["parallelism"],
        }

    async def current_usage_summary(self, worker_id: str) -> dict[str, float | int]:
        """一次扫描返回资源占用和租约阶段计数。"""
        usage: dict[str, float | int] = {
            "cpu": 0.0,
            "memory_gb": 0.0,
            "parallelism": 0,
            "reservation_count": 0,
            "execution_count": 0,
            "unknown_count": 0,
        }
        prefix = self._lease_key(str(worker_id), "")
        for key in await self.cache.scan_keys(f"{prefix}*"):
            payload = await self.cache.get_json(key)
            if not isinstance(payload, dict):
                continue
            usage["cpu"] += _as_float(payload.get("cpu"))
            usage["memory_gb"] += _as_float(payload.get("memory_gb"))
            usage["parallelism"] += _as_int(payload.get("parallelism"))
            phase = _normalize_lease_phase(payload.get("phase"))
            if phase == "reserved":
                usage["reservation_count"] += 1
            elif phase == "running":
                usage["execution_count"] += 1
            else:
                usage["unknown_count"] += 1
        return usage

    async def current_lease_phase_counts(self, worker_id: str) -> dict[str, int]:
        """返回 Worker 当前 reservation、running 和未知租约数量。"""
        summary = await self.current_usage_summary(worker_id)
        return {
            "reserved": int(summary["reservation_count"]),
            "running": int(summary["execution_count"]),
            "unknown": int(summary["unknown_count"]),
        }

    async def reclaim_stale_reservations(self, *, max_age_seconds: int) -> int:
        """在锁保护下回收超过年龄阈值且仍处于 reserved 阶段的租约。"""
        reclaimed_count = 0
        threshold = max(int(max_age_seconds), 0)
        now = self.clock()

        for lease_key in await self.cache.scan_keys(f"{self.LEASE_KEY_PREFIX}*"):
            payload = await self.cache.get_json(lease_key)
            if not isinstance(payload, dict) or payload.get("phase") != "reserved":
                continue

            created_at = _parse_lease_timestamp(payload.get("created_at"))
            if created_at is None or (now - created_at).total_seconds() <= threshold:
                continue

            worker_id = str(payload.get("worker_id") or "").strip()
            if not worker_id:
                continue

            lock_key = self._lock_key(worker_id)
            lock_token = uuid4().hex
            if not await self.cache.set(
                lock_key,
                lock_token,
                ex=self.lock_ttl_seconds,
                nx=True,
            ):
                continue

            try:
                current = await self.cache.get_json(lease_key)
                if not isinstance(current, dict) or current.get("phase") != "reserved":
                    continue
                current_created_at = _parse_lease_timestamp(current.get("created_at"))
                if (
                    current_created_at is None
                    or (now - current_created_at).total_seconds() <= threshold
                ):
                    continue
                if await self.cache.delete(lease_key):
                    reclaimed_count += 1
            finally:
                await self.cache.delete_if_value(lock_key, lock_token)

        return reclaimed_count

    async def capacity_failure_reason(
        self,
        *,
        capability: WorkerCapability,
        request: ResourceRequest,
    ) -> str | None:
        """检查当前动态占用是否会拒绝一次资源请求。"""
        usage = await self.current_usage(capability.worker_id)
        return self._capacity_failure_reason(
            capability=capability,
            usage=usage,
            requested=self._requested_capacity(request),
        )

    @classmethod
    def _lease_key(cls, worker_id: str, lease_id: str) -> str:
        return f"{cls.LEASE_KEY_PREFIX}{worker_id}:{lease_id}"

    @classmethod
    def _lock_key(cls, worker_id: str) -> str:
        return f"{cls.LOCK_KEY_PREFIX}{worker_id}"

    @classmethod
    def _requested_capacity(cls, request: ResourceRequest) -> dict[str, float | int]:
        return {
            "cpu": float(request.cpu_limit or request.cpu or 0),
            "memory_gb": float(request.memory_gb or 0),
            "parallelism": max(int(request.parallelism or 0), 0),
            "gpu_count": max(int(request.gpu_count or 0), 0),
            "gpu_memory_mb": max(int(request.gpu_memory_mb or 0), 0),
        }

    @staticmethod
    def _capacity_failure_reason(
        *,
        capability: WorkerCapability,
        usage: dict[str, float | int],
        requested: dict[str, float | int],
    ) -> str | None:
        if (
            capability.cpu_capacity is not None
            and float(usage["cpu"]) + float(requested["cpu"]) > capability.cpu_capacity
        ):
            return "cpu_capacity_exhausted"
        if (
            capability.memory_capacity_gb is not None
            and float(usage["memory_gb"]) + float(requested["memory_gb"])
            > capability.memory_capacity_gb
        ):
            return "memory_capacity_exhausted"
        if (
            capability.parallelism is not None
            and int(usage["parallelism"]) + int(requested["parallelism"])
            > capability.parallelism
        ):
            return "parallelism_capacity_exhausted"
        return None

    @classmethod
    def lease_ttl_seconds(
        cls,
        request: ResourceRequest,
        ttl_seconds: int | None,
    ) -> int:
        if ttl_seconds is not None:
            return max(int(ttl_seconds), cls.MIN_LEASE_TTL_SECONDS)
        return max(int(request.timeout_sec or 0) + cls.MIN_LEASE_TTL_SECONDS, cls.MIN_LEASE_TTL_SECONDS)


async def release_task_resource_reservation(
    task: Any,
    *,
    reason: str,
    attempt_id: str | None = None,
    cache: CacheBackend | None = None,
) -> bool:
    """释放任务 dispatch reservation，并保留清理结果供任务详情展示。"""
    extra_data = task.extra_data if isinstance(getattr(task, "extra_data", None), dict) else {}
    dispatch = extra_data.get("dispatch")
    reservation = dispatch.get("resource_reservation") if isinstance(dispatch, dict) else None
    if not isinstance(reservation, dict):
        return False

    worker_id = str(reservation.get("worker_id") or "").strip()
    lease_id = str(reservation.get("lease_id") or "").strip()
    if not worker_id or not lease_id:
        return False
    if attempt_id is not None and lease_id != f"{task.id}:{attempt_id}":
        return False
    if reservation.get("status") in {"released", "not_found"}:
        return False

    released = False
    release_error: str | None = None
    try:
        backend = cache
        if backend is None:
            from app.cache import get_cache

            backend = get_cache()
        released = await WorkerResourceLeaseManager(cache=backend).release(
            worker_id=worker_id,
            lease_id=lease_id,
        )
    except Exception as exc:
        release_error = str(exc)
        logger.warning(
            "Failed to release resource reservation for task %s: %s",
            task.id,
            exc,
        )

    updated_reservation = {
        **{key: value for key, value in reservation.items() if key != "release_error"},
        "status": "release_failed" if release_error else "released",
        "release_result": "deleted" if released else "already_absent",
        "release_reason": reason,
        "released_at": utcnow().isoformat(),
    }
    if release_error:
        updated_reservation["release_error"] = release_error

    task.extra_data = {
        **extra_data,
        "dispatch": {
            **dispatch,
            "resource_reservation": updated_reservation,
        },
    }
    return True


def mark_task_resource_reservation_claimed(task: Any, *, worker_id: str) -> bool:
    """将任务 reservation 标记为已被目标 Worker 接管。"""
    extra_data = task.extra_data if isinstance(getattr(task, "extra_data", None), dict) else {}
    dispatch = extra_data.get("dispatch")
    reservation = dispatch.get("resource_reservation") if isinstance(dispatch, dict) else None
    if not isinstance(reservation, dict):
        return False
    if str(reservation.get("worker_id") or "").strip() != str(worker_id or "").strip():
        return False
    if reservation.get("status") in {"claimed", "released", "release_failed"}:
        return False

    task.extra_data = {
        **extra_data,
        "dispatch": {
            **dispatch,
            "resource_reservation": {
                **reservation,
                "status": "claimed",
                "claimed_at": utcnow().isoformat(),
            },
        },
    }
    return True


def _normalize_lease_phase(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"reserved", "running"}:
        return normalized
    return "running" if not normalized else "unknown"


def _normalize_scope_id(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _parse_lease_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
