"""AIDD agent orchestration models."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class AgentRun(Base, UUIDMixin, TimestampMixin):
    """A single user-visible AIDD agent run."""

    __tablename__ = "agent_runs"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    intent = Column(String(100), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    input_type = Column(String(64), nullable=False)
    input_file_id = Column(String(36), ForeignKey("files.id"), nullable=True, index=True)
    requested_outputs = Column(JSON, nullable=False, default=list)
    plan = Column(JSON, nullable=False, default=dict)
    summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    user = relationship("User")
    input_file = relationship("File")
    steps = relationship(
        "AgentRunStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentRunStep.sort_order",
    )


class AgentRunStep(Base, UUIDMixin, TimestampMixin):
    """A single tool step inside an agent run."""

    __tablename__ = "agent_run_steps"

    agent_run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False, index=True)
    step_key = Column(String(100), nullable=False, index=True)
    tool_slug = Column(String(100), nullable=False, index=True)
    tool_id = Column(String(36), ForeignKey("tools.id"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    depends_on_step_ids = Column(JSON, nullable=False, default=list)
    semantic_inputs = Column(JSON, nullable=False, default=dict)
    semantic_outputs = Column(JSON, nullable=False, default=dict)
    params = Column(JSON, nullable=False, default=dict)
    input_file_ids = Column(JSON, nullable=False, default=list)
    output_file_ids = Column(JSON, nullable=False, default=list)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    run = relationship("AgentRun", back_populates="steps")
    tool = relationship("Tool")
    task = relationship("Task")
