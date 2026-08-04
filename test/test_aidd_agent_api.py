"""AIDD legacy API shutdown tests and internal service guards."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import get_current_user  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import agent as _agent_models  # noqa: F401,E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import system_settings as _system_settings  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.agent import AgentRun, AgentRunStep  # noqa: E402
from app.models.tasks import Task, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402


LEGACY_REPLACEMENT = "/api/v1/projects/{project_id}/conversations"


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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


async def create_user(db_session: AsyncSession, *, email: str) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        display_name=email.split("@")[0],
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def current_user(db_session: AsyncSession) -> User:
    return await create_user(db_session, email="owner@example.com")


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, current_user: User):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == "Bearer owner-token":
            return current_user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


async def create_tool(
    db_session: AsyncSession,
    owner: User,
    *,
    slug: str,
    name: str,
) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name=name,
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "ssh_job"},
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


def _legacy_run_payload() -> dict[str, Any]:
    return {
        "message": "旧智能体入口应返回迁移提示",
        "input_file_id": "00000000-0000-0000-0000-000000000000",
        "requested_outputs": ["generated_ligand"],
    }


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("post", "/api/v1/agents/aidd/workflow-drafts", {"json": _legacy_run_payload()}),
        ("post", "/api/v1/agents/aidd/runs", {"json": _legacy_run_payload()}),
        ("get", "/api/v1/agents/aidd/runs", {}),
        ("get", "/api/v1/agents/aidd/runs/run-1", {}),
        ("post", "/api/v1/agents/aidd/runs/run-1/cancel", {}),
        ("delete", "/api/v1/agents/aidd/runs/run-1", {}),
        ("post", "/api/v1/agents/aidd/runs/run-1/sync", {}),
    ],
)
@pytest.mark.asyncio
async def test_legacy_aidd_api_endpoints_return_gone(
    api_client: httpx.AsyncClient,
    method: str,
    path: str,
    kwargs: dict[str, Any],
):
    response = await getattr(api_client, method)(
        path,
        headers={"Authorization": "Bearer owner-token"},
        **kwargs,
    )

    assert response.status_code == 410
    assert response.json()["detail"] == {
        "message": "旧 AIDD API 已下线，请使用项目会话 Agent Run 接口",
        "replacement": LEGACY_REPLACEMENT,
    }


@pytest.mark.asyncio
async def test_legacy_aidd_api_gone_does_not_create_agent_runs(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    response = await api_client.post(
        "/api/v1/agents/aidd/runs",
        headers={"Authorization": "Bearer owner-token"},
        json=_legacy_run_payload(),
    )

    assert response.status_code == 410
    assert await db_session.scalar(select(func.count()).select_from(AgentRun)) == 0


@pytest.mark.asyncio
async def test_legacy_aidd_api_still_requires_authentication(api_client: httpx.AsyncClient):
    response = await api_client.get("/api/v1/agents/aidd/runs")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cancel_agent_run_cancels_linked_platform_task(
    db_session: AsyncSession,
    current_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.aidd.service import cancel_agent_run

    tool = await create_tool(
        db_session,
        current_user,
        slug="gcdm-pocket-generation",
        name="STD-Diff",
    )
    task = Task(
        user_id=current_user.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        status=TaskStatus.PENDING.value,
    )
    db_session.add(task)
    await db_session.flush()
    run = AgentRun(
        user_id=current_user.id,
        message="cancel me",
        intent="molecule_generation",
        status="waiting_task",
        input_type="protein_pdb",
        requested_outputs=[],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(
        AgentRunStep(
            agent_run_id=run.id,
            step_key="molecule_generation",
            tool_slug=tool.slug,
            task_id=task.id,
            status="waiting_task",
            sort_order=0,
        )
    )
    await db_session.commit()

    canceled_task_ids: list[str] = []

    async def fake_cancel_task(db, *, task, current_user):
        canceled_task_ids.append(task.id)
        task.status = TaskStatus.CANCELED.value

    monkeypatch.setattr("app.agents.aidd.service.cancel_platform_task", fake_cancel_task)

    canceled_run = await cancel_agent_run(db_session, current_user=current_user, run_id=run.id)

    assert canceled_task_ids == [task.id]
    assert canceled_run.status == "canceled"


@pytest.mark.asyncio
async def test_claim_ready_agent_step_is_atomic(
    db_session: AsyncSession,
    current_user: User,
) -> None:
    from app.agents.aidd.service import claim_agent_step_for_dispatch

    run = AgentRun(
        user_id=current_user.id,
        message="claim me",
        intent="test",
        status="pending",
        input_type="protein_pdb",
        requested_outputs=[],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    step = AgentRunStep(
        agent_run_id=run.id,
        step_key="only_step",
        tool_slug="test-tool",
        status="pending",
        sort_order=0,
    )
    db_session.add(step)
    await db_session.commit()

    assert await claim_agent_step_for_dispatch(db_session, step.id) is True
    assert await claim_agent_step_for_dispatch(db_session, step.id) is False
