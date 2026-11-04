"""Workflow persistence models."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text
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
    __table_args__ = (
        # 活跃运行巡检（超时/对账）：只索引非终态行。终态值经 grep 核实为
        # success / failure / canceled（workflow_reconciliation.py、
        # workflow_cancellation.py），非终态为 pending / waiting_task。
        Index(
            "ix_workflow_runs_active_created",
            "created_at",
            sqlite_where=text("status NOT IN ('success', 'failure', 'canceled')"),
            postgresql_where=text("status NOT IN ('success', 'failure', 'canceled')"),
        ),
        # 工作流运行列表游标（keyset）翻页：按项目 / 按 owner 两个入口，
        # 排序键 (created_at DESC, id DESC) 的全序。末列 id 不能省：只到 created_at
        # 时 SQLite 仍会对同一毫秒的并列行做「RIGHT PART OF ORDER BY」内存排序。
        Index("ix_workflow_runs_project_created", "project_id", "created_at", "id"),
        Index("ix_workflow_runs_owner_created", "owner_id", "created_at", "id"),
        # project_id 单列索引：数据库上实际存在（历史迁移建立），模型此前缺失，
        # 导致 alembic check 误报 "removed index"。它是复合索引 ix_workflow_runs_project_created
        # 的前缀，对纯等值过滤并非最优替代（复合索引同样可用），但为了消除模型与库
        # 的双真源漂移而在此显式声明；test_index_governance 已将本索引登记为允许的
        # 「前缀冗余」（见 ALLOWED_REDUNDANT_PREFIXES）。
        Index("ix_workflow_runs_project_id", "project_id"),
    )

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
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
