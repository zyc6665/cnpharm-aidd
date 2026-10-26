"""配额核销的补扫循环（docs/04 §5.3 的「终态核销」兜底）。

为什么需要它
------------
核销挂在 ``TaskStateMachine.transition`` 的终态分支上，所有**经过状态机**的路径
都会被记上成本。但下面这些路径不经过：

* 升级前就已经落在终态的历史任务（那时还没有 ``cost`` 字段）；
* 远端结果补回、直接改库修数据、脚本批量改状态；
* 状态变更提交了但后续事务回滚（极端情况）。

漏掉它们的后果是「用量永久偏低」——配额看起来永远用不完，超额告警永远不响，
这个功能就等于只做了一半。所以必须有一个与业务路径无关的兜底。

为什么沿用 queue_timeout 的结构
-------------------------------
``app.services.queue_timeout`` 是仓库里刚修好的正确范式（步骤 13）。本模块逐行
照抄它的循环骨架，**特别是退出条件**：

* ``while not self._stop_event.is_set():`` 而不是 ``while True:``。``stop()`` 先
  set 事件再 ``cancel()``；如果循环只靠 cancel 退出，而单轮 sweep 恰好是纯计算
  （没有任何 ``await`` 挂起点），事件循环就没有机会投递 ``CancelledError``，
  ``await self._task`` 会永久挂住，CI 直接卡死 45 分钟。仓库踩过这个坑，
  ``test/test_project_quotas.py::test_loop_stop_returns_promptly_for_pure_compute_sweep``
  是它的回归用例。

单轮失败不退出循环：一次数据库抖动不该让进程内唯一的质量兜底停摆，
``logger.exception`` 留下痕迹后等下一个间隔重试。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Awaitable, Callable

from app.config import settings
from app.database.session import async_session_factory
from app.services.project_quotas import settle_finished_tasks

logger = logging.getLogger(__name__)


async def run_quota_settlement_once(*, batch_size: int | None = None) -> int:
    """跑一轮补核销，返回本轮核销条数（供主循环与手动运维调用）。

    自己开 session 并 commit：这是独立于任何请求的巡检动作，没有外部事务可依附。
    """
    limit = (
        int(batch_size)
        if batch_size is not None
        else int(settings.QUOTA_SETTLEMENT_BATCH_SIZE)
    )
    if limit <= 0:
        return 0
    async with async_session_factory() as db:
        return await settle_finished_tasks(db, limit=limit)


class QuotaSettlementLoop:
    """周期性补核销的后台循环（与 ``QueueTimeoutSweepLoop`` 同构）。"""

    def __init__(
        self,
        *,
        sweep: Callable[..., Awaitable[object]],
        interval_seconds: float,
    ) -> None:
        self._sweep = sweep
        self._interval_seconds = max(float(interval_seconds), 1.0)
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
            self._run(), name="quota-settlement-sweep-loop"
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
                logger.exception("配额核销巡检单轮执行失败")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval_seconds
                )
            except (TimeoutError, asyncio.TimeoutError):
                continue


def build_quota_settlement_loop() -> QuotaSettlementLoop | None:
    """按配置构造巡检循环；关闭时返回 ``None``，``main.py`` 据此跳过启停。"""
    if not settings.PROJECT_QUOTA_ENABLED:
        return None
    return QuotaSettlementLoop(
        sweep=run_quota_settlement_once,
        interval_seconds=settings.QUOTA_SETTLEMENT_INTERVAL_SECONDS,
    )


quota_settlement_loop = build_quota_settlement_loop()


__all__ = [
    "QuotaSettlementLoop",
    "build_quota_settlement_loop",
    "quota_settlement_loop",
    "run_quota_settlement_once",
]
