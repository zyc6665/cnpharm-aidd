"""Add administrator-managed image assets.

Revision ID: 20261004_01
Revises: 20260930_01
"""

import sqlalchemy as sa
from alembic import op


revision = "20261004_01"
down_revision = "20260930_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "image_assets" in existing:
        return
    op.create_table(
        "image_assets",
        sa.Column("repository", sa.String(255), nullable=False),
        sa.Column("tag", sa.String(128), nullable=False),
        sa.Column("image_reference", sa.String(512), nullable=False),
        sa.Column("manifest_digest", sa.String(71), nullable=False),
        sa.Column("archive_sha256", sa.String(64), nullable=False),
        sa.Column("archive_size_bytes", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False, server_default="linux/amd64"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ready"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("repository", "manifest_digest", name="uq_image_assets_repository_digest"),
    )
    op.create_index("ix_image_assets_repository", "image_assets", ["repository"])
    op.create_index("ix_image_assets_manifest_digest", "image_assets", ["manifest_digest"])
    op.create_index("ix_image_assets_archive_sha256", "image_assets", ["archive_sha256"])
    op.create_index("ix_image_assets_status", "image_assets", ["status"])
    op.create_index("ix_image_assets_created_by", "image_assets", ["created_by"])


def downgrade() -> None:
    if "image_assets" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("image_assets")
