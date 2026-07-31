"""Add Tool Package registry tables.

Revision ID: 20260730_05
Revises: 20260730_04
"""

import sqlalchemy as sa
from alembic import op


revision = "20260730_05"
down_revision = "20260730_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "tool_packages" not in existing:
        op.create_table(
            "tool_packages",
            sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("slug", sa.String(100), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("current_version_id", sa.String(36), nullable=True),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("slug"),
        )
        op.create_index("ix_tool_packages_owner_id", "tool_packages", ["owner_id"])
        op.create_index("ix_tool_packages_slug", "tool_packages", ["slug"], unique=True)
        op.create_index("ix_tool_packages_status", "tool_packages", ["status"])

    if "tool_package_versions" not in existing:
        op.create_table(
            "tool_package_versions",
            sa.Column(
                "package_id", sa.String(36), sa.ForeignKey("tool_packages.id"), nullable=False
            ),
            sa.Column("version", sa.String(64), nullable=False),
            sa.Column("manifest", sa.JSON(), nullable=False),
            sa.Column("manifest_digest", sa.String(64), nullable=False),
            sa.Column("signature", sa.Text(), nullable=True),
            sa.Column("is_signed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("validation_status", sa.String(32), nullable=False, server_default="invalid"),
            sa.Column("validation_errors", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "package_id", "version", name="uq_tool_package_versions_package_version"
            ),
        )
        op.create_index(
            "ix_tool_package_versions_package_id", "tool_package_versions", ["package_id"]
        )
        op.create_index(
            "ix_tool_package_versions_manifest_digest",
            "tool_package_versions",
            ["manifest_digest"],
        )
        op.create_index(
            "ix_tool_package_versions_is_signed", "tool_package_versions", ["is_signed"]
        )
        op.create_index(
            "ix_tool_package_versions_validation_status",
            "tool_package_versions",
            ["validation_status"],
        )


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "tool_package_versions" in existing:
        op.drop_table("tool_package_versions")
    if "tool_packages" in existing:
        op.drop_table("tool_packages")

