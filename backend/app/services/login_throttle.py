# backend/app/services/login_throttle.py
"""登录账户级锁定（username + IP）。

* 计数窗口 15 分钟，同一 ``username+IP`` 连续失败 5 次即锁定 15 分钟；
* 成功登录清零；
* **fail-closed**：计数后端（生产为 Redis）不可用时返回 503「认证服务暂不可用」，
  绝不放行——限流/锁定失效不能成为暴力破解的旁路。

刻意不改 ``middleware/rate_limit.py``（那是 IP 级的粗粒度限流，且由并行任务维护）。
"""

from __future__ import annotations

import logging
from typing import Optional

from app.cache.base import CacheBackend
from app.cache.factory import get_cache_backend
from app.common.exceptions import BusinessException

logger = logging.getLogger(__name__)

#: 失败阈值 / 计数窗口 / 锁定时长（秒）。
MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
LOCK_SECONDS = 15 * 60

_FAIL_PREFIX = "login:fail"
_LOCK_PREFIX = "login:lock"


def _normalize(username: Optional[str], ip: Optional[str]) -> tuple[str, str]:
    return (username or "").strip().lower(), (ip or "unknown").strip()


def _fail_key(username: str, ip: str) -> str:
    return f"{_FAIL_PREFIX}:{username}:{ip}"


def _lock_key(username: str, ip: str) -> str:
    return f"{_LOCK_PREFIX}:{username}:{ip}"


def _get_backend() -> CacheBackend:
    """返回计数后端；单测可 monkeypatch 本函数注入 fake。"""
    return get_cache_backend()


def _unavailable() -> BusinessException:
    return BusinessException(
        "认证服务暂不可用，请稍后再试", http_status=503, code=50301
    )


async def is_locked(
    username: Optional[str], ip: Optional[str], *, backend: Optional[CacheBackend] = None
) -> bool:
    """该 username+IP 当前是否处于锁定窗口。后端异常 -> 503（fail-closed）。"""
    user, addr = _normalize(username, ip)
    repo = backend or _get_backend()
    try:
        return bool(await repo.exists(_lock_key(user, addr)))
    except Exception as exc:  # noqa: BLE001 - 任何后端异常都必须 fail-closed
        logger.warning("登录锁定检查失败（fail-closed）: %s", exc)
        raise _unavailable() from exc


async def register_failure(
    username: Optional[str], ip: Optional[str], *, backend: Optional[CacheBackend] = None
) -> int:
    """记录一次失败；达到阈值则设置锁定键。返回当前窗口内失败次数。"""
    user, addr = _normalize(username, ip)
    repo = backend or _get_backend()
    try:
        key = _fail_key(user, addr)
        count = await repo.incr(key, 1)
        if count == 1:
            # 首次失败才设置窗口 TTL（memory/redis 的 incr 首次不自动带过期）。
            await repo.expire(key, WINDOW_SECONDS)
        if count >= MAX_FAILURES:
            await repo.set(_lock_key(user, addr), "1", expire=LOCK_SECONDS)
        return int(count)
    except Exception as exc:  # noqa: BLE001
        logger.warning("登录失败计数失败（fail-closed）: %s", exc)
        raise _unavailable() from exc


async def reset(
    username: Optional[str], ip: Optional[str], *, backend: Optional[CacheBackend] = None
) -> None:
    """登录成功后清零失败计数与锁定。"""
    user, addr = _normalize(username, ip)
    repo = backend or _get_backend()
    try:
        await repo.delete(_fail_key(user, addr))
        await repo.delete(_lock_key(user, addr))
    except Exception as exc:  # noqa: BLE001
        logger.warning("登录成功清零失败（fail-closed）: %s", exc)
        raise _unavailable() from exc


async def ensure_not_locked(
    username: Optional[str], ip: Optional[str], *, backend: Optional[CacheBackend] = None
) -> None:
    """锁定中 -> 抛 429；后端不可用 -> 抛 503。"""
    if await is_locked(username, ip, backend=backend):
        raise BusinessException(
            "登录失败次数过多，请 15 分钟后再试", http_status=429, code=42901
        )
