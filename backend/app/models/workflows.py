"""Workflow persistence models."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class WorkflowDefinition(Base, UUIDMixin, TimestampMixin):
    """用户保存的工作流画布定义。"""

    __tablename__ = "workflow_definitions"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=True)
    template_id = Column(String(120), nullable=False, index=True)
    nodes = Column(JSON, nullable=False, default=list)
    edges = Column(JSON, nullable=False, default=list)
    selected_tool_by_node = Column(JSON, nullable=False, default=dict)
    artifact_bindings_by_node = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="draft", index=True)

    user = relationship("User")


class WorkflowTemplate(Base, UUIDMixin, TimestampMixin):
    """Reusable workflow definition owned by a user."""

    __tablename__ = "workflow_templates"

    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    definition = Column(JSON, nullable=False, default=dict)
    is_public = Column(Boolean, nullable=False, default=False, index=True)
    version = Column(Integer, nullable=False, default=1)

    owner = relationship("User")
    runs = relationship(
        "WorkflowRun",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="WorkflowRun.created_at.desc()",
    )


class WorkflowRun(Base, UUIDMixin, TimestampMixin):
    """One execution instance created from a workflow template."""

    __tablename__ = "workflow_runs"

    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    template_id = Column(String(36), ForeignKey("workflow_templates.id"), nullable=True, index=True)
    name = Column(String(160), nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True)
    definition = Column(JSON, nullable=False, default=dict)
    input_files = Column(JSON, nullable=False, default=dict)
    execution_order = Column(JSON, nullable=False, default=list)
    node_states = Column(JSON, nullable=False, default=dict)
    artifact_lineage = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    owner = relationship("User")
    template = relationship("WorkflowTemplate", back_populates="runs")
