"""Add persistent GPU allocation leases.

Revision ID: 20260823_01
Revises: 20260822_01
"""

import sqlalchemy as sa
from alembic import op


revision = "20260823_01"
down_revision = "20260822_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "gpu_allocations" not in inspector.get_table_names():
        op.create_table(
            "gpu_allocations",
            sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False),
            sa.Column("execution_attempt_id", sa.String(64), nullable=True),
            sa.Column("gpu_node_id", sa.String(36), nullable=False),
            sa.Column("gpu_index", sa.Integer(), nullable=False),
            sa.Column("memory_allocated_mb", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("allocated_at", sa.DateTime(), nullable=False),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=False),
            sa.Column("released_at", sa.DateTime(), nullable=True),
            sa.Column("id", sa.String(36), primary_key=True),
        )

    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("gpu_allocations")}
    if "uq_gpu_allocations_active_device" not in existing_indexes:
        op.create_index(
            "uq_gpu_allocations_active_device",
            "gpu_allocations",
            ["gpu_node_id", "gpu_index"],
            unique=True,
            sqlite_where=sa.text("status = 'active'"),
            postgresql_where=sa.text("status = 'active'"),
        )
    for column in ("task_id", "execution_attempt_id", "gpu_node_id", "status"):
        index_name = f"ix_gpu_allocations_{column}"
        if index_name not in existing_indexes:
            op.create_index(index_name, "gpu_allocations", [column])


def downgrade() -> None:
    bind = op.get_bind()
    if "gpu_allocations" in sa.inspect(bind).get_table_names():
        op.drop_table("gpu_allocations")
