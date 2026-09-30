"""Workflow persistence models."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class WorkflowDefinition(Base, UUIDMixin, TimestampMixin):
    """用户保存的工作流画布定义。"""

    __tablename__ = "workflow_definitions"

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=True)
    canvas_preset_id = Column(String(120), nullable=False, index=True)
    nodes = Column(JSON, nullable=False, default=list)
    edges = Column(JSON, nullable=False, default=list)
    selected_tool_by_node = Column(JSON, nullable=False, default=dict)
    artifact_bindings_by_node = Column(JSON, nullable=False, default=dict)
    task_bindings_by_node = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="draft", index=True)

    user = relationship("User")


class WorkflowRun(Base, UUIDMixin, TimestampMixin):
    """One execution instance created from a workflow definition."""

    __tablename__ = "workflow_runs"

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    workflow_definition_id = Column(
        String(36),
        ForeignKey("workflow_definitions.id"),
        nullable=False,
        index=True,
    )
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
    workflow_definition = relationship("WorkflowDefinition")


class ResearchBoard(Base, UUIDMixin, TimestampMixin):
    """Legacy table retained for historical records and cleanup only."""

    __tablename__ = "research_boards"

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(160), nullable=False, index=True)
    description = Column(Text, nullable=True)
    content = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)

    owner = relationship("User")
