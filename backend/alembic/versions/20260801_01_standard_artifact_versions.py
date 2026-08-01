"""Add standard Artifact version file roles.

Revision ID: 20260801_01
Revises: 20260730_07
"""

import sqlalchemy as sa
from alembic import op


revision = "20260801_01"
down_revision = "20260730_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "artifacts" in tables:
        artifact_columns = {column["name"] for column in inspector.get_columns("artifacts")}
        _add_column_if_missing(
            artifact_columns,
            "artifacts",
            sa.Column("standard_type", sa.String(100), nullable=True),
        )
        _add_column_if_missing(
            artifact_columns,
            "artifacts",
            sa.Column("standard_version", sa.Integer(), nullable=True),
        )
        _add_column_if_missing(
            artifact_columns,
            "artifacts",
            sa.Column("source_task_id", sa.String(36), nullable=True),
        )
        for column in ("standard_type", "standard_version", "source_task_id"):
            _create_index_if_missing(inspector, "artifacts", column)

    if "artifact_versions" in tables:
        version_columns = {
            column["name"] for column in inspector.get_columns("artifact_versions")
        }
        _add_column_if_missing(
            version_columns,
            "artifact_versions",
            sa.Column("validation_status", sa.String(32), nullable=False, server_default="pending"),
        )
        _add_column_if_missing(
            version_columns,
            "artifact_versions",
            sa.Column("validation_errors", sa.JSON(), nullable=False, server_default="[]"),
        )
        _add_column_if_missing(
            version_columns,
            "artifact_versions",
            sa.Column("manifest_json", sa.JSON(), nullable=False, server_default="{}"),
        )
        _add_column_if_missing(
            version_columns,
            "artifact_versions",
            sa.Column("summary_json", sa.JSON(), nullable=False, server_default="{}"),
        )
        _add_column_if_missing(
            version_columns,
            "artifact_versions",
            sa.Column("metrics_json", sa.JSON(), nullable=False, server_default="{}"),
        )
        _create_index_if_missing(inspector, "artifact_versions", "validation_status")

    if "artifact_version_files" not in tables:
        op.create_table(
            "artifact_version_files",
            sa.Column(
                "artifact_version_id",
                sa.String(36),
                sa.ForeignKey("artifact_versions.id"),
                nullable=False,
            ),
            sa.Column("role", sa.String(100), nullable=False),
            sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id"), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "artifact_version_id",
                "role",
                name="uq_artifact_version_files_version_role",
            ),
        )
        for column in ("artifact_version_id", "role", "file_id"):
            op.create_index(
                f"ix_artifact_version_files_{column}",
                "artifact_version_files",
                [column],
            )


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "artifact_version_files" in existing:
        op.drop_table("artifact_version_files")


def _add_column_if_missing(
    existing_columns: set[str],
    table_name: str,
    column: sa.Column,
) -> None:
    if column.name not in existing_columns:
        op.add_column(table_name, column)
        existing_columns.add(column.name)


def _create_index_if_missing(inspector: sa.Inspector, table_name: str, column: str) -> None:
    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes(table_name)
    }
    index_name = f"ix_{table_name}_{column}"
    if index_name not in existing_indexes:
        op.create_index(index_name, table_name, [column])
