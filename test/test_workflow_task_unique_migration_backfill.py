"""20261030_06 迁移回填的选取规则测试。

旧库里同一 ``(run, node)`` 可能有多条任务行（历史「最近 20 条猜」去重的产物）。
回填必须把唯一键留给「还在跑」的那一行，否则 lookup 会跳过终态行、调度器再建
任务撞唯一索引、回查又回到终态行，节点以为任务存在却永远等不到结果。
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: E402,F401  (注册全部模型，create_all 才能建全表)
from app.database.base import Base  # noqa: E402
from app.models.tasks import Task, TaskInput, TaskStatus  # noqa: E402
from app.services.workflow_task_lookup import find_existing_workflow_node_task  # noqa: E402


def _load_migration_module():
    path = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "20261030_06_workflow_node_task_unique.py"
    )
    spec = importlib.util.spec_from_file_location("migration_20261030_06", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _add_task(session: Session, *, task_id: str, status: str, created_at: datetime) -> None:
    session.add(
        Task(
            id=task_id,
            user_id=None,
            tool_id="tool-legacy",
            tool_version_id="tool-version-legacy",
            status=status,
            created_at=created_at,
        )
    )
    session.add(
        TaskInput(
            task_id=task_id,
            params={"workflow_run_id": "run-1", "workflow_node_id": "node-1"},
        )
    )


@pytest.mark.asyncio
async def test_backfill_prefers_running_row_over_terminal_duplicate(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    sync_engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(sync_engine)
    with Session(sync_engine) as session:
        # 最早的行已终态，第二条才是真正在跑的；回填必须选后者。
        _add_task(
            session,
            task_id="task-failed",
            status=TaskStatus.FAILURE.value,
            created_at=datetime(2026, 1, 1, 10, 0, 0),
        )
        _add_task(
            session,
            task_id="task-running",
            status=TaskStatus.RUNNING.value,
            created_at=datetime(2026, 1, 1, 11, 0, 0),
        )
        session.commit()

    migration = _load_migration_module()
    with sync_engine.begin() as conn:
        migration._backfill(conn)

    with Session(sync_engine) as session:
        failed = session.get(Task, "task-failed")
        running = session.get(Task, "task-running")
        assert failed.workflow_run_id is None
        assert failed.workflow_node_attempt is None
        assert running.workflow_run_id == "run-1"
        assert running.workflow_node_id == "node-1"
        assert running.workflow_node_attempt == 1

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        async with session_factory() as db:
            found = await find_existing_workflow_node_task(
                db, run_id="run-1", node_id="node-1"
            )
            assert found is not None
            assert found.id == "task-running"

            duplicate = Task(
                id="task-duplicate",
                user_id=None,
                tool_id="tool-legacy",
                tool_version_id="tool-version-legacy",
                status=TaskStatus.PENDING.value,
                workflow_run_id="run-1",
                workflow_node_id="node-1",
                workflow_node_attempt=1,
            )
            db.add(duplicate)
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
    finally:
        await async_engine.dispose()
        sync_engine.dispose()


@pytest.mark.asyncio
async def test_backfill_falls_back_to_earliest_when_all_terminal(tmp_path: Path):
    db_path = tmp_path / "legacy-terminal.db"
    sync_engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(sync_engine)
    with Session(sync_engine) as session:
        _add_task(
            session,
            task_id="task-old",
            status=TaskStatus.SUCCESS.value,
            created_at=datetime(2026, 1, 1, 9, 0, 0),
        )
        _add_task(
            session,
            task_id="task-newer",
            status=TaskStatus.CANCELED.value,
            created_at=datetime(2026, 1, 1, 12, 0, 0),
        )
        session.commit()

    migration = _load_migration_module()
    with sync_engine.begin() as conn:
        migration._backfill(conn)

    with Session(sync_engine) as session:
        assert session.get(Task, "task-old").workflow_node_attempt == 1
        assert session.get(Task, "task-newer").workflow_node_attempt is None
    sync_engine.dispose()
