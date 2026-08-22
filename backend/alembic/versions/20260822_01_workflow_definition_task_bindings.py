"""Persist saved workflow node task bindings.

Revision ID: 20260822_01
Revises: 20260821_01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260822_01"
down_revision = "20260821_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "workflow_definitions" not in set(inspector.get_table_names()):
        return

    columns = {column["name"] for column in inspector.get_columns("workflow_definitions")}
    if "task_bindings_by_node" in columns:
        return

    with op.batch_alter_table("workflow_definitions") as batch:
        batch.add_column(
            sa.Column(
                "task_bindings_by_node",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "workflow_definitions" not in set(inspector.get_table_names()):
        return

    columns = {column["name"] for column in inspector.get_columns("workflow_definitions")}
    if "task_bindings_by_node" not in columns:
        return

    with op.batch_alter_table("workflow_definitions") as batch:
        batch.drop_column("task_bindings_by_node")
