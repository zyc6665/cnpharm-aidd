"""Traceability persistence: input snapshots and the audit trail.

Two tables live here, both **append-only** (docs/10 DB-09):

* ``task_input_snapshots`` — the exact inputs a task consumed, written once at
  submission time. ``docs/04`` §9.2 calls this out as 只追加 because the whole
  point is that the record cannot drift after the fact; a task whose inputs are
  recomputed from live rows would produce a different 追溯包 a month later.
* ``audit_logs`` — the audit trail. Until step 7 this only existed as a rotating
  JSON file, which cannot be queried by the admin console (docs/06 P-38) and
  cannot be joined to projects.

Immutability is enforced twice: at the ORM level by the event listeners below
(which turn an ``UPDATE``/``DELETE`` into an immediate programming error), and in
production by the narrow grants the deployment gives these tables.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
)

from app.database.base import Base, UUIDMixin, utcnow


class ImmutableRecordError(RuntimeError):
    """Raised when append-only rows are mutated."""


class TaskInputSnapshot(Base, UUIDMixin):
    """输入快照（只追加）— docs/04 §9.2.

    ``input_role`` is the semantic slot the input filled (``RECEPTOR`` /
    ``LIGAND`` / ``SEQUENCE`` / ``POCKET`` / ``SET`` / ``FILE``), and
    ``ordinal`` disambiguates repeated roles so that two ligands in one docking
    batch stay distinguishable and ordered.
    """

    __tablename__ = "task_input_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "input_role",
            "ordinal",
            name="uq_task_input_snapshots_task_role_ordinal",
        ),
        Index("ix_task_input_snapshots_task_role", "task_id", "input_role"),
    )

    task_id = Column(String(36), nullable=False)
    input_role = Column(String(32), nullable=False)
    ordinal = Column(Integer, nullable=False, default=0)
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(String(36), nullable=True)
    urn = Column(String(512), nullable=True)
    sha256 = Column(String(64), nullable=True)
    data_version = Column(Integer, nullable=True)
    file_id = Column(String(36), nullable=True, index=True)
    detail = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)


class AuditLog(Base, UUIDMixin):
    """审计日志（只追加）— docs/04 §5.4.

    ``actor`` stores the username snapshot rather than a foreign key: the audit
    trail must stay readable after a user is renamed or disabled (docs/04 §3
    note 1). ``actor_id`` is kept alongside for joins, but never as the sole
    source of truth.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
    )

    actor = Column(String(64), nullable=False)
    actor_id = Column(String(36), nullable=True)
    action = Column(String(64), nullable=False, index=True)
    result = Column(String(16), nullable=False, default="SUCCESS")
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(String(64), nullable=True, index=True)
    resource_name = Column(String(255), nullable=True)
    detail = Column(JSON, nullable=False, default=dict)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(256), nullable=True)
    request_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)


def _reject_mutation(*_args: object, **_kwargs: object) -> None:
    raise ImmutableRecordError(
        "只追加表禁止更新或删除（docs/10 DB-09：audit_logs 与 task_input_snapshots）"
    )


for _model in (TaskInputSnapshot, AuditLog):
    for _event_name in ("before_update", "before_delete"):
        event.listen(_model, _event_name, _reject_mutation)

# ``Session.merge`` bypasses nothing but would silently issue an UPDATE, so the
# guard above already covers it. The bulk APIs (``update()``/``delete()``) do
# bypass ORM events; callers must not use them on these tables, which the
# ``aidd`` lint rule and the review checklist enforce.


def reject_bulk_mutation(*_args: object, **_kwargs: object) -> None:
    """Public alias kept for tests that assert the guard exists."""

    _reject_mutation()


__all__ = [
    "AuditLog",
    "ImmutableRecordError",
    "TaskInputSnapshot",
    "reject_bulk_mutation",
]
