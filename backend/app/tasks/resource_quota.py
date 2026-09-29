"""用户与项目级资源并发配额。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.cache.base import CacheBackend


class ResourceQuotaManager:
    """使用缓存租约汇总资源占用，按用户和项目做软隔离。"""

    LEASE_KEY_PREFIX = "worker:resource:lease:"
    LOCK_KEY_PREFIX = "worker:resource:quota:lock:"
    REJECTION_KEY_PREFIX = "worker:resource:quota:rejection:"

    def __init__(
        self,
        *,
        cache: CacheBackend,
        user_max_cpu: float | None = None,
        user_max_memory_gb: float | None = None,
        user_max_parallelism: int | None = None,
        project_max_cpu: float | None = None,
        project_max_memory_gb: float | None = None,
        project_max_parallelism: int | None = None,
        lock_ttl_seconds: int = 10,
        rejection_ttl_seconds: int = 86400,
    ) -> None:
        self.cache = cache
        self.user_max_cpu = _optional_positive_float(user_max_cpu)
        self.user_max_memory_gb = _optional_positive_float(user_max_memory_gb)
        self.user_max_parallelism = _optional_positive_int(user_max_parallelism)
        self.project_max_cpu = _optional_positive_float(project_max_cpu)
        self.project_max_memory_gb = _optional_positive_float(project_max_memory_gb)
        self.project_max_parallelism = _optional_positive_int(project_max_parallelism)
        self.lock_ttl_seconds = max(int(lock_ttl_seconds), 1)
        self.rejection_ttl_seconds = max(int(rejection_ttl_seconds), 1)

    @property
    def enabled(self) -> bool:
        return (
            self.user_max_cpu is not None
            or self.user_max_memory_gb is not None
            or self.user_max_parallelism is not None
            or self.project_max_cpu is not None
            or self.project_max_memory_gb is not None
            or self.project_max_parallelism is not None
        )

    async def acquire_scope_locks(
        self,
        *,
        user_id: str | None,
        project_id: str | None,
    ) -> list[tuple[str, str]] | None:
        """按稳定顺序申请 scope 锁，避免跨 scope 死锁。"""
        lock_keys = self._scope_lock_keys(user_id=user_id, project_id=project_id)
        locks: list[tuple[str, str]] = []
        for key in lock_keys:
            token = uuid4().hex
            if await self.cache.set(
                key,
                token,
                ex=self.lock_ttl_seconds,
                nx=True,
            ):
                locks.append((key, token))
                continue

            await self.release_scope_locks(locks)
            return None
        return locks

    async def release_scope_locks(self, locks: list[tuple[str, str]]) -> None:
        for key, token in locks:
            await self.cache.delete_if_value(key, token)

    async def capacity_failure_reason(
        self,
        *,
        user_id: str | None,
        project_id: str | None,
        requested_cpu: float = 0.0,
        requested_memory_gb: float = 0.0,
        requested_parallelism: int,
    ) -> str | None:
        """检查一次新增租约是否超过用户或项目资源配额。"""
        usage = await self.current_usage(user_id=user_id, project_id=project_id)
        requested = {
            "cpu": max(float(requested_cpu), 0.0),
            "memory_gb": max(float(requested_memory_gb), 0.0),
            "parallelism": max(int(requested_parallelism), 0),
        }
        checks = (
            ("user", user_id, "cpu", self.user_max_cpu),
            ("user", user_id, "memory_gb", self.user_max_memory_gb),
            ("user", user_id, "parallelism", self.user_max_parallelism),
            ("project", project_id, "cpu", self.project_max_cpu),
            ("project", project_id, "memory_gb", self.project_max_memory_gb),
            ("project", project_id, "parallelism", self.project_max_parallelism),
        )
        for scope_type, scope_id, dimension, limit in checks:
            if limit is None or not _normalize_scope_id(scope_id):
                continue
            usage_key = f"{scope_type}_{dimension}"
            if float(usage[usage_key]) + requested[dimension] > float(limit):
                reason_dimension = "memory" if dimension == "memory_gb" else dimension
                reason = f"{scope_type}_{reason_dimension}_quota_exhausted"
                await self.record_rejection(
                    scope_type=scope_type,
                    scope_id=str(scope_id),
                    reason=reason,
                )
                return reason
        return None

    async def current_usage(
        self,
        *,
        user_id: str | None,
        project_id: str | None,
    ) -> dict[str, float | int]:
        """汇总当前租约中指定用户和项目的资源占用。"""
        normalized_user_id = _normalize_scope_id(user_id)
        normalized_project_id = _normalize_scope_id(project_id)
        usage: dict[str, float | int] = {
            "user_cpu": 0.0,
            "user_memory_gb": 0.0,
            "user_parallelism": 0,
            "project_cpu": 0.0,
            "project_memory_gb": 0.0,
            "project_parallelism": 0,
        }
        if not normalized_user_id and not normalized_project_id:
            return usage

        for key in await self.cache.scan_keys(f"{self.LEASE_KEY_PREFIX}*"):
            payload = await self.cache.get_json(key)
            if not isinstance(payload, dict):
                continue
            cpu = _as_float(payload.get("cpu"))
            memory_gb = _as_float(payload.get("memory_gb"))
            parallelism = _as_int(payload.get("parallelism"))
            if normalized_user_id and payload.get("user_id") == normalized_user_id:
                usage["user_cpu"] += cpu
                usage["user_memory_gb"] += memory_gb
                usage["user_parallelism"] += parallelism
            if normalized_project_id and payload.get("project_id") == normalized_project_id:
                usage["project_cpu"] += cpu
                usage["project_memory_gb"] += memory_gb
                usage["project_parallelism"] += parallelism
        return usage

    async def current_scope_snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        """返回管理员资源页需要的用户/项目配额快照。"""
        snapshot: dict[str, dict[str, dict[str, Any]]] = {
            "user": {},
            "project": {},
        }
        for key in await self.cache.scan_keys(f"{self.LEASE_KEY_PREFIX}*"):
            payload = await self.cache.get_json(key)
            if not isinstance(payload, dict):
                continue
            usage = {
                "cpu": _as_float(payload.get("cpu")),
                "memory_gb": _as_float(payload.get("memory_gb")),
                "parallelism": _as_int(payload.get("parallelism")),
            }
            gpu_usage = {
                "count": _as_int(payload.get("gpu_count")),
                "memory_mb": _as_int(payload.get("gpu_memory_mb")),
            }
            for scope_type, field in (("user", "user_id"), ("project", "project_id")):
                scope_id = _normalize_scope_id(payload.get(field))
                if not scope_id:
                    continue
                entry = snapshot[scope_type].setdefault(
                    scope_id,
                    {"usage": _empty_usage(), "rejection_counts": {}},
                )
                _add_usage(entry["usage"], usage)
                entry.setdefault("gpu_usage", {"count": 0, "memory_mb": 0})
                entry["gpu_usage"]["count"] += gpu_usage["count"]
                entry["gpu_usage"]["memory_mb"] += gpu_usage["memory_mb"]

        for scope_type, limits in self._scope_limits().items():
            for scope_id in await self._scope_ids_with_rejections(scope_type):
                snapshot[scope_type].setdefault(
                    scope_id,
                    {
                        "usage": _empty_usage(),
                        "gpu_usage": {"count": 0, "memory_mb": 0},
                        "rejection_counts": {},
                    },
                )
            for scope_id, entry in snapshot[scope_type].items():
                entry["limits"] = dict(limits)
                entry["rejection_counts"] = await self._rejection_counts(
                    scope_type=scope_type,
                    scope_id=scope_id,
                )
        return snapshot

    async def record_rejection(
        self,
        *,
        scope_type: str,
        scope_id: str,
        reason: str,
    ) -> None:
        """记录运行期拒绝原因，供管理端诊断使用。"""
        normalized_scope_id = _normalize_scope_id(scope_id)
        if scope_type not in {"user", "project"} or not normalized_scope_id:
            return
        key = self._rejection_key(scope_type, normalized_scope_id, reason)
        await self.cache.incr(key)
        await self.cache.expire(key, self.rejection_ttl_seconds)

    def _scope_lock_keys(
        self,
        *,
        user_id: str | None,
        project_id: str | None,
    ) -> list[str]:
        scopes: set[str] = set()
        normalized_user_id = _normalize_scope_id(user_id)
        normalized_project_id = _normalize_scope_id(project_id)
        if self._has_user_quota() and normalized_user_id:
            scopes.add(self._scope_lock_key("user", normalized_user_id))
        if self._has_project_quota() and normalized_project_id:
            scopes.add(self._scope_lock_key("project", normalized_project_id))
        return sorted(scopes)

    @classmethod
    def _scope_lock_key(cls, scope_type: str, scope_id: str) -> str:
        return f"{cls.LOCK_KEY_PREFIX}{scope_type}:{scope_id}"

    def _scope_limits(self) -> dict[str, dict[str, float | int | None]]:
        return {
            "user": {
                "cpu": self.user_max_cpu,
                "memory_gb": self.user_max_memory_gb,
                "parallelism": self.user_max_parallelism,
            },
            "project": {
                "cpu": self.project_max_cpu,
                "memory_gb": self.project_max_memory_gb,
                "parallelism": self.project_max_parallelism,
            },
        }

    def _has_user_quota(self) -> bool:
        return any(value is not None for value in self._scope_limits()["user"].values())

    def _has_project_quota(self) -> bool:
        return any(value is not None for value in self._scope_limits()["project"].values())

    async def _scope_ids_with_rejections(self, scope_type: str) -> set[str]:
        prefix = f"{self.REJECTION_KEY_PREFIX}{scope_type}:"
        ids: set[str] = set()
        for key in await self.cache.scan_keys(f"{prefix}*"):
            remainder = key[len(prefix):]
            scope_id = remainder.split(":", 1)[0]
            if scope_id:
                ids.add(scope_id)
        return ids

    async def _rejection_counts(self, *, scope_type: str, scope_id: str) -> dict[str, int]:
        prefix = self._rejection_key(scope_type, scope_id, "")
        counts: dict[str, int] = {}
        for key in await self.cache.scan_keys(f"{prefix}*"):
            reason = key[len(prefix):]
            if reason:
                counts[reason] = _as_int(await self.cache.get(key))
        return counts

    def _rejection_key(self, scope_type: str, scope_id: str, reason: str) -> str:
        return f"{self.REJECTION_KEY_PREFIX}{scope_type}:{scope_id}:{reason}"


def build_resource_quota_manager(cache: CacheBackend) -> ResourceQuotaManager | None:
    """从运行时配置创建配额管理器；未开启时返回 None。"""
    from app.config import settings

    if not settings.RESOURCE_SCOPE_QUOTA_ENABLED:
        return None
    manager = ResourceQuotaManager(
        cache=cache,
        user_max_cpu=settings.RESOURCE_USER_MAX_CPU,
        user_max_memory_gb=settings.RESOURCE_USER_MAX_MEMORY_GB,
        user_max_parallelism=settings.RESOURCE_USER_MAX_PARALLELISM,
        project_max_cpu=settings.RESOURCE_PROJECT_MAX_CPU,
        project_max_memory_gb=settings.RESOURCE_PROJECT_MAX_MEMORY_GB,
        project_max_parallelism=settings.RESOURCE_PROJECT_MAX_PARALLELISM,
        lock_ttl_seconds=settings.RESOURCE_QUOTA_LOCK_TTL_SECONDS,
        rejection_ttl_seconds=settings.RESOURCE_QUOTA_REJECTION_TTL_SECONDS,
    )
    return manager if manager.enabled else None


def _normalize_scope_id(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    normalized = int(value)
    return normalized if normalized > 0 else None


def _optional_positive_float(value: Any) -> float | None:
    if value is None:
        return None
    normalized = float(value)
    return normalized if normalized > 0 else None


def _empty_usage() -> dict[str, float | int]:
    return {"cpu": 0.0, "memory_gb": 0.0, "parallelism": 0}


def _add_usage(target: dict[str, float | int], source: dict[str, float | int]) -> None:
    target["cpu"] += float(source["cpu"])
    target["memory_gb"] += float(source["memory_gb"])
    target["parallelism"] += int(source["parallelism"])


def _as_float(value: Any) -> float:
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0
