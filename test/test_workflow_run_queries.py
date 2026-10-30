"""Workflow run query helper tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.models.workflows import WorkflowDefinition, WorkflowRun  # noqa: E402
from app.services.workflow_run_queries import (  # noqa: E402
    WorkflowRunPage,
    list_workflow_runs,
    load_run_for_user,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_load_run_for_user_allows_projectless_owner(db_session: AsyncSession):
    user = User(
        email="workflow-query-owner@example.com",
        password_hash="hashed-password",
        display_name="owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.flush()

    workflow = WorkflowDefinition(
        user_id=user.id,
        name="Query workflow",
        canvas_preset_id="custom",
        nodes=[],
        edges=[],
    )
    db_session.add(workflow)
    await db_session.flush()

    run = WorkflowRun(
        owner_id=user.id,
        workflow_definition_id=workflow.id,
        name="Query run",
        definition={"nodes": [], "edges": []},
        input_files={},
        execution_order=[],
        node_states={},
        artifact_lineage={},
    )
    db_session.add(run)
    await db_session.commit()

    loaded = await load_run_for_user(db_session, run_id=run.id, current_user=user)

    assert loaded.id == run.id


def _workflow_run(owner: User, workflow: WorkflowDefinition, name: str) -> WorkflowRun:
    return WorkflowRun(
        owner_id=owner.id,
        workflow_definition_id=workflow.id,
        name=name,
        status="pending",
        definition={"nodes": [], "edges": []},
        input_files={},
        execution_order=[],
        node_states={},
        artifact_lineage={},
    )


@pytest.mark.asyncio
async def test_list_workflow_runs_cursor_pagination_contract(db_session: AsyncSession):
    """工作流运行游标分页：不传 cursor 有 total；传 cursor total=None 且不重不漏。"""
    from datetime import datetime

    user = User(
        email="workflow-cursor@example.com",
        password_hash="hashed",
        display_name="cursor",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.flush()
    workflow = WorkflowDefinition(
        user_id=user.id,
        name="Cursor workflow",
        canvas_preset_id="custom",
        nodes=[],
        edges=[],
    )
    db_session.add(workflow)
    await db_session.flush()

    fixed = datetime(2026, 1, 1, 12, 0, 0)
    runs = [_workflow_run(user, workflow, f"run-{index}") for index in range(5)]
    db_session.add_all(runs)
    await db_session.flush()
    for run in runs:
        run.created_at = fixed
    await db_session.commit()

    expected = sorted((run.id for run in runs), reverse=True)

    # 1) 偏移模式：保留旧行为（total 为整数），并从本页末行给 next_cursor。
    page = await list_workflow_runs(db_session, current_user=user, page=1, page_size=2)
    assert isinstance(page, WorkflowRunPage)
    assert page.total == 5
    assert page.has_more is True
    assert page.next_cursor
    assert [run.id for run in page.runs] == expected[:2]

    # 2) 游标模式：total 为 None（不算 count），顺序与去重正确。
    collected = [run.id for run in page.runs]
    cursor = page.next_cursor
    pages = 0
    while cursor:
        next_page = await list_workflow_runs(
            db_session, current_user=user, page_size=2, cursor=cursor
        )
        assert next_page.total is None
        collected.extend(run.id for run in next_page.runs)
        pages += 1
        assert pages < 10, "游标翻页没有收敛"
        cursor = next_page.next_cursor if next_page.has_more else None

    assert collected == expected
    assert len(collected) == len(set(collected)) == 5
