"""Project conversation, durable agent event, and plan approval models."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from app.database.base import Base, TimestampMixin, UUIDMixin, utcnow


class Conversation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversations"

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    status = Column(String(32), nullable=False, default="active", index=True)


class ConversationBranch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversation_branches"

    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    parent_branch_id = Column(String(36), ForeignKey("conversation_branches.id"), nullable=True, index=True)
    # Kept as an indexed immutable reference to avoid a circular table dependency.
    forked_from_message_id = Column(String(36), nullable=True, index=True)
    title = Column(String(200), nullable=True)
    is_root = Column(Boolean, nullable=False, default=False, index=True)


class ConversationMessage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "branch_id",
            "sequence",
            name="uq_conversation_messages_branch_sequence",
        ),
    )

    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    branch_id = Column(String(36), ForeignKey("conversation_branches.id"), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    parent_message_id = Column(String(36), ForeignKey("conversation_messages.id"), nullable=True, index=True)
    role = Column(String(32), nullable=False, index=True)
    content = Column(JSON, nullable=False, default=list)
    plain_text = Column(Text, nullable=False, default="")
    sequence = Column(Integer, nullable=False)


class AgentEvent(Base, UUIDMixin):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "sequence", name="uq_agent_events_run_sequence"),
    )

    agent_run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class PlanVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "plan_versions"

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=True, index=True)
    agent_run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=True, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content = Column(JSON, nullable=False, default=dict)
    risk_level = Column(String(32), nullable=False, default="medium", index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)


class PlanDecision(Base, UUIDMixin):
    __tablename__ = "plan_decisions"

    plan_version_id = Column(
        String(36), ForeignKey("plan_versions.id"), nullable=False, unique=True, index=True
    )
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    decision = Column(String(16), nullable=False, index=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
