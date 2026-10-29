"""无引用 ``File`` 的定期回收（计划 §5.6）。

产物上传/版本写入会先落一条 ``files`` 行；版本被删除或项目被删除后，这些行可能
不再被任何 ``artifact_version_files`` 引用。只删版本行会让对象存储里留下孤儿
对象（本地盘同理），长期占用空间且无法从元数据反查。本任务补上兜底：

* **只回收同时满足三个条件的 File**：``source_type == "tool_output"``（用户上传/
  系统文件一律不动）、创建时间超过 ``ARTIFACT_GC_RETENTION_DAYS``，且没有任何
  ``artifact_version_files.file_id`` 指向它。30 天保留期给「先删版本、之后再恢复」
  留出窗口。
* **逐条事务**：一条对象删不掉（对象存储超时、权限）只记录并继续，绝不让整批
  回滚。否则一条坏对象会让其余所有可回收对象永远清不掉。
* **先删对象再删行**：顺序反过来会出现「行没了但对象还在」，之后再也无法从库里
  枚举到该对象；留着行至少下一轮还能重试。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import Text, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_cache
from app.common.time import utcnow
from app.config import settings
from app.database.session import async_session_factory
from app.files.file_records import delete_stored_content
from app.models.artifacts import ArtifactVersionFile
from app.models.files import File, FileSourceType
from app.models.tasks import TaskInput, TaskOutput

logger = logging.getLogger(__name__)

ARTIFACT_GC_LOCK_KEY = "artifact:gc:lock"

#: 单轮最多处理多少条；防止某次积压把一轮跑成几分钟。
DEFAULT_GC_BATCH_SIZE = 200


async def _is_still_referenced(db: AsyncSession, file_id: str) -> bool:
    """File 是否仍被任务输入/输出引用。

    ``TaskInput.file_ids`` / ``TaskOutput.file_ids`` 是 JSON 数组，没有外键，
    数据库层拦不住 File 被删；必须在 Python 侧逐条查。用 ``CAST(json AS TEXT)
    LIKE '%"<id>"%'`` 而不是 ``json_each``，SQLite 与 PostgreSQL 都能跑。
    """
    for model in (TaskInput, TaskOutput):
        matched = await db.scalar(
            select(model.id)
            .where(cast(model.file_ids, Text).like(f'%"{file_id}"%'))
            .limit(1)
        )
        if matched is not None:
            return True
    return False


async def collect_orphan_files(
    db: AsyncSession,
    *,
    retention_days: int | None = None,
    batch_size: int = DEFAULT_GC_BATCH_SIZE,
    now=None,
) -> int:
    """删除「无版本引用且超过保留期」的 File 对象与行，返回成功条数。"""
    days = settings.ARTIFACT_GC_RETENTION_DAYS if retention_days is None else retention_days
    cutoff = (now or utcnow()) - timedelta(days=max(int(days), 0))
    result = await db.execute(
        select(File)
        .where(
            File.source_type == FileSourceType.TOOL_OUTPUT.value,
            File.created_at < cutoff,
            ~select(ArtifactVersionFile.id)
            .where(ArtifactVersionFile.file_id == File.id)
            .exists(),
        )
        .order_by(File.created_at.asc(), File.id.asc())
        .limit(max(int(batch_size), 0))
    )
    records = list(result.scalars().all())
    if not records:
        return 0
    # 先取出 id：单条失败时 rollback 会 expire 整批 ORM 实例，
    # 之后不能再依赖这些对象的属性，逐条按 id 重新 get。
    file_ids = [str(record.id) for record in records]

    removed = 0
    for file_id in file_ids:
        record = await db.get(File, file_id)
        if record is None:
            continue
        try:
            if await _is_still_referenced(db, file_id):
                logger.debug("跳过仍被任务引用的 File: %s", file_id)
                continue
            # 先删对象（可重试），再删行（不可重试）。
            await delete_stored_content(record)
            await db.delete(record)
            await db.commit()
        except Exception:  # noqa: BLE001 - 单条失败不阻塞整批
            await db.rollback()
            logger.exception("回收无引用 File 失败: %s", file_id)
            continue
        removed += 1
    if removed:
        logger.info("已回收 %s 个无引用 File", removed)
    return removed


async def run_artifact_gc_once() -> int:
    """抢到选主锁后跑一轮 GC；没抢到说明别的副本在跑，直接跳过。"""
    cache = get_cache()
    lock_token = uuid4().hex
    # TTL 至少覆盖一轮默认间隔；GC 单轮漏锁最坏是重复删除，删除本身幂等。
    lock_ttl = max(int(settings.ARTIFACT_GC_INTERVAL_SECONDS), 600)
    acquired = await cache.set(
        ARTIFACT_GC_LOCK_KEY,
        lock_token,
        ex=lock_ttl,
        nx=True,
    )
    if not acquired:
        logger.debug("Skip artifact GC because another instance owns the lock")
        return 0
    try:
        async with async_session_factory() as db:
            return await collect_orphan_files(db)
    finally:
        await cache.delete_if_value(ARTIFACT_GC_LOCK_KEY, lock_token)


class ArtifactGcLoop:
    """周期性回收无引用 File（与 ``UploadSessionSweepLoop`` 同形状）。"""

    def __init__(
        self,
        *,
        sweep,
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
        self._task = asyncio.create_task(self._run(), name="artifact-gc-loop")

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
        # 绝不写 ``while True``：本仓库曾因此让 CI 挂死 45 分钟。
        while not self._stop_event.is_set():
            try:
                await self._sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("无引用 File 回收失败")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval_seconds
                )
            except TimeoutError:
                continue


def build_artifact_gc_loop() -> ArtifactGcLoop | None:
    """按配置构造 GC 循环；关闭时返回 ``None``。"""
    if not settings.ARTIFACT_GC_ENABLED:
        return None
    return ArtifactGcLoop(
        sweep=run_artifact_gc_once,
        interval_seconds=float(settings.ARTIFACT_GC_INTERVAL_SECONDS),
    )


artifact_gc_loop = build_artifact_gc_loop()


__all__ = [
    "ARTIFACT_GC_LOCK_KEY",
    "DEFAULT_GC_BATCH_SIZE",
    "ArtifactGcLoop",
    "artifact_gc_loop",
    "build_artifact_gc_loop",
    "collect_orphan_files",
    "run_artifact_gc_once",
]
