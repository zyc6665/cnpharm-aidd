"""Allow persisted file and image sizes above the 32-bit integer range."""

import sqlalchemy as sa
from alembic import op


revision = "20261008_01"
down_revision = "20261006_01"
branch_labels = None
depends_on = None


_SIZE_COLUMNS = {
    "files": ("size_bytes",),
    "artifacts": ("size_bytes",),
    "artifact_versions": ("size_bytes",),
    "image_imports": ("size_bytes",),
    "image_assets": ("archive_size_bytes", "size_bytes"),
}


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if table_name not in tables:
        return set()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    for table_name, column_names in _SIZE_COLUMNS.items():
        existing_columns = _existing_columns(table_name)
        present_columns = [
            column_name for column_name in column_names if column_name in existing_columns
        ]
        if not present_columns:
            continue
        with op.batch_alter_table(table_name, recreate="always") as batch:
            for column_name in present_columns:
                batch.alter_column(
                    column_name,
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                )


def downgrade() -> None:
    for table_name, column_names in reversed(tuple(_SIZE_COLUMNS.items())):
        existing_columns = _existing_columns(table_name)
        present_columns = [
            column_name for column_name in column_names if column_name in existing_columns
        ]
        if not present_columns:
            continue
        with op.batch_alter_table(table_name, recreate="always") as batch:
            for column_name in present_columns:
                batch.alter_column(
                    column_name,
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False,
                )
