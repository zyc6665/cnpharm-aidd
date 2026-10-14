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


def _existing_column_types(table_name: str) -> dict[str, sa.types.TypeEngine]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return {}
    return {
        column["name"]: column["type"]
        for column in inspector.get_columns(table_name)
    }


def upgrade() -> None:
    for table_name, column_names in _SIZE_COLUMNS.items():
        existing_column_types = _existing_column_types(table_name)
        present_columns = [
            column_name
            for column_name in column_names
            if column_name in existing_column_types
            and not isinstance(existing_column_types[column_name], sa.BigInteger)
        ]
        if not present_columns:
            continue
        with op.batch_alter_table(table_name) as batch:
            for column_name in present_columns:
                batch.alter_column(
                    column_name,
                    existing_type=existing_column_types[column_name],
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                )


def downgrade() -> None:
    for table_name, column_names in reversed(tuple(_SIZE_COLUMNS.items())):
        existing_column_types = _existing_column_types(table_name)
        present_columns = [
            column_name
            for column_name in column_names
            if column_name in existing_column_types
            and isinstance(existing_column_types[column_name], sa.BigInteger)
        ]
        if not present_columns:
            continue
        with op.batch_alter_table(table_name) as batch:
            for column_name in present_columns:
                batch.alter_column(
                    column_name,
                    existing_type=existing_column_types[column_name],
                    type_=sa.Integer(),
                    existing_nullable=False,
                )
