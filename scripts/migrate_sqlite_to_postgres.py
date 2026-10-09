#!/usr/bin/env python3
"""迁移 SciMiner SQLite 业务数据到空的 PostgreSQL 数据库。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import Integer, create_engine, inspect, select, text


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models import agent, files, statistics, system_settings, tasks, tools, users, verification, workflows  # noqa: F401,E402


def _postgres_sync_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-db",
        type=Path,
        default=BACKEND_ROOT / "storage" / "scitool.db",
    )
    parser.add_argument(
        "--target-url",
        default=os.environ.get("TARGET_DATABASE_URL"),
    )
    parser.add_argument("--alembic-head", default="20261006_01")
    return parser.parse_args()


def _target_is_empty(connection) -> bool:
    inspector = inspect(connection)
    existing = set(inspector.get_table_names()) & set(Base.metadata.tables)
    for table_name in sorted(existing):
        table = Base.metadata.tables[table_name]
        if connection.execute(select(table).limit(1)).first() is not None:
            return False
    return True


def _reset_sequences(connection) -> None:
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if not column.primary_key or not isinstance(column.type, Integer):
                continue
            sequence = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": table.name, "column_name": column.name},
            ).scalar_one_or_none()
            if not sequence:
                continue
            connection.execute(
                text(
                    f"SELECT setval(:sequence_name, "
                    f"COALESCE(MAX(\"{column.name}\"), 1), "
                    f"MAX(\"{column.name}\") IS NOT NULL FROM \"{table.name}\""
                ),
                {"sequence_name": sequence},
            )


def _widen_byte_columns(connection) -> None:
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if not column.name.endswith("_bytes"):
                continue
            connection.execute(
                text(
                    f'ALTER TABLE "{table.name}" '
                    f'ALTER COLUMN "{column.name}" TYPE BIGINT'
                )
            )


def _drop_orphaned_foreign_key_rows(connection, table, rows):
    filtered = list(rows)
    for foreign_key in table.foreign_keys:
        child_name = foreign_key.parent.name
        parent = foreign_key.column
        parent_values = {
            value
            for (value,) in connection.execute(select(parent)).all()
        }
        orphaned = [
            row
            for row in filtered
            if row[child_name] is not None and row[child_name] not in parent_values
        ]
        if orphaned:
            print(
                f"skipped {table.name} rows with missing "
                f"{child_name} references: {len(orphaned)}"
            )
            orphaned_ids = {id(row) for row in orphaned}
            filtered = [row for row in filtered if id(row) not in orphaned_ids]
    return filtered


def migrate(source_db: Path, target_url: str, alembic_head: str) -> None:
    if not source_db.is_file():
        raise SystemExit(f"source database does not exist: {source_db}")
    if not target_url:
        raise SystemExit("TARGET_DATABASE_URL or --target-url is required")
    if not target_url.startswith("postgresql+"):
        raise SystemExit("target database must be PostgreSQL")

    source_engine = create_engine(f"sqlite:///{source_db.resolve()}")
    target_engine = create_engine(_postgres_sync_url(target_url), future=True)

    Base.metadata.create_all(target_engine)
    with target_engine.begin() as target_connection:
        if not _target_is_empty(target_connection):
            raise SystemExit("target PostgreSQL database is not empty; refusing to merge")
        _widen_byte_columns(target_connection)

        with source_engine.connect() as source_connection:
            for table in Base.metadata.sorted_tables:
                rows = source_connection.execute(select(table)).mappings().all()
                rows = _drop_orphaned_foreign_key_rows(source_connection, table, rows)
                if table.name == "user_statistics":
                    orphaned = [row for row in rows if row["user_id"] is None]
                    if orphaned:
                        print(f"skipped user_statistics rows without user_id: {len(orphaned)}")
                    rows = [row for row in rows if row["user_id"] is not None]
                if not rows:
                    continue
                target_connection.execute(table.insert(), [dict(row) for row in rows])
                print(f"copied {table.name}: {len(rows)}")

        target_connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        target_connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        target_connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
            {"head": alembic_head},
        )
        _reset_sequences(target_connection)

    source_engine.dispose()
    target_engine.dispose()


if __name__ == "__main__":
    arguments = _parse_args()
    migrate(arguments.source_db, arguments.target_url, arguments.alembic_head)
