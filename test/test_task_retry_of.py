"""G-4：任务重试来源 ``retry_of`` 的行为与序列化测试。

覆盖点（对应任务验收要求）：
* 非重试任务 ``retry_of is None``；
* 首次重试后 ``retry_of`` 非空且等于链起点（就地重试时即自身 id）；
* 已有 ``retry_of`` 时再次重试**不覆盖**（保住「最初从哪条任务开始重试」）；
* 任务详情 / 列表 API 都返回 ``retry_of``；
* 迁移 ``20261028_08`` 的 upgrade/downgrade 可逆且幂等。

本仓库的重提是**就地复用同一 task 行**（``TaskStateMachine.retry`` 只把 status 改回
PENDING、retry_count+1），因此「链起点」在首次重试时就是本行自身。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1 import tasks as tasks_api  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.config import settings as config_settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import projects as _project_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _user_models  # noqa: F401,E402
from app.models.tasks import Task, TaskInput, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _create_user(db: AsyncSession, email: str, *, role: str = UserRole.USER.value) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        display_name=email.split("@")[0],
        role=role,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = await _create_user(db_session, "owner@example.com")
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, owner: User) -> Iterator[httpx.AsyncClient]:
    users = {"owner": owner}

    async def override_get_db():
        yield db_session

    async def override_get_current_user(authorization: str | None = Header(default=None)) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in users:
            return users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    try:
        yield client
    finally:
        await client.aclose()
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def published_tool(db_session: AsyncSession, owner: User) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name="Retry Of Tool",
        slug="retry-of-tool",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "python_script"},
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


async def _create_task(
    db: AsyncSession,
    *,
    user: User,
    tool: Tool,
    status: str,
    retry_of: str | None = None,
) -> Task:
    task = Task(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        name="retry-of task",
        status=status,
        progress=0,
        retry_of=retry_of,
        extra_data={},
    )
    db.add(task)
    await db.flush()
    db.add(TaskInput(task_id=task.id, params={"seed": 1}, file_ids=[]))
    await db.commit()
    await db.refresh(task)
    return task


def _patch_direct_runner(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """把任务派发切换到 direct 后端并注入一个只记录调用的 runner。"""
    runner = SimpleNamespace(
        scheduled=[],
        cancelled=[],
        schedule_task=lambda task_id, tool_version_id: runner.scheduled.append(
            (task_id, tool_version_id)
        ),
        cancel_task=lambda task_id: runner.cancelled.append(task_id) or True,
    )
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)
    return runner


# --------------------------------------------------------------------------- #
# 行为测试
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_non_retried_task_retry_of_is_none(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    published_tool: Tool,
) -> None:
    """非重试产生的任务：库里与详情 API 的 retry_of 都为 None。"""
    task = await _create_task(
        db_session, user=owner, tool=published_tool, status=TaskStatus.SUCCESS.value
    )
    assert task.retry_of is None

    detail = await api_client.get(
        f"/api/v1/tasks/{task.id}", headers={"Authorization": "Bearer owner"}
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["retry_of"] is None


@pytest.mark.asyncio
async def test_first_retry_sets_retry_of_to_lineage_origin(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次重试：链起点就是本行自身，retry_of == task.id，retry_count+1。"""
    _patch_direct_runner(monkeypatch)
    task = await _create_task(
        db_session, user=owner, tool=published_tool, status=TaskStatus.FAILURE.value
    )
    task_id = task.id

    response = await api_client.post(
        f"/api/v1/tasks/{task_id}/retry", headers={"Authorization": "Bearer owner"}
    )
    assert response.status_code == 200

    await db_session.refresh(task)
    assert task.retry_of == task_id
    assert task.retry_count == 1


