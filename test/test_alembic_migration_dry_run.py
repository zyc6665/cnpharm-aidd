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
LEGACY_PROJECT_RESOURCE_TABLES = (
    "files",
    "workflow_definitions",
    "workflow_runs",
    "research_boards",
)
# 交付线移除了 Agent 特性面，agent_runs 由 20261025_01 迁移删除，
# 因此不再属于「升级后必须带 project_id 的存量资源表」。
DROPPED_AGENT_TABLES = (
    "agent_runs",
    "agent_run_steps",
    "agent_events",
    "conversations",
    "conversation_branches",
    "conversation_messages",
    "plan_versions",
    "plan_decisions",
)
ALEMBIC_SUBPROCESS_TIMEOUT_SECONDS = int(
    os.getenv("AIDD_ALEMBIC_TEST_TIMEOUT_SECONDS", "600")
)


def _run_alembic_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=ALEMBIC_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        command_text = " ".join(str(item) for item in command)
        raise AssertionError(
            f"Alembic command timed out after {ALEMBIC_SUBPROCESS_TIMEOUT_SECONDS}s: "
            f"{command_text}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        ) from exc


def _run_alembic(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return _run_alembic_command(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=PROJECT_ROOT,
        env=env,
    )


def _run_backend_alembic(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return _run_alembic_command(
        [sys.executable, "-m", "alembic", "-c", "../alembic.ini", *args],
        cwd=PROJECT_ROOT / "backend",
        env=env,
    )


def test_run_alembic_surfaces_timeout_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    """迁移子进程超时时应暴露命令和已捕获输出。"""

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=30,
            output="upgrade stdout",
            stderr="upgrade stderr",
        )

    monkeypatch.setattr(subprocess, "run", raise_timeout)

    with pytest.raises(AssertionError, match="upgrade stdout") as exc_info:
        _run_alembic("upgrade", "head", env={})

    assert "-m alembic -c alembic.ini upgrade head" in str(exc_info.value)


def _current_alembic_head() -> str:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    current_head = ScriptDirectory.from_config(config).get_current_head()
    assert current_head is not None
    return current_head


def test_alembic_sqlite_upgrade_and_downgrade_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "alembic_dry_run.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert {
        "alembic_version",
        "users",
        "tools",
        "tasks",
        "files",
        "workflow_runs",
        "tool_capabilities",
        "gpu_allocations",
    }.issubset(
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
        workflow_definition_columns = {
            row[1]: row for row in conn.execute("PRAGMA table_info(workflow_definitions)")
        }
        assert "canvas_preset_id" in workflow_definition_columns
        assert "task_bindings_by_node" in workflow_definition_columns
        assert "template_id" not in workflow_definition_columns

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
        conn.execute(
            "CREATE TABLE users ("
            "id VARCHAR(36) PRIMARY KEY, "
            "role VARCHAR(20), "
            "status VARCHAR(20), "
            "created_at DATETIME"
            ")"
        )
        conn.execute(
            "INSERT INTO users (id, role, status, created_at) "
            "VALUES ('legacy-user-1', 'admin', 'active', '2026-08-01 00:00:00')"
        )
        conn.execute("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
        conn.execute("CREATE TABLE workflow_templates (id VARCHAR(36) PRIMARY KEY)")
        for table_name in LEGACY_PROJECT_RESOURCE_TABLES:
            conn.execute(f"CREATE TABLE {table_name} (id VARCHAR(36) PRIMARY KEY)")
        for table_name in DROPPED_AGENT_TABLES:
            conn.execute(f"CREATE TABLE {table_name} (id VARCHAR(36) PRIMARY KEY)")

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    upgrade = _run_alembic("upgrade", "head", env=env)
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == (
            _current_alembic_head(),
        )
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "workflow_templates" not in tables
        for table_name in LEGACY_PROJECT_RESOURCE_TABLES:
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
            indexes = {row[1] for row in conn.execute(f"PRAGMA index_list({table_name})")}
            assert "project_id" in columns
            assert f"ix_{table_name}_project_id" in indexes
        for table_name in DROPPED_AGENT_TABLES:
            assert table_name not in tables
        workflow_run_columns = {
            row[1]: row for row in conn.execute("PRAGMA table_info(workflow_runs)")
        }
        assert "workflow_definition_id" in workflow_run_columns
        assert workflow_run_columns["workflow_definition_id"][3] == 1
        assert "template_id" not in workflow_run_columns
        workflow_definition_columns = {
            row[1]: row for row in conn.execute("PRAGMA table_info(workflow_definitions)")
        }
        assert "canvas_preset_id" in workflow_definition_columns
        assert "task_bindings_by_node" in workflow_definition_columns
        assert "template_id" not in workflow_definition_columns


def test_alembic_heads_command_works_from_backend_directory() -> None:
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "error::DeprecationWarning"
    result = _run_backend_alembic("heads", env=env)
    current_head = _current_alembic_head()

    assert result.returncode == 0, result.stderr or result.stdout
    assert current_head in result.stdout
