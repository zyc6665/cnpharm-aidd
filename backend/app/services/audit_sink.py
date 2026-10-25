"""Durable audit sink: rotate the JSON file trail into the ``audit_logs`` table.

``app.logging.audit`` already emits every event as a structured record, but until
step 7 the only destination was a rotating file — unqueryable from the console
(docs/06 P-38) and impossible to join to projects or tasks. ``AuditLogger`` has
carried an ``enable_db_logging`` + ``db_writer`` hook since it was written; this
module is the writer that hook was waiting for.

Two design constraints decide the shape:

* **Audit must never block or break business code** (docs/04 §3.2.2: 审计日志为
  最终一致，写入失败不阻断业务). ``AuditLogger`` calls ``db_writer`` synchronously
  from inside request handlers, so the writer must not await. It enqueues instead,
  and a single background task drains the queue with its own session.
* **Dropping is preferable to stalling.** If the queue is full the event is
  dropped with a warning rather than applying back-pressure to the request path.

The file trail stays enabled: it is the only record that survives a database
outage, and the two destinations are compared during acceptance (docs/12
TC-NFR-04).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.logging.audit import AuditEvent

logger = logging.getLogger(__name__)

#: Bounded so a burst cannot exhaust memory; see the module docstring for why
#: dropping beats blocking.
DEFAULT_QUEUE_SIZE = 2000


def _upper(value: str | None) -> str | None:
    return value.upper() if value else value


def event_to_row(event: AuditEvent) -> dict[str, Any]:
    """Map an ``AuditEvent`` onto the ``audit_logs`` column set.

    ``actor`` is the username snapshot (docs/04 §3 note 1): the trail must stay
    readable after the user is renamed or disabled, so it never depends on a join.
    """
    detail = dict(event.changes or {})
    if event.reason:
        detail["reason"] = event.reason
    if event.duration_ms is not None:
        detail["durationMs"] = event.duration_ms
    if event.session_id:
        detail["sessionId"] = event.session_id
    if event.user_role:
        detail["userRole"] = event.user_role
    if event.extra:
        detail.update(event.extra)

    return {
        "id": event.id,
        "actor": event.user_email or event.user_id or "anonymous",
        "actor_id": event.user_id,
        # docs/04 §5.4 用大写枚举值（LOGIN/READ/CREATE…）描述这两列，审计员按文档
        # 检索时不希望再猜大小写，所以入库时统一转大写；`AuditAction` 的
        # `.value` 是历史留下的小写，保持不变以免影响文件日志的既有消费方。
        "action": _upper(event.action.value),
        "result": _upper(event.result.value),
        "resource_type": _upper(event.resource_type.value) if event.resource_type else None,
        "resource_id": event.resource_id,
        "resource_name": event.resource_name,
        "detail": detail,
        "ip": event.client_ip,
        "user_agent": (event.user_agent or "")[:256] or None,
        "request_id": event.request_id,
        "created_at": event.timestamp,
    }


class AuditDbWriter:
    """Queue-backed writer that persists audit events into ``audit_logs``."""

    def __init__(self, *, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        self._queue: asyncio.Queue[AuditEvent] | None = None
        self._worker: asyncio.Task[None] | None = None
        self._queue_size = queue_size
        self.dropped = 0
        self.written = 0
        self.failed = 0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Create the queue and background drainer inside the running loop."""
        if self._worker is not None:
            return
        self._queue = asyncio.Queue(maxsize=self._queue_size)
        self._worker = asyncio.create_task(self._drain(), name="audit-log-writer")

    async def stop(self) -> None:
        """Flush what is queued, then cancel the drainer."""
        if self._worker is None:
            return
        worker, self._worker = self._worker, None
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass

    # -- writer hook -------------------------------------------------------

    def __call__(self, event: AuditEvent) -> None:
        """``AuditLogger`` calls this synchronously; it must not block."""
        queue = self._queue
        if queue is None:
            logger.debug("Audit DB writer not started; event stays in the file trail")
            return
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped % 100 == 1:
                logger.warning(
                    "Audit queue full; dropped %s audit event(s) so far", self.dropped
                )

    # -- internals ---------------------------------------------------------

    async def _drain(self) -> None:
        from app.database.session import async_session_factory
        from app.models.traceability import AuditLog

        while True:
            event = await self._queue.get()  # type: ignore[union-attr]
            try:
                async with async_session_factory() as session:  # type: AsyncSession
                    session.add(AuditLog(**event_to_row(event)))
                    await session.commit()
                self.written += 1
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - defensive
                self.failed += 1
                logger.exception("Failed to persist audit event %s", event.id)
            finally:
                self._queue.task_done()  # type: ignore[union-attr]


def configure_audit_db_writer(writer: AuditDbWriter | None = None) -> AuditDbWriter:
    """Attach the DB writer to the process-wide ``AuditLogger`` singleton.

    ``get_audit_logger()`` is created lazily by every caller, so the writer is
    installed on the singleton after the fact. Called from the app lifespan
    (``app.main``) so tests that never start the app keep the file-only behaviour.
    """
    from app.logging.audit import get_audit_logger

    audit_logger = get_audit_logger()
    sink = writer or AuditDbWriter()
    audit_logger.enable_db_logging = True
    audit_logger._db_writer = sink  # noqa: SLF001 - the hook is private by design
    return sink


__all__ = ["AuditDbWriter", "configure_audit_db_writer", "event_to_row"]
