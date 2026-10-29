"""Migration backfill test for ``tasks.project_id`` (Task 2, plan §4).

These tests must exercise the *real* add-column / add-foreign-key path of
``20261030_04``.  Building the "previous" database with
``alembic upgrade 20261029_01`` is a false positive: the baseline revision calls
``Base.metadata.create_all()`` with the **current** models, so a fresh database
already has ``tasks.project_id`` and ``projects.version`` before the migration
runs.  Instead we hand-write the legacy DDL (no ``project_id`` column, no
``version`` column) and pin ``alembic_version`` to ``20261029_01``.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "20261029_01"
TARGET_REVISION = "20261030_04"


def _run_alembic(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


LEGACY_DDL = """
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);
INSERT INTO alembic_version (version_num) VALUES ('20261029_01');

CREATE TABLE projects (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL,
    created_by VARCHAR(36) NOT NULL,
    name VARCHAR(120) NOT NULL,
    status VARCHAR(32) NOT NULL,
    model_policy JSON NOT NULL,
    data_policy JSON NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE tasks (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36),
    tool_id VARCHAR(36) NOT NULL,
    tool_version_id VARCHAR(36) NOT NULL,
    name VARCHAR(120),
    status VARCHAR(32) NOT NULL,
    priority VARCHAR(16) NOT NULL,
    extra_data JSON,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
"""


def _create_legacy_schema(db_path: Path) -> None:
    """Hand-written pre-20261030_04 schema (no project_id column, no version)."""
    with sqlite3.connect(db_path) as conn:
        conn.executescript(LEGACY_DDL)
        conn.commit()


def _insert_legacy_rows(db_path: Path, *, extra_project_id: str) -> None:
    """Insert a project + a task that only stores project_id in extra_data."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO projects (
                id, organization_id, created_by, name, status,
                model_policy, data_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("project-backfill", "org-1", "user-1", "Backfill project", "active", "{}", "{}"),
        )
        conn.execute(
            """
            INSERT INTO tasks (
                id, user_id, tool_id, tool_version_id, name, status, priority,
                extra_data, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                "task-legacy",
                "user-1",
                "tool-1",
                "tool-version-1",
                "Legacy task",
                "PENDING",
                "normal",
                '{"project_id": "%s"}' % extra_project_id,
            ),
        )
        conn.commit()


def _columns(db_path: Path, table: str) -> dict[str, dict]:
    with sqlite3.connect(db_path) as conn:
        return {
            row[1]: {"type": row[2], "notnull": row[3], "default": row[4]}
            for row in conn.execute(f"PRAGMA table_info({table})")
        }


def _foreign_keys(db_path: Path, table: str) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        return [
            {"table": row[2], "from": row[3], "to": row[4], "on_delete": row[6]}
            for row in conn.execute(f"PRAGMA foreign_key_list({table})")
        ]


def test_alembic_heads_include_project_aggregate() -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == [TARGET_REVISION], heads


def test_project_id_column_backfilled_from_extra_data(tmp_path: Path) -> None:
    db_path = tmp_path / "task_project_aggregate.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    _create_legacy_schema(db_path)
    # Sanity: the legacy schema really lacks the column, so upgrade must add it.
    assert "project_id" not in _columns(db_path, "tasks")
    assert "version" not in _columns(db_path, "projects")

    _insert_legacy_rows(db_path, extra_project_id="project-backfill")

    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    columns = _columns(db_path, "tasks")
    assert "project_id" in columns

    foreign_keys = _foreign_keys(db_path, "tasks")
    project_fks = [fk for fk in foreign_keys if fk["table"] == "projects"]
    assert len(project_fks) == 1, foreign_keys
    assert project_fks[0]["from"] == "project_id"
    assert project_fks[0]["to"] == "id"
    assert project_fks[0]["on_delete"] == "SET NULL"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM tasks WHERE id = 'task-legacy'"
        ).fetchone()
        project_version = conn.execute(
            "SELECT version FROM projects WHERE id = 'project-backfill'"
        ).fetchone()

    assert row is not None and row[0] == "project-backfill"
    assert project_version is not None and project_version[0] == 1


def test_backfill_ignores_dangling_project_reference(tmp_path: Path) -> None:
    db_path = tmp_path / "task_project_aggregate_dangling.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    _create_legacy_schema(db_path)
    _insert_legacy_rows(db_path, extra_project_id="missing-project")

    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM tasks WHERE id = 'task-legacy'"
        ).fetchone()
    # Dangling reference must not be backfilled (FK would reject it).
    assert row is not None and row[0] is None


def test_sqlite_upgrade_downgrade_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "task_project_aggregate_roundtrip.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    _create_legacy_schema(db_path)
    _insert_legacy_rows(db_path, extra_project_id="project-backfill")

    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout
    downgrade = _run_alembic("downgrade", PREVIOUS_REVISION, env=env)
    assert downgrade.returncode == 0, downgrade.stderr or downgrade.stdout

    assert "project_id" not in _columns(db_path, "tasks")
    assert "version" not in _columns(db_path, "projects")


@pytest.mark.asyncio
async def test_new_task_double_writes_project_id_column(tmp_path: Path) -> None:
    """A task created with only ``extra_data['project_id']`` still lands the real column."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models  # noqa: F401  (register all tables on Base.metadata)
    from app.models.tasks import Task

    db_path = tmp_path / "task_project_aggregate_orm.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            Task(
                id="task-new",
                user_id="user-1",
                tool_id="tool-1",
                tool_version_id="tool-version-1",
                name="New task",
                status="PENDING",
                priority="normal",
                extra_data={"project_id": "project-new"},
            )
        )
        await session.commit()
        await session.close()

    async with engine.connect() as connection:
        value = (
            await connection.execute(
                text("SELECT project_id FROM tasks WHERE id = 'task-new'")
            )
        ).scalar_one()
    await engine.dispose()
    assert value == "project-new"
