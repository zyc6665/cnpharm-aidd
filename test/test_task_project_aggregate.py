"""Migration backfill test for ``tasks.project_id`` (Task 2, plan §4).

Builds a SQLite database at the revision *before* ``20261030_04``, inserts a task
whose project only exists in ``extra_data["project_id"]`` (the legacy shape),
then runs the new migration and asserts the real column is populated.
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


def test_alembic_heads_include_project_aggregate() -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == [TARGET_REVISION], heads


def test_project_id_column_backfilled_from_extra_data(tmp_path: Path) -> None:
    db_path = tmp_path / "task_project_aggregate.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    baseline = _run_alembic("upgrade", PREVIOUS_REVISION, env=env)
    assert baseline.returncode == 0, baseline.stderr or baseline.stdout

    _insert_legacy_rows(db_path, extra_project_id="project-backfill")

    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

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

    baseline = _run_alembic("upgrade", PREVIOUS_REVISION, env=env)
    assert baseline.returncode == 0, baseline.stderr or baseline.stdout

    _insert_legacy_rows(db_path, extra_project_id="missing-project")

    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM tasks WHERE id = 'task-legacy'"
        ).fetchone()
    # Dangling reference must not be backfilled (FK would reject it).
    assert row is not None and row[0] is None


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
