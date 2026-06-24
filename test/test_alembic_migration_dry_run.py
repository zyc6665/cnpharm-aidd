from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_alembic(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_backend_alembic(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "../alembic.ini", *args],
        cwd=PROJECT_ROOT / "backend",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_alembic_sqlite_upgrade_and_downgrade_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "alembic_dry_run.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert {"alembic_version", "users", "tools", "tasks", "files", "workflow_runs"}.issubset(
        tables
    )

    downgrade = _run_alembic("downgrade", "-1", env=env)
    assert downgrade.returncode == 0, downgrade.stderr or downgrade.stdout

    with sqlite3.connect(db_path) as conn:
        remaining_tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    assert "users" not in remaining_tables
    assert "tools" not in remaining_tables
    assert "workflow_runs" not in remaining_tables


def test_alembic_heads_command_works_from_backend_directory() -> None:
    result = _run_backend_alembic("heads", env=os.environ.copy())

    assert result.returncode == 0, result.stderr or result.stdout
    assert "20260624_01" in result.stdout
