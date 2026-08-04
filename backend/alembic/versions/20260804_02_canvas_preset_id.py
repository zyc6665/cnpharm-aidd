"""Rename workflow definition template id to canvas preset id.

Revision ID: 20260804_02
Revises: 20260804_01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260804_02"
down_revision = "20260804_01"
branch_labels = None
depends_on = None


def _table_columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _table_indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "workflow_definitions" not in set(inspector.get_table_names()):
        return

    columns = _table_columns("workflow_definitions")
    indexes = _table_indexes("workflow_definitions")

    with op.batch_alter_table("workflow_definitions") as batch:
        if "ix_workflow_definitions_template_id" in indexes:
            batch.drop_index("ix_workflow_definitions_template_id")
        if "template_id" in columns and "canvas_preset_id" not in columns:
            batch.alter_column(
                "template_id",
                new_column_name="canvas_preset_id",
                existing_type=sa.String(120),
                existing_nullable=False,
            )
        elif "canvas_preset_id" not in columns:
            batch.add_column(sa.Column("canvas_preset_id", sa.String(120), nullable=True))

    columns = _table_columns("workflow_definitions")
    if "canvas_preset_id" in columns:
        op.execute(
            sa.text(
                "UPDATE workflow_definitions "
                "SET canvas_preset_id = 'free-canvas' "
                "WHERE canvas_preset_id IS NULL OR canvas_preset_id = ''"
            )
        )
        with op.batch_alter_table("workflow_definitions") as batch:
            batch.alter_column(
                "canvas_preset_id",
                existing_type=sa.String(120),
                nullable=False,
            )

    indexes = _table_indexes("workflow_definitions")
    if "ix_workflow_definitions_canvas_preset_id" not in indexes:
        op.create_index(
            "ix_workflow_definitions_canvas_preset_id",
            "workflow_definitions",
            ["canvas_preset_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "workflow_definitions" not in set(inspector.get_table_names()):
        return

    columns = _table_columns("workflow_definitions")
    indexes = _table_indexes("workflow_definitions")

    with op.batch_alter_table("workflow_definitions") as batch:
        if "ix_workflow_definitions_canvas_preset_id" in indexes:
            batch.drop_index("ix_workflow_definitions_canvas_preset_id")
        if "canvas_preset_id" in columns and "template_id" not in columns:
            batch.alter_column(
                "canvas_preset_id",
                new_column_name="template_id",
                existing_type=sa.String(120),
                existing_nullable=False,
            )
        elif "template_id" not in columns:
            batch.add_column(sa.Column("template_id", sa.String(120), nullable=True))

    columns = _table_columns("workflow_definitions")
    if "template_id" in columns:
        op.execute(
            sa.text(
                "UPDATE workflow_definitions "
                "SET template_id = 'free-canvas' "
                "WHERE template_id IS NULL OR template_id = ''"
            )
        )
        with op.batch_alter_table("workflow_definitions") as batch:
            batch.alter_column(
                "template_id",
                existing_type=sa.String(120),
                nullable=False,
            )

    indexes = _table_indexes("workflow_definitions")
    if "ix_workflow_definitions_template_id" not in indexes:
        op.create_index(
            "ix_workflow_definitions_template_id",
            "workflow_definitions",
            ["template_id"],
        )
