"""Add typed Artifact versions and lineage.

Revision ID: 20260730_06
Revises: 20260730_05
"""

import sqlalchemy as sa
from alembic import op

revision = "20260730_06"
down_revision = "20260730_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "artifacts" not in existing:
        op.create_table(
            "artifacts",
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("artifact_type", sa.String(100), nullable=False),
            sa.Column("semantic_type", sa.String(100), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("latest_version_id", sa.String(36), nullable=True),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        for column in ("project_id", "created_by", "artifact_type", "semantic_type"):
            op.create_index(f"ix_artifacts_{column}", "artifacts", [column])
    if "artifact_versions" not in existing:
        op.create_table(
            "artifact_versions",
            sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifacts.id"), nullable=False),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(160), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("storage_key", sa.String(1000), nullable=False),
            sa.Column("storage_etag", sa.String(255), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="available"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("artifact_id", "version", name="uq_artifact_versions_artifact_version"),
        )
        for column in ("artifact_id", "created_by", "sha256", "status", "expires_at"):
            op.create_index(f"ix_artifact_versions_{column}", "artifact_versions", [column])
    if "artifact_lineage" not in existing:
        op.create_table(
            "artifact_lineage",
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("input_version_id", sa.String(36), sa.ForeignKey("artifact_versions.id"), nullable=False),
            sa.Column("output_version_id", sa.String(36), sa.ForeignKey("artifact_versions.id"), nullable=False),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("relation_type", sa.String(32), nullable=False, server_default="derived_from"),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("input_version_id", "output_version_id", name="uq_artifact_lineage_input_output"),
        )
        for column in ("project_id", "input_version_id", "output_version_id", "created_by"):
            op.create_index(f"ix_artifact_lineage_{column}", "artifact_lineage", [column])


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in ("artifact_lineage", "artifact_versions", "artifacts"):
        if table_name in existing:
            op.drop_table(table_name)
