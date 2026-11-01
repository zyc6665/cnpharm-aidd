"""Secret-free durable execution metadata."""

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String, Text

from app.database.base import Base, TimestampMixin, UUIDMixin


class ExecutionRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "execution_records"

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    requested_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    #: 所属任务。历史记录通过 request_snapshot['task_id'] 间接关联（迁移 20261031_01
    #: 回填）；任务归档删除时置 NULL，执行审计记录本身保留（不级联删除）。
    task_id = Column(
        String(36),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tool_package_version_id = Column(
        String(36), ForeignKey("tool_package_versions.id"), nullable=False, index=True
    )
    adapter_type = Column(String(32), nullable=False, index=True)
    external_id = Column(String(255), nullable=True, index=True)
    idempotency_key = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    request_snapshot = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
