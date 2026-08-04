"""Replace template workflow runs with definition workflow runs.

Revision ID: 20260804_01
Revises: 20260801_01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260804_01"
down_revision = "20260801_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "workflow_runs" in tables:
        # Old template-backed runs cannot be safely mapped to WorkflowDefinition.
        op.execute(sa.text("DELETE FROM workflow_runs"))

        run_columns = {column["name"] for column in inspector.get_columns("workflow_runs")}
        run_indexes = {index["name"] for index in inspector.get_indexes("workflow_runs")}
        with op.batch_alter_table("workflow_runs") as batch:
            if "ix_workflow_runs_template_id" in run_indexes:
                batch.drop_index("ix_workflow_runs_template_id")
            if "workflow_definition_id" not in run_columns:
                batch.add_column(
                    sa.Column(
                        "workflow_definition_id",
                        sa.String(36),
                        sa.ForeignKey(
                            "workflow_definitions.id",
                            name="fk_workflow_runs_workflow_definition_id_workflow_definitions",
                        ),
                        nullable=False,
                    )
                )
            else:
                batch.alter_column(
                    "workflow_definition_id",
                    existing_type=sa.String(36),
                    nullable=False,
                )
            if "template_id" in run_columns:
                batch.drop_column("template_id")

        inspector = sa.inspect(bind)
        run_indexes = {index["name"] for index in inspector.get_indexes("workflow_runs")}
        if "ix_workflow_runs_workflow_definition_id" not in run_indexes:
            op.create_index(
                "ix_workflow_runs_workflow_definition_id",
                "workflow_runs",
                ["workflow_definition_id"],
            )

    inspector = sa.inspect(bind)
    if "workflow_templates" in set(inspector.get_table_names()):
        op.drop_table("workflow_templates")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "workflow_templates" not in tables:
        op.create_table(
            "workflow_templates",
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True),
            sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("definition", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        for column in ("project_id", "owner_id", "status"):
            op.create_index(f"ix_workflow_templates_{column}", "workflow_templates", [column])

    inspector = sa.inspect(bind)
    if "workflow_runs" in set(inspector.get_table_names()):
        op.execute(sa.text("DELETE FROM workflow_runs"))
        run_columns = {column["name"] for column in inspector.get_columns("workflow_runs")}
        run_indexes = {index["name"] for index in inspector.get_indexes("workflow_runs")}

        with op.batch_alter_table("workflow_runs") as batch:
            if "ix_workflow_runs_workflow_definition_id" in run_indexes:
                batch.drop_index("ix_workflow_runs_workflow_definition_id")
            if "template_id" not in run_columns:
                batch.add_column(
                    sa.Column(
                        "template_id",
                        sa.String(36),
                        sa.ForeignKey(
                            "workflow_templates.id",
                            name="fk_workflow_runs_template_id_workflow_templates",
                        ),
                        nullable=True,
                    )
                )
            if "workflow_definition_id" in run_columns:
                batch.drop_column("workflow_definition_id")

        inspector = sa.inspect(bind)
        run_indexes = {index["name"] for index in inspector.get_indexes("workflow_runs")}
        if "ix_workflow_runs_template_id" not in run_indexes:
            op.create_index("ix_workflow_runs_template_id", "workflow_runs", ["template_id"])
