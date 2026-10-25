"""Drop the AIDD agent orchestration and project conversation tables.

The China Pharmaceutical delivery line removes the Agent feature surface:
conversational planning, plan approval, and the durable agent event stream are
all out of scope for the一期 delivery.  Tool capability registration, semantic
output extraction, and builtin tool execution were relocated to
``app/tools`` / ``app/external_databases`` and keep working without these
tables.

Dropped tables (dependency order):

    plan_decisions -> plan_versions -> agent_events -> conversation_messages
    -> conversation_branches -> conversations -> agent_run_steps -> agent_runs

``downgrade`` re-creates the schema only (no data); the Agent application code
is gone from this branch, so the restored tables stay empty until a fork-point
backup is restored.
"""

import sqlalchemy as sa
from alembic import op


revision = "20261025_01"
down_revision = "20261008_01"
branch_labels = None
depends_on = None


DROP_ORDER: tuple[str, ...] = (
    "plan_decisions",
    "plan_versions",
    "agent_events",
    "conversation_messages",
    "conversation_branches",
    "conversations",
    "agent_run_steps",
    "agent_runs",
)


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()
    for table_name in DROP_ORDER:
        if table_name in existing:
            op.drop_table(table_name)


def downgrade() -> None:
    existing = _existing_tables()

    def _create(table_name: str, *columns: sa.Column, **kwargs: object) -> None:
        if table_name not in existing:
            op.create_table(table_name, *columns, **kwargs)

    _create(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(100), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
        sa.Column("input_type", sa.String(64), nullable=False),
        sa.Column("input_file_id", sa.String(36), sa.ForeignKey("files.id"), index=True),
        sa.Column("requested_outputs", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    _create(
        "agent_run_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "agent_run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("step_key", sa.String(100), nullable=False, index=True),
        sa.Column("tool_slug", sa.String(100), nullable=False, index=True),
        sa.Column("tool_id", sa.String(36), sa.ForeignKey("tools.id"), index=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("depends_on_step_ids", sa.JSON(), nullable=False),
        sa.Column("semantic_inputs", sa.JSON(), nullable=False),
        sa.Column("semantic_outputs", sa.JSON(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("input_file_ids", sa.JSON(), nullable=False),
        sa.Column("output_file_ids", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    _create(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active", index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    _create(
        "conversation_branches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column(
            "parent_branch_id",
            sa.String(36),
            sa.ForeignKey("conversation_branches.id"),
            index=True,
        ),
        sa.Column("forked_from_message_id", sa.String(36), index=True),
        sa.Column("title", sa.String(200)),
        sa.Column("is_root", sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    _create(
        "conversation_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "branch_id",
            sa.String(36),
            sa.ForeignKey("conversation_branches.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), index=True),
        sa.Column(
            "parent_message_id",
            sa.String(36),
            sa.ForeignKey("conversation_messages.id"),
            index=True,
        ),
        sa.Column("role", sa.String(32), nullable=False, index=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("plain_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "conversation_id",
            "branch_id",
            "sequence",
            name="uq_conversation_messages_branch_sequence",
        ),
    )

    _create(
        "agent_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "agent_run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("agent_run_id", "sequence", name="uq_agent_events_run_sequence"),
    )

    _create(
        "plan_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), index=True),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), index=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False, server_default="medium", index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    _create(
        "plan_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "plan_version_id",
            sa.String(36),
            sa.ForeignKey("plan_versions.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("decision", sa.String(16), nullable=False, index=True),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
