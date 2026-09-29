"""远程 API 服务的共享容量租约。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from app.cache.base import CacheBackend
from app.common.time import utcnow


REMOTE_CAPACITY_MODES = frozenset({"unmanaged", "static"})
MIN_REMOTE_LEASE_TTL_SECONDS = 60
HEARTBEAT_INTERVAL_SECONDS = 30


@dataclass(frozen=True)
class RemoteCapacityPolicy:
    """ToolVersion 声明的远程服务容量策略。"""

    mode: str
    capacity_group: str | None = None
    max_inflight: int | None = None
    lease_ttl_seconds: int | None = None

    @property
    def managed(self) -> bool:
        return self.mode == "static" and self.capacity_group is not None and self.max_inflight is not None


@dataclass(frozen=True)
class RemoteCapacityLeaseDecision:
    """一次远程服务容量申请结果。"""

    acquired: bool
    capacity_group: str
    lease_id: str
    slot: int | None = None
    token: str | None = None
    reason: str | None = None


class RemoteCapacityLeaseManager:
    """使用固定槽位和 TTL 限制共享远程 API 的并发数。"""

    SLOT_KEY_PREFIX = "remote:capacity:slot:"
    MARKER_KEY_PREFIX = "remote:capacity:lease:"
    GROUP_LIMIT_KEY_PREFIX = "remote:capacity:limit:"
    LOCK_KEY_PREFIX = "remote:capacity:lock:"

    def __init__(self, *, cache: CacheBackend) -> None:
        self.cache = cache

    async def acquire(
        self,
        *,
        policy: RemoteCapacityPolicy,
        lease_id: str,
        timeout_sec: int,
    ) -> RemoteCapacityLeaseDecision:
        if not policy.managed:
            return RemoteCapacityLeaseDecision(
                acquired=True,
                capacity_group=policy.capacity_group or "",
                lease_id=lease_id,
            )

        group = _normalize_group(policy.capacity_group)
        normalized_lease_id = str(lease_id or "").strip()
        if not group or not normalized_lease_id:
            return RemoteCapacityLeaseDecision(
                acquired=False,
                capacity_group=group,
                lease_id=normalized_lease_id,
                reason="invalid_remote_capacity_identity",
            )

        ttl = _lease_ttl(policy, timeout_sec)
        marker_key = self._marker_key(group, normalized_lease_id)
        lock_key = self._lock_key(group)
        lock_token = _lease_token(group, normalized_lease_id, -1)
        if not await self.cache.set(lock_key, lock_token, ex=10, nx=True):
            return RemoteCapacityLeaseDecision(
                acquired=False,
                capacity_group=group,
                lease_id=normalized_lease_id,
                reason="remote_capacity_lock_busy",
            )

        try:
            configured_limit = str(policy.max_inflight)
            await self.cache.set(
                self._group_limit_key(group), configured_limit, nx=True
            )
            registered_limit = await self.cache.get(self._group_limit_key(group))
            if str(registered_limit) != configured_limit:
                previous_limit = _positive_int(registered_limit)
                if previous_limit is None:
                    return RemoteCapacityLeaseDecision(
                        acquired=False,
                        capacity_group=group,
                        lease_id=normalized_lease_id,
                        reason="remote_capacity_limit_mismatch",
                    )
                occupied = any(
                    [
                        await self.cache.exists(self._slot_key(group, slot))
                        for slot in range(max(previous_limit, policy.max_inflight or 0))
                    ]
                )
                if occupied:
                    return RemoteCapacityLeaseDecision(
                        acquired=False,
                        capacity_group=group,
                        lease_id=normalized_lease_id,
                        reason="remote_capacity_limit_mismatch",
                    )
                await self.cache.set(
                    self._group_limit_key(group), configured_limit
                )

            existing = await self.cache.get(marker_key)
            if isinstance(existing, str):
                slot, token = _parse_marker(existing)
                if slot is not None and token:
                    refreshed = await self.cache.expire_if_value(
                        self._slot_key(group, slot), token, ttl
                    )
                    if refreshed:
                        await self.cache.expire(marker_key, ttl)
                        return RemoteCapacityLeaseDecision(
                            acquired=True,
                            capacity_group=group,
                            lease_id=normalized_lease_id,
                            slot=slot,
                            token=token,
                        )

            for slot in range(policy.max_inflight or 0):
                token = _lease_token(group, normalized_lease_id, slot)
                if not await self.cache.set(
                    self._slot_key(group, slot), token, ex=ttl, nx=True
                ):
                    continue

                await self.cache.set(marker_key, f"{slot}:{token}", ex=ttl)
                return RemoteCapacityLeaseDecision(
                    acquired=True,
                    capacity_group=group,
                    lease_id=normalized_lease_id,
                    slot=slot,
                    token=token,
                )

            return RemoteCapacityLeaseDecision(
                acquired=False,
                capacity_group=group,
                lease_id=normalized_lease_id,
                reason="remote_capacity_exhausted",
            )
        finally:
            await self.cache.delete_if_value(lock_key, lock_token)

    async def heartbeat(
        self,
        *,
        decision: RemoteCapacityLeaseDecision,
        ttl_seconds: int,
    ) -> bool:
        if not decision.acquired or decision.slot is None or not decision.token:
            return True
        ttl = max(int(ttl_seconds), MIN_REMOTE_LEASE_TTL_SECONDS)
        slot_refreshed = await self.cache.expire_if_value(
            self._slot_key(decision.capacity_group, decision.slot),
            decision.token,
            ttl,
        )
        if slot_refreshed:
            await self.cache.expire(
                self._marker_key(decision.capacity_group, decision.lease_id), ttl
            )
        return slot_refreshed

    async def release(self, *, decision: RemoteCapacityLeaseDecision) -> bool:
        if not decision.acquired or decision.slot is None or not decision.token:
            return True
        released = await self.cache.delete_if_value(
            self._slot_key(decision.capacity_group, decision.slot), decision.token
        )
        await self.cache.delete_if_value(
            self._marker_key(decision.capacity_group, decision.lease_id),
            f"{decision.slot}:{decision.token}",
        )
        return released

    @classmethod
    def _slot_key(cls, group: str, slot: int) -> str:
        return f"{cls.SLOT_KEY_PREFIX}{_group_key(group)}:{slot}"

    @classmethod
    def _marker_key(cls, group: str, lease_id: str) -> str:
        return f"{cls.MARKER_KEY_PREFIX}{_group_key(group)}:{_group_key(lease_id)}"

    @classmethod
    def _group_limit_key(cls, group: str) -> str:
        return f"{cls.GROUP_LIMIT_KEY_PREFIX}{_group_key(group)}"

    @classmethod
    def _lock_key(cls, group: str) -> str:
        return f"{cls.LOCK_KEY_PREFIX}{_group_key(group)}"


def remote_capacity_policy(config: dict[str, Any] | None) -> RemoteCapacityPolicy:
    """从工具配置读取容量策略；缺省策略不接管远程服务容量。"""
    raw = config.get("capacity_policy") if isinstance(config, dict) else None
    if not isinstance(raw, dict):
        return RemoteCapacityPolicy(mode="unmanaged")
    mode = str(raw.get("mode") or "unmanaged").strip().lower()
    return RemoteCapacityPolicy(
        mode=mode,
        capacity_group=_normalize_group(raw.get("capacity_group")),
        max_inflight=_positive_int(raw.get("max_inflight")),
        lease_ttl_seconds=_positive_int(raw.get("lease_ttl_sec")),
    )


def validate_remote_capacity_policy(value: Any) -> list[str]:
    """返回 remote_api.capacity_policy 的配置错误。"""
    if value is None:
        return []
    if not isinstance(value, dict):
        return ["capacity_policy must be an object"]

    mode = str(value.get("mode") or "unmanaged").strip().lower()
    errors: list[str] = []
    if mode not in REMOTE_CAPACITY_MODES:
        errors.append(f"capacity_policy.mode must be one of {sorted(REMOTE_CAPACITY_MODES)}")
        return errors

    group = value.get("capacity_group")
    if group is not None and (not isinstance(group, str) or not group.strip() or len(group.strip()) > 120):
        errors.append("capacity_policy.capacity_group must be a non-empty string of at most 120 characters")

    max_inflight = value.get("max_inflight")
    if mode == "static" and (
        isinstance(max_inflight, bool)
        or not isinstance(max_inflight, int)
        or max_inflight < 1
    ):
        errors.append("capacity_policy.max_inflight must be a positive integer for static mode")
    if mode == "static" and (not isinstance(group, str) or not group.strip()):
        errors.append("capacity_policy.capacity_group is required for static mode")

    lease_ttl = value.get("lease_ttl_sec")
    if lease_ttl is not None and (
        isinstance(lease_ttl, bool) or not isinstance(lease_ttl, int) or lease_ttl < MIN_REMOTE_LEASE_TTL_SECONDS
    ):
        errors.append(
            f"capacity_policy.lease_ttl_sec must be an integer >= {MIN_REMOTE_LEASE_TTL_SECONDS}"
        )
    return errors


def _lease_ttl(policy: RemoteCapacityPolicy, timeout_sec: int) -> int:
    configured = policy.lease_ttl_seconds
    if configured is not None:
        return max(configured, MIN_REMOTE_LEASE_TTL_SECONDS)
    return max(int(timeout_sec or 0) + MIN_REMOTE_LEASE_TTL_SECONDS, MIN_REMOTE_LEASE_TTL_SECONDS)


def _normalize_group(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized[:120] or None


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _as_slot(value: Any) -> int | None:
    try:
        slot = int(value)
    except (TypeError, ValueError):
        return None
    return slot if slot >= 0 else None


def _parse_marker(value: str) -> tuple[int | None, str | None]:
    raw_slot, separator, token = value.partition(":")
    if not separator:
        return None, None
    return _as_slot(raw_slot), token or None


def _group_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _lease_token(group: str, lease_id: str, slot: int) -> str:
    payload = f"{group}:{lease_id}:{slot}:{utcnow().timestamp()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
