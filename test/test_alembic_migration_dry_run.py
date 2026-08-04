from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROJECT_RESOURCE_TABLES = (
    "files",
    "agent_runs",
    "workflow_definitions",
    "workflow_runs",
    "research_boards",
)


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

    assert {"alembic_version", "users", "tools", "tasks", "files", "workflow_runs", "tool_capabilities"}.issubset(
        tables
    )
    assert "workflow_templates" not in tables
    assert "user_sessions" not in tables

    with sqlite3.connect(db_path) as conn:
        assert "session_id" not in {
            row[1] for row in conn.execute("PRAGMA table_info(tasks)")
        }
        assert "session_id" not in {
            row[1] for row in conn.execute("PRAGMA table_info(files)")
        }
        workflow_run_columns = {
            row[1]: row for row in conn.execute("PRAGMA table_info(workflow_runs)")
        }
        assert "workflow_definition_id" in workflow_run_columns
        assert workflow_run_columns["workflow_definition_id"][3] == 1
        assert "template_id" not in workflow_run_columns

    downgrade = _run_alembic("downgrade", "base", env=env)
    assert downgrade.returncode == 0, downgrade.stderr or downgrade.stdout

    with sqlite3.connect(db_path) as conn:
        remaining_tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    assert "users" not in remaining_tables
    assert "tools" not in remaining_tables
    assert "workflow_runs" not in remaining_tables


def test_alembic_sqlite_legacy_project_link_upgrade_is_resumable(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_project_links.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('20260730_02')")
        conn.execute("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)")
        conn.execute("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
        conn.execute("CREATE TABLE workflow_templates (id VARCHAR(36) PRIMARY KEY)")
        for table_name in LEGACY_PROJECT_RESOURCE_TABLES:
            conn.execute(f"CREATE TABLE {table_name} (id VARCHAR(36) PRIMARY KEY)")

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260804_01",
        )
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "workflow_templates" not in tables
        for table_name in LEGACY_PROJECT_RESOURCE_TABLES:
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
            indexes = {row[1] for row in conn.execute(f"PRAGMA index_list({table_name})")}
            assert "project_id" in columns
            assert f"ix_{table_name}_project_id" in indexes
        workflow_run_columns = {
            row[1]: row for row in conn.execute("PRAGMA table_info(workflow_runs)")
        }
        assert "workflow_definition_id" in workflow_run_columns
        assert workflow_run_columns["workflow_definition_id"][3] == 1
        assert "template_id" not in workflow_run_columns


def test_alembic_heads_command_works_from_backend_directory() -> None:
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "error::DeprecationWarning"
    result = _run_backend_alembic("heads", env=env)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    current_head = ScriptDirectory.from_config(config).get_current_head()

    assert result.returncode == 0, result.stderr or result.stdout
    assert current_head is not None
    assert current_head in result.stdout
