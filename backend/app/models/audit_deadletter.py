"""Audit dead-letter persistence: append-only overflow for the audit sink.

Plan §3.5 asks the durable audit sink to stop *dropping* events when its bounded
queue is full. Instead of losing the trail, ``app.services.audit_sink`` writes the
overflowed event synchronously into ``audit_log_deadletters`` — a slower write is
still far better than a hole in an audit trail (docs/04 §3.2.2).

The table mirrors ``audit_logs`` and adds two columns:

* ``deadletter_reason`` — why the row landed here rather than in ``audit_logs``
  (currently always ``queue_full``; shutdown-time rejects are recorded too).
* ``deadletter_at`` — when the fallback write happened, which can lag
  ``created_at`` (the original event timestamp) under load.

Append-only is enforced at the ORM level exactly like ``audit_logs``: the same
``_reject_mutation`` listener turns ``UPDATE``/``DELETE`` into an immediate
programming error.

Migration note: this branch deliberately ships **only the model**. The parallel
``feat/project-aggregate`` branch occupies ``20261030_04`` (``down_revision=
20261029_01``); the migration chain must stay linear and this table sorts after
it. The mainline adds the ``audit_log_deadletters`` migration as
``20261030_03`` with ``down_revision="20261030_04"`` when merging — see
``docs/superpowers/plans/NOTES-20261030_03.md``.
"""

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, Index, String, event

from app.database.base import Base, UUIDMixin, utcnow
from app.models.traceability import _reject_mutation


class AuditLogDeadletter(Base, UUIDMixin):
    """审计死信表（只追加）— 队列满时的同步降级落点（计划 §3.5）。"""

    __tablename__ = "audit_log_deadletters"
    __table_args__ = (
        Index("ix_audit_log_deadletters_actor_created", "actor", "created_at"),
        Index("ix_audit_log_deadletters_resource", "resource_type", "resource_id"),
    )

    actor = Column(String(64), nullable=False, index=True)
    actor_id = Column(String(36), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    result = Column(String(16), nullable=False, default="SUCCESS")
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(String(64), nullable=True)
    resource_name = Column(String(255), nullable=True)
    detail = Column(JSON, nullable=False, default=dict)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(256), nullable=True)
    request_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
    deadletter_reason = Column(String(64), nullable=False, default="queue_full")
    deadletter_at = Column(DateTime, nullable=False, default=utcnow)


for _event_name in ("before_update", "before_delete"):
    event.listen(AuditLogDeadletter, _event_name, _reject_mutation)


__all__ = ["AuditLogDeadletter"]
