"""幂等表的过期清理循环（docs/04 §5.5 的 24h 保留期）。

结构完全照搬 ``app.services.upload_maintenance``：同样是「批量取 + 单轮一个事务」+
一个 ``asyncio`` 循环对象，由 ``create_app()`` 的 ``lifespan`` 启停。这里不新造
定时器框架，也不需要 ``celery beat``——幂等记录过期不清理只会让表慢慢变大，属于
「兜底运维」而不是业务关键路径，所以放在进程内。

为什么要清理
------------
``idempotency_keys`` 的每一行只在 TTL（默认 24h）内有用：过期后
``begin_request`` 会把它视为不存在并覆盖。留下的行不会造成功能错误，但会无限增长
（每个写请求一行，且带 ``response_body`` 快照）。保留 24h 是规格承诺，过期即删。

批量的意义
----------
一次 ``DELETE`` 扫掉几十万行会长时间持锁并拖慢写入。这里每轮最多删
``batch_size`` 行，跑不完就等下一个间隔继续——清理任务晚几分钟完成没有影响。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Awaitable, Callable

from app.config import settings
from app.database.session import async_session_factory
from app.services.idempotency import (
    DEFAULT_PURGE_BATCH_SIZE,
    purge_expired_idempotency_keys,
)

logger = logging.getLogger(__name__)


async def run_idempotency_sweep_once(
    *, batch_size: int = DEFAULT_PURGE_BATCH_SIZE
) -> int:
    """跑一轮清理，返回本轮删除的行数（供测试与手动运维调用）。"""
    async with async_session_factory() as db:
        return await purge_expired_idempotency_keys(db, batch_size=batch_size)


class IdempotencySweepLoop:
    """周期性清理过期幂等记录的后台循环（与 ``UploadSessionSweepLoop`` 同构）。"""

    def __init__(
        self,
        *,
        sweep: Callable[[], Awaitable[object]],
        interval_seconds: float,
    ) -> None:
        self._sweep = sweep
        self._interval_seconds = float(interval_seconds)
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run(), name="idempotency-key-sweep-loop"
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        # 退出条件必须写在 while 上，不能只靠 cancel()：`stop()` 会先 set 事件再
        # cancel，事件置位后 `wait_for` 立即返回，循环若继续转圈而 sweep 又是纯计算，
        # 事件循环就没有挂起点可以投递 CancelledError，`await self._task` 会永久挂住。
        while not self._stop_event.is_set():
            try:
                await self._sweep()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 单轮失败不能让循环退出
                logger.exception("幂等键清理任务单轮执行失败")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval_seconds
                )
            except (TimeoutError, asyncio.TimeoutError):
                continue


def build_idempotency_sweep_loop() -> IdempotencySweepLoop | None:
    """按配置构造清理循环；关闭时返回 ``None``，``main.py`` 据此跳过启停。"""
    if not settings.IDEMPOTENCY_SWEEP_ENABLED:
        return None
    return IdempotencySweepLoop(
        sweep=run_idempotency_sweep_once,
        interval_seconds=settings.IDEMPOTENCY_SWEEP_INTERVAL_SECONDS,
    )


idempotency_sweep_loop = build_idempotency_sweep_loop()


__all__ = [
    "IdempotencySweepLoop",
    "build_idempotency_sweep_loop",
    "idempotency_sweep_loop",
    "run_idempotency_sweep_once",
]
