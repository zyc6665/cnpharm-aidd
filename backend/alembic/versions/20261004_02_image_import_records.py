"""Add image import records and complete image asset linkage.

Revision ID: 20261004_02
Revises: 20261004_01
"""

import sqlalchemy as sa
from alembic import op


revision = "20261004_02"
down_revision = "20261004_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "image_imports" not in tables:
        op.create_table(
            "image_imports",
            sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("archive_sha256", sa.String(64), nullable=False),
            sa.Column("requested_repository", sa.String(255), nullable=False),
            sa.Column("requested_tag", sa.String(128), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_image_imports_owner_id", "image_imports", ["owner_id"])
        op.create_index("ix_image_imports_archive_sha256", "image_imports", ["archive_sha256"])
        op.create_index("ix_image_imports_status", "image_imports", ["status"])

    columns = {column["name"] for column in sa.inspect(bind).get_columns("image_assets")}
    if "import_id" not in columns:
        with op.batch_alter_table("image_assets", recreate="always") as batch:
            batch.add_column(
                sa.Column(
                    "import_id",
                    sa.String(36),
                    sa.ForeignKey("image_imports.id", name="fk_image_assets_import_id"),
                    nullable=False,
                )
            )
            batch.create_index("ix_image_assets_import_id", ["import_id"], unique=True)
    if "is_active" not in columns:
        with op.batch_alter_table("image_assets", recreate="always") as batch:
            batch.add_column(
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
            )
            batch.create_index("ix_image_assets_is_active", ["is_active"])


def downgrade() -> None:
    bind = op.get_bind()
    if "image_assets" in set(sa.inspect(bind).get_table_names()):
        inspector = sa.inspect(bind)
        columns = {column["name"] for column in inspector.get_columns("image_assets")}
        indexes = {index["name"] for index in inspector.get_indexes("image_assets")}
        columns_to_drop = {"is_active", "import_id"}.intersection(columns)
        indexes_to_drop = {
            "ix_image_assets_is_active",
            "ix_image_assets_import_id",
        }.intersection(indexes)
        if columns_to_drop or indexes_to_drop:
            with op.batch_alter_table("image_assets", recreate="always") as batch:
                for index_name in sorted(indexes_to_drop):
                    batch.drop_index(index_name)
                for column_name in ("is_active", "import_id"):
                    if column_name in columns_to_drop:
                        batch.drop_column(column_name)
    if "image_imports" in set(sa.inspect(bind).get_table_names()):
        op.drop_table("image_imports")
