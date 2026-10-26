"""过期分片上传会话的清理任务（docs/04 §5.8）。

为什么需要后台任务
------------------
``upload_sessions.expires_at`` 只在三个业务入口（上报分片、合并、取消）被检查。
用户创建完会话就直接关页面时，没有任何入口会再碰到这条记录——它既不会变成
``EXPIRED``，暂存分片也会一直占着本地盘或对象存储。线上这类「僵尸会话」只会
单调增长，必须有一个与用户行为无关的兜底。

设计取舍
--------
* **批量 + 单条事务**：每选中一条就独立提交，一条失败不影响其它条。会话数量级
  很小（一个项目一天不过几十条），不需要批量提交换吞吐。
* **先置状态再删字节**：先把 ``state`` 写成 ``EXPIRED`` 并提交，再清暂存。顺序
  反过来会出现「字节删了但状态还是 UPLOADING」，用户重试时会拿到一个永远合并不
  了的会话。反之最坏是「状态过期了但暂存还在」，由下一轮清理接着删。
* **只碰活跃态**：``COMPLETED``/``ABORTED``/``EXPIRED`` 一律跳过，避免误删已完成
  上传的中间产物（那时暂存本来就该没了）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.config import settings
from app.database.session import async_session_factory
from app.files.part_staging import build_part_staging
from app.models.uploads import UploadSession

logger = logging.getLogger(__name__)

#: 只清理这两种状态：其余状态要么已结束，要么已被别的路径处理过。
SWEEPABLE_STATES = ("INITIATED", "UPLOADING")

#: 单轮最多处理多少条；防止某次积压把一轮跑成几分钟。
DEFAULT_SWEEP_BATCH_SIZE = 200


async def expire_stale_upload_sessions(
    db: AsyncSession,
    *,
    batch_size: int = DEFAULT_SWEEP_BATCH_SIZE,
    now=None,
) -> int:
    """把到期的活跃会话置 ``EXPIRED`` 并清掉暂存分片，返回处理条数。"""
    moment = now or utcnow()
    result = await db.execute(
        select(UploadSession)
        .where(
            UploadSession.state.in_(SWEEPABLE_STATES),
            UploadSession.expires_at.is_not(None),
            UploadSession.expires_at <= moment,
        )
        .order_by(UploadSession.expires_at.asc())
        .limit(max(int(batch_size), 0))
    )
    sessions = list(result.scalars().all())
    if not sessions:
        return 0

    staging = build_part_staging()
    processed = 0
    for session in sessions:
        session_id = str(session.id)
        try:
            # 先落状态（可查证），再删字节（尽力而为）。
            session.state = "EXPIRED"
            await db.commit()
        except Exception:  # noqa: BLE001 - 单条失败不阻塞整批
            await db.rollback()
            logger.exception("标记上传会话过期失败: %s", session_id)
            continue
        try:
            await staging.discard(session_id)
        except Exception:  # noqa: BLE001 - 清理失败留给下一轮
            logger.warning("清理过期会话的暂存分片失败: %s", session_id, exc_info=True)
            continue
        processed += 1
    if processed:
        logger.info("已清理 %s 个过期分片上传会话", processed)
    return processed


async def run_upload_sweep_once() -> int:
    """在一次短生命周期会话里跑一轮清理（供后台循环调用）。"""
    async with async_session_factory() as db:
        return await expire_stale_upload_sessions(db)


class UploadSessionSweepLoop:
    """周期性清理过期上传会话。

    与 ``WorkflowReconcileLoop`` 同一形状（``start``/``stop``/``_run``），但刻意
    共用一个基类会逼两个领域互相 import；重复这 40 行比制造耦合更划算。
    """

    def __init__(
        self,
        *,
        sweep: Callable[[], Awaitable[object]],
        interval_seconds: float,
    ) -> None:
        self._sweep = sweep
        self._interval_seconds = max(float(interval_seconds), 1.0)
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    @property
    def is_running(self) -> bool:
        return bool(self._task and not self._task.done())

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run(), name="upload-session-sweep-loop"
        )

    async def stop(self) -> None:
        if not self._task:
            return
        if self._stop_event:
            self._stop_event.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self._sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("过期上传会话清理失败")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval_seconds
                )
            except TimeoutError:
                continue


def build_upload_sweep_loop() -> UploadSessionSweepLoop | None:
    """按配置构造清理循环；关闭时返回 ``None``，调用方无需判断。"""
    if not settings.UPLOAD_SWEEP_ENABLED:
        return None
    return UploadSessionSweepLoop(
        sweep=run_upload_sweep_once,
        interval_seconds=float(settings.UPLOAD_SWEEP_INTERVAL_SECONDS),
    )


upload_sweep_loop = build_upload_sweep_loop()


__all__ = [
    "DEFAULT_SWEEP_BATCH_SIZE",
    "SWEEPABLE_STATES",
    "UploadSessionSweepLoop",
    "build_upload_sweep_loop",
    "expire_stale_upload_sessions",
    "run_upload_sweep_once",
    "upload_sweep_loop",
]
