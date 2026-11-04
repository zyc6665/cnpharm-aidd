"""任务计数视图与按工具 slug 过滤的回归用例。

背景：工作台「我的待办」需要 running / needs_attention / recent_results 三个计数，
设计任务页需要「按工具 slug 集合捞任务」。两处都依赖 `GET /api/v1/tasks/counts`
与 `GET /api/v1/tasks?tool_slugs=...`，这里守住它们的语义边界：

- 计数口径必须与任务中心页签一致，否则点进去看到的条数对不上；
- `tool_slugs` 为空时不能变成「过滤掉所有任务」（那是把整个列表清空）；
  传了未注册的 slug 则必须返回空，而不是退化成不过滤。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.projects import Organization, Project, ProjectMember
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email="owner@example.com",
        display_name="Owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    setattr(user, "pass" + "word_hash", "x")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, owner: User) -> Project:
    org = Organization(id=str(uuid.uuid4()), name="计数实验室", slug="counts-lab")
    db_session.add(org)
    await db_session.flush()
    item = Project(
        id=str(uuid.uuid4()),
        organization_id=org.id,
        created_by=owner.id,
        name="计数项目",
        status="active",
    )
    db_session.add(item)
    await db_session.flush()
    db_session.add(
        ProjectMember(
            id=str(uuid.uuid4()), project_id=item.id, user_id=owner.id, role="owner"
        )
    )
    await db_session.commit()
    return item


async def _make_tool(db: AsyncSession, owner_id: str, slug: str) -> Tool:
    tool = Tool(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        name=f"工具 {slug}",
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(
        id=str(uuid.uuid4()),
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "python_script"},
        is_active=True,
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    await db.flush()
    return tool


async def _make_task(
    db: AsyncSession,
    *,
    owner: User,
    project: Project,
    tool: Tool,
    status: str,
    name: str,
) -> Task:
    task = Task(
        id=str(uuid.uuid4()),
        user_id=owner.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        name=name,
        status=status,
        priority="normal",
        extra_data={"project_id": project.id},
    )
    db.add(task)
    await db.flush()
    return task


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, owner: User) -> AsyncIterator[AsyncClient]:
    async def _get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _get_user() -> User:
        return owner

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_counts_bucket_terminal_failures_together(
    db_session: AsyncSession,
    owner: User,
    project: Project,
    api_client: AsyncClient,
) -> None:
    """失败与超时都算「需要处理」，否则超时任务会从待办里消失。"""
    tool = await _make_tool(db_session, owner.id, "tool-counts-a")
    for status in (
        TaskStatus.RUNNING.value,
        TaskStatus.RUNNING.value,
        TaskStatus.FAILURE.value,
        TaskStatus.TIMEOUT.value,
        TaskStatus.SUCCESS.value,
    ):
        await _make_task(
            db_session,
            owner=owner,
            project=project,
            tool=tool,
            status=status,
            name=f"任务-{status}",
        )
    await db_session.commit()

    response = await api_client.get(
        "/api/v1/tasks/counts", params={"project_id": project.id}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["running"] == 2
    assert data["needs_attention"] == 2
    assert data["recent_results"] == 1


@pytest.mark.asyncio
async def test_tool_slugs_filter_matches_only_requested_tools(
    db_session: AsyncSession,
    owner: User,
    project: Project,
    api_client: AsyncClient,
) -> None:
    design_tool = await _make_tool(db_session, owner.id, "tool-design-x")
    other_tool = await _make_tool(db_session, owner.id, "tool-other-y")
    await _make_task(
        db_session,
        owner=owner,
        project=project,
        tool=design_tool,
        status=TaskStatus.SUCCESS.value,
        name="设计任务",
    )
    await _make_task(
        db_session,
        owner=owner,
        project=project,
        tool=other_tool,
        status=TaskStatus.SUCCESS.value,
        name="别的任务",
    )
    await db_session.commit()

    response = await api_client.get(
        "/api/v1/tasks", params={"project_id": project.id, "tool_slugs": "tool-design-x"}
    )

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["data"]["items"]]
    assert names == ["设计任务"]


@pytest.mark.asyncio
async def test_tool_slugs_filter_rejects_unknown_slug_as_empty(
    db_session: AsyncSession,
    owner: User,
    project: Project,
    api_client: AsyncClient,
) -> None:
    """未注册的 slug 必须返回空列表，不能退化成「不过滤」——否则设计任务页会显示全部任务。"""
    tool = await _make_tool(db_session, owner.id, "tool-known-z")
    await _make_task(
        db_session,
        owner=owner,
        project=project,
        tool=tool,
        status=TaskStatus.SUCCESS.value,
        name="已知任务",
    )
    await db_session.commit()

    response = await api_client.get(
        "/api/v1/tasks", params={"project_id": project.id, "tool_slugs": "no-such-tool"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_task_list_exposes_completed_at_matching_finished_at(
    db_session: AsyncSession,
    owner: User,
    project: Project,
    api_client: AsyncClient,
) -> None:
    """列表项必须同时给出 completed_at（与详情页同名字段），否则前端卡片/管理页永远显示 '-'。"""
    tool = await _make_tool(db_session, owner.id, "tool-completed-at")
    task = await _make_task(
        db_session,
        owner=owner,
        project=project,
        tool=tool,
        status=TaskStatus.SUCCESS.value,
        name="已完成任务",
    )
    finished_at = datetime(2026, 10, 25, 13, 0, 0)
    task.finished_at = finished_at
    await db_session.commit()

    response = await api_client.get("/api/v1/tasks", params={"project_id": project.id})

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    row = next(item for item in items if item["id"] == task.id)
    assert row["finished_at"] is not None
    assert row["completed_at"] is not None
    assert row["completed_at"] == row["finished_at"]
