from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    PROJECT_ROOT
    / "backend"
    / "alembic"
    / "versions"
    / "20261008_01_bigint_file_sizes.py"
)
SPEC = importlib.util.spec_from_file_location(
    "bigint_file_size_migration", MIGRATION_PATH
)
assert SPEC is not None and SPEC.loader is not None
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def _create_size_tables(connection: sa.Connection, column_type: sa.types.TypeEngine) -> None:
    definitions = {
        "files": ("size_bytes",),
        "artifacts": ("size_bytes",),
        "artifact_versions": ("size_bytes",),
        "image_imports": ("size_bytes",),
        "image_assets": ("archive_size_bytes", "size_bytes"),
    }
    for table_name, column_names in definitions.items():
        columns = ", ".join(
            f'"{column_name}" {column_type} NOT NULL'
            for column_name in column_names
        )
        connection.execute(sa.text(f'CREATE TABLE "{table_name}" ({columns})'))


def _run_upgrade(connection: sa.Connection, monkeypatch) -> Operations:
    operations = Operations(MigrationContext.configure(connection))
    monkeypatch.setattr(MIGRATION, "op", operations)
    MIGRATION.upgrade()
    return operations


def test_upgrade_does_not_rebuild_tables_when_size_columns_are_already_bigint(
    monkeypatch,
):
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            _create_size_tables(connection, sa.BigInteger())
            operations = Operations(MigrationContext.configure(connection))
            batch_calls: list[str] = []
            original_batch_alter_table = operations.batch_alter_table

            def track_batch_alter_table(table_name: str, *args, **kwargs):
                batch_calls.append(table_name)
                return original_batch_alter_table(table_name, *args, **kwargs)

            monkeypatch.setattr(
                operations, "batch_alter_table", track_batch_alter_table
            )
            monkeypatch.setattr(MIGRATION, "op", operations)

            MIGRATION.upgrade()

            assert batch_calls == []
    finally:
        engine.dispose()


def test_upgrade_converts_integer_size_columns_to_bigint(monkeypatch):
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            _create_size_tables(connection, sa.Integer())

            _run_upgrade(connection, monkeypatch)

            for table_name in (
                "files",
                "artifacts",
                "artifact_versions",
                "image_imports",
                "image_assets",
            ):
                columns = {
                    column["name"]: column["type"]
                    for column in sa.inspect(connection).get_columns(table_name)
                }
                for column_name in set(columns) & {"size_bytes", "archive_size_bytes"}:
                    assert isinstance(columns[column_name], sa.BigInteger)
    finally:
        engine.dispose()
