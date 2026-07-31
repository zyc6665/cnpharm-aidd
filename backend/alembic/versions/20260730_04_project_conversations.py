"""Add project conversations, durable events, and plan decisions.

Revision ID: 20260730_04
Revises: 20260730_03
"""

import sqlalchemy as sa
from alembic import op

revision = "20260730_04"
down_revision = "20260730_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    target_tables = {
        "conversations",
        "conversation_branches",
        "conversation_messages",
        "agent_events",
        "plan_versions",
        "plan_decisions",
    }
    # The historical baseline uses metadata.create_all(checkfirst=True), so a
    # fresh installation can already contain every current model table.
    if target_tables.issubset(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "conversations",
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for column in ("project_id", "created_by", "status"):
        op.create_index(f"ix_conversations_{column}", "conversations", [column])

    op.create_table(
        "conversation_branches",
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("parent_branch_id", sa.String(36), sa.ForeignKey("conversation_branches.id"), nullable=True),
        sa.Column("forked_from_message_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("is_root", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for column in ("conversation_id", "created_by", "parent_branch_id", "forked_from_message_id", "is_root"):
        op.create_index(f"ix_conversation_branches_{column}", "conversation_branches", [column])

    op.create_table(
        "conversation_messages",
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("conversation_branches.id"), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("parent_message_id", sa.String(36), sa.ForeignKey("conversation_messages.id"), nullable=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("plain_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("conversation_id", "branch_id", "sequence", name="uq_conversation_messages_branch_sequence"),
    )
    for column in ("conversation_id", "branch_id", "author_id", "parent_message_id", "role"):
        op.create_index(f"ix_conversation_messages_{column}", "conversation_messages", [column])

    op.create_table(
        "agent_events",
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("agent_run_id", "sequence", name="uq_agent_events_run_sequence"),
    )
    for column in ("agent_run_id", "event_type"):
        op.create_index(f"ix_agent_events_{column}", "agent_events", [column])

    op.create_table(
        "plan_versions",
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for column in ("project_id", "conversation_id", "agent_run_id", "created_by", "risk_level", "status"):
        op.create_index(f"ix_plan_versions_{column}", "plan_versions", [column])

    op.create_table(
        "plan_decisions",
        sa.Column("plan_version_id", sa.String(36), sa.ForeignKey("plan_versions.id"), nullable=False),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("plan_version_id"),
    )
    op.create_index("ix_plan_decisions_plan_version_id", "plan_decisions", ["plan_version_id"], unique=True)
    op.create_index("ix_plan_decisions_reviewer_id", "plan_decisions", ["reviewer_id"])
    op.create_index("ix_plan_decisions_decision", "plan_decisions", ["decision"])


def downgrade() -> None:
    for table_name in (
        "plan_decisions",
        "plan_versions",
        "agent_events",
        "conversation_messages",
        "conversation_branches",
        "conversations",
    ):
        op.drop_table(table_name)
