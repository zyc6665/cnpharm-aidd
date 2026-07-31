"""Add nullable project links to legacy research resources.

Revision ID: 20260730_03
Revises: 20260730_02
"""

import sqlalchemy as sa
from alembic import op

revision = "20260730_03"
down_revision = "20260730_02"
branch_labels = None
depends_on = None


RESOURCE_TABLES = (
    "files",
    "agent_runs",
    "workflow_definitions",
    "workflow_templates",
    "workflow_runs",
    "research_boards",
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table_name in RESOURCE_TABLES:
        if table_name not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "project_id" in columns:
            continue
        with op.batch_alter_table(table_name) as batch:
            batch.add_column(
                sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True)
            )
            batch.create_index(f"ix_{table_name}_project_id", ["project_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table_name in reversed(RESOURCE_TABLES):
        if table_name not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "project_id" not in columns:
            continue
        with op.batch_alter_table(table_name) as batch:
            batch.drop_index(f"ix_{table_name}_project_id")
            batch.drop_column("project_id")
