"""Add secret-free execution records.

Revision ID: 20260730_07
Revises: 20260730_06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260730_07"
down_revision = "20260730_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "execution_records" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "execution_records",
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("requested_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tool_package_version_id", sa.String(36), sa.ForeignKey("tool_package_versions.id"), nullable=False),
        sa.Column("adapter_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("request_snapshot", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("idempotency_key"),
    )
    for column in (
        "project_id", "requested_by", "tool_package_version_id", "adapter_type",
        "external_id", "idempotency_key", "status",
    ):
        op.create_index(
            f"ix_execution_records_{column}",
            "execution_records",
            [column],
            unique=column == "idempotency_key",
        )


def downgrade() -> None:
    if "execution_records" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("execution_records")