@pytest.mark.asyncio
async def test_retry_does_not_overwrite_existing_retry_of(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已有 retry_of（来自更早的链起点）时再次重试必须保持不变。

    这是「每次重试都覆盖」变异的关键杀手：若实现无条件写入 task.id，
    这里会从 "origin-task" 变成 task.id 而失败。
    """
    _patch_direct_runner(monkeypatch)
    origin = "origin-task-0000-0000-0000-000000000000"
    task = await _create_task(
        db_session,
        user=owner,
        tool=published_tool,
        status=TaskStatus.FAILURE.value,
        retry_of=origin,
    )

    response = await api_client.post(
        f"/api/v1/tasks/{task.id}/retry", headers={"Authorization": "Bearer owner"}
    )
    assert response.status_code == 200

    await db_session.refresh(task)
    assert task.retry_of == origin
    assert task.retry_of != task.id


@pytest.mark.asyncio
async def test_repeated_retry_keeps_retry_of_unchanged(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连续两次重试：retry_of 第一次写入后不再变化，retry_count 持续累加。"""
    _patch_direct_runner(monkeypatch)
    task = await _create_task(
        db_session, user=owner, tool=published_tool, status=TaskStatus.FAILURE.value
    )
    task_id = task.id

    first = await api_client.post(
        f"/api/v1/tasks/{task_id}/retry", headers={"Authorization": "Bearer owner"}
    )
    assert first.status_code == 200
    await db_session.refresh(task)
    assert task.retry_of == task_id
    assert task.retry_count == 1
    retry_of_after_first = task.retry_of

    # 把状态改回 FAILURE，模拟「重试后再次失败」以触发第二次重试。
    task.status = TaskStatus.FAILURE.value
    await db_session.commit()

    second = await api_client.post(
        f"/api/v1/tasks/{task_id}/retry", headers={"Authorization": "Bearer owner"}
    )
    assert second.status_code == 200
    await db_session.refresh(task)
    assert task.retry_of == retry_of_after_first
    assert task.retry_count == 2


@pytest.mark.asyncio
async def test_task_detail_and_list_expose_retry_of(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    published_tool: Tool,
) -> None:
    """任务详情与列表都返回 retry_of 字段。"""
    origin = "lineage-origin-1111-1111-1111-111111111111"
    task = await _create_task(
        db_session,
        user=owner,
        tool=published_tool,
        status=TaskStatus.SUCCESS.value,
        retry_of=origin,
    )

    detail = await api_client.get(
        f"/api/v1/tasks/{task.id}", headers={"Authorization": "Bearer owner"}
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["retry_of"] == origin

    listing = await api_client.get(
        "/api/v1/tasks", headers={"Authorization": "Bearer owner"}
    )
    assert listing.status_code == 200
    items = listing.json()["data"]["items"]
    matched = [item for item in items if item["id"] == task.id]
    assert matched, f"任务 {task.id} 未出现在列表响应中"
    assert matched[0]["retry_of"] == origin


# --------------------------------------------------------------------------- #
# 迁移可逆性测试
# --------------------------------------------------------------------------- #
def _load_migration_module():
    path = BACKEND_ROOT / "alembic" / "versions" / "20261028_08_task_retry_of.py"
    spec = importlib.util.spec_from_file_location("migration_20261028_08_task_retry_of", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_upgrade_downgrade_is_reversible(monkeypatch: pytest.MonkeyPatch) -> None:
    """upgrade 加列+索引、重复 upgrade 幂等、downgrade 删列、重复 downgrade 幂等。"""
    migration = _load_migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text('CREATE TABLE "tasks" (id VARCHAR(36) NOT NULL PRIMARY KEY)')
            )
            operations = Operations(MigrationContext.configure(connection))
            monkeypatch.setattr(migration, "op", operations)

            migration.upgrade()
            columns = {c["name"] for c in sa.inspect(connection).get_columns("tasks")}
            indexes = {i["name"] for i in sa.inspect(connection).get_indexes("tasks")}
            assert "retry_of" in columns
            assert "ix_tasks_retry_of" in indexes

            # 幂等：再跑一次不应报错，状态不变。
            migration.upgrade()
            columns = {c["name"] for c in sa.inspect(connection).get_columns("tasks")}
            assert "retry_of" in columns

            migration.downgrade()
            columns = {c["name"] for c in sa.inspect(connection).get_columns("tasks")}
            indexes = {i["name"] for i in sa.inspect(connection).get_indexes("tasks")}
            assert "retry_of" not in columns
            assert "ix_tasks_retry_of" not in indexes

            # 幂等：再降一次不应报错。
            migration.downgrade()
            columns = {c["name"] for c in sa.inspect(connection).get_columns("tasks")}
            assert "retry_of" not in columns
    finally:
        engine.dispose()
