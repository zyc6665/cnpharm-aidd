"""工作流节点任务建任务幂等测试（Task 4-5）。

验证两件事：
1. 建任务时把 ``workflow_run_id``/``workflow_node_id``/``workflow_node_attempt``
   写进 ``tasks`` 真列；
2. 同一 run+node+attempt 重复建任务时，唯一索引拒绝第二条插入，服务层捕获
   ``IntegrityError`` 后回查既有任务并原样返回，不新增行、不冒 500。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.models.tasks import Task  # noqa: E402
from app.models.users import User  # noqa: E402
from app.schemas.tasks import TaskCreate  # noqa: E402
from app.services.run_preparation import PreparedRun  # noqa: E402
from app.tasks import service as service_module  # noqa: E402
from app.tasks.service import create_and_schedule_tool_task  # noqa: E402

WORKFLOW_PARAMS = {
    "workflow_run_id": "run-1",
    "workflow_node_id": "node-a",
    "workflow_definition_id": "workflow-1",
}


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    owner = User(id="user-1", email="u@example.com", password_hash="hash")
    db_session.add(owner)
    await db_session.commit()
    return owner


async def _patch_creation_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = SimpleNamespace(id="tool-1", name="Score Tool", current_version_id="version-1")

    async def fake_prepare(**kwargs):
        prepared = PreparedRun(
            ready=True,
            project_id=None,
            params=dict(WORKFLOW_PARAMS),
            file_ids=[],
            input_bindings={},
            standard_input_uploads={},
            binding_decisions={},
        )
        return tool, SimpleNamespace(id="version-1"), "version-1", prepared, {}

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(service_module, "_prepare_tool_task_run", fake_prepare)
    monkeypatch.setattr(service_module, "_enforce_project_quota", noop)
    monkeypatch.setattr(service_module, "record_task_inputs", noop)
    monkeypatch.setattr(service_module, "record_tool_usage", noop)
    monkeypatch.setattr(service_module, "dispatch_tool_task", noop)
    monkeypatch.setattr(
        service_module,
        "get_audit_logger",
        lambda: SimpleNamespace(log_task_operation=lambda **kwargs: None),
    )


@pytest.mark.asyncio
async def test_workflow_node_task_creation_is_idempotent(
    db_session: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _patch_creation_side_effects(monkeypatch)
    task_data = TaskCreate(tool_id="tool-1", name="node task", params=dict(WORKFLOW_PARAMS))

    first = await create_and_schedule_tool_task(
        db=db_session, current_user=user, task_data=task_data
    )
    second = await create_and_schedule_tool_task(
        db=db_session, current_user=user, task_data=task_data
    )

    assert second.id == first.id

    stored = (
        await db_session.execute(
            select(Task).where(Task.workflow_run_id == "run-1")
        )
    ).scalars().all()
    assert len(stored) == 1
    assert stored[0].workflow_node_id == "node-a"
    assert stored[0].workflow_node_attempt == 1

    count = (
        await db_session.execute(select(func.count()).select_from(Task))
    ).scalar_one()
    assert int(count) == 1


@pytest.mark.asyncio
async def test_non_workflow_task_leaves_workflow_key_null(
    db_session: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _patch_creation_side_effects(monkeypatch)
    service_module_task_data = TaskCreate(tool_id="tool-1", name="plain", params={})
    # 非工作流任务没有 params 归属键；重新 patch 一个空 params 的 prepare。
    tool = SimpleNamespace(id="tool-1", name="Score Tool", current_version_id="version-1")

    async def fake_prepare(**kwargs):
        prepared = PreparedRun(
            ready=True,
            project_id=None,
            params={},
            file_ids=[],
            input_bindings={},
            standard_input_uploads={},
            binding_decisions={},
        )
        return tool, SimpleNamespace(id="version-1"), "version-1", prepared, {}

    monkeypatch.setattr(service_module, "_prepare_tool_task_run", fake_prepare)

    task = await create_and_schedule_tool_task(
        db=db_session, current_user=user, task_data=service_module_task_data
    )

    assert task.workflow_run_id is None
    assert task.workflow_node_id is None
    assert task.workflow_node_attempt is None
