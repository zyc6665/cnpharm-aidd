"""Research project API tests."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.agent import AgentRun, AgentRunStep
from app.models.conversations import (
    AgentEvent,
    Conversation,
    ConversationBranch,
    ConversationMessage,
    PlanDecision,
    PlanVersion,
)
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session
    await engine.dispose()


async def _create_user(db: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        display_name=email.split("@")[0],
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def users(db_session: AsyncSession) -> dict[str, User]:
    return {
        "owner": await _create_user(db_session, "owner@example.com"),
        "other": await _create_user(db_session, "other@example.com"),
    }


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, users: dict[str, User]):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(authorization: str | None = Header(default=None)) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in users:
            return users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client
    app.dependency_overrides.clear()


async def _create_project(client: httpx.AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/projects",
        headers={"Authorization": "Bearer owner"},
        json={"name": "Pocket study", "goal": "Identify ligandable pockets"},
    )
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.asyncio
async def test_project_owner_can_create_and_read_project(api_client: httpx.AsyncClient):
    project = await _create_project(api_client)

    response = await api_client.get(
        f"/api/v1/projects/{project['id']}",
        headers={"Authorization": "Bearer owner"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Pocket study"
    assert response.json()["data"]["membership"]["role"] == "owner"


@pytest.mark.asyncio
async def test_project_is_not_enumerable_by_non_member(api_client: httpx.AsyncClient):
    project = await _create_project(api_client)

    response = await api_client.get(
        f"/api/v1/projects/{project['id']}",
        headers={"Authorization": "Bearer other"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_viewer_cannot_update_project(api_client: httpx.AsyncClient):
    project = await _create_project(api_client)
    member_response = await api_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers={"Authorization": "Bearer owner"},
        json={"email": "other@example.com", "role": "viewer"},
    )
    assert member_response.status_code == 200

    response = await api_client.patch(
        f"/api/v1/projects/{project['id']}",
        headers={"Authorization": "Bearer other"},
        json={"name": "Unauthorized rename"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_archive_project_and_default_list_hides_it(
    api_client: httpx.AsyncClient,
):
    project = await _create_project(api_client)

    archive_response = await api_client.post(
        f"/api/v1/projects/{project['id']}/archive",
        headers={"Authorization": "Bearer owner"},
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["data"]["status"] == "archived"

    list_response = await api_client.get(
        "/api/v1/projects",
        headers={"Authorization": "Bearer owner"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"] == []

    archived_response = await api_client.get(
        "/api/v1/projects?include_archived=true",
        headers={"Authorization": "Bearer owner"},
    )
    assert archived_response.status_code == 200
    assert archived_response.json()["data"]["items"][0]["id"] == project["id"]


@pytest.mark.asyncio
async def test_owner_can_delete_project_and_non_member_cannot(
    api_client: httpx.AsyncClient,
):
    project = await _create_project(api_client)

    forbidden_response = await api_client.delete(
        f"/api/v1/projects/{project['id']}",
        headers={"Authorization": "Bearer other"},
    )
    assert forbidden_response.status_code == 404

    delete_response = await api_client.delete(
        f"/api/v1/projects/{project['id']}",
        headers={"Authorization": "Bearer owner"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["id"] == project["id"]

    get_response = await api_client.get(
        f"/api/v1/projects/{project['id']}",
        headers={"Authorization": "Bearer owner"},
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_owner_can_delete_project_with_conversation_plan_dependencies(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
):
    project = await _create_project(api_client)
    owner = users["owner"]

    conversation = Conversation(
        project_id=project["id"],
        created_by=owner.id,
        title="口袋研究会话",
    )
    db_session.add(conversation)
    await db_session.flush()

    branch = ConversationBranch(
        conversation_id=conversation.id,
        created_by=owner.id,
        title="主分支",
        is_root=True,
    )
    db_session.add(branch)
    await db_session.flush()

    db_session.add(
        ConversationMessage(
            conversation_id=conversation.id,
            branch_id=branch.id,
            author_id=owner.id,
            role="user",
            content=[{"type": "text", "text": "开始研究"}],
            plain_text="开始研究",
            sequence=1,
        )
    )
    plan_version = PlanVersion(
        project_id=project["id"],
        conversation_id=conversation.id,
        created_by=owner.id,
        version=1,
        content={"steps": []},
        status="approved",
    )
    db_session.add(plan_version)
    await db_session.flush()
    db_session.add(
        PlanDecision(
            plan_version_id=plan_version.id,
            reviewer_id=owner.id,
            decision="approve",
        )
    )
    await db_session.commit()

    delete_response = await api_client.delete(
        f"/api/v1/projects/{project['id']}",
        headers={"Authorization": "Bearer owner"},
    )

    assert delete_response.status_code == 200
    assert (
        await db_session.execute(
            select(Conversation).where(Conversation.project_id == project["id"])
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(PlanVersion).where(PlanVersion.project_id == project["id"])
        )
    ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_owner_delete_project_removes_project_agent_runs(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
):
    project = await _create_project(api_client)
    owner = users["owner"]

    run = AgentRun(
        project_id=project["id"],
        user_id=owner.id,
        message="project agent run",
        intent="pocket_exploration",
        status="success",
        input_type="protein_pdb",
        requested_outputs=["binding_pocket@1"],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    step = AgentRunStep(
        agent_run_id=run.id,
        step_key="pocket_prediction",
        tool_slug="lvpocket",
        status="success",
        sort_order=0,
    )
    db_session.add(step)
    db_session.add(
        AgentEvent(
            agent_run_id=run.id,
            sequence=1,
            event_type="run.completed",
            payload={},
        )
    )
    await db_session.commit()

    response = await api_client.delete(
        f"/api/v1/projects/{project['id']}",
        headers={"Authorization": "Bearer owner"},
    )

    assert response.status_code == 200
    assert await db_session.get(AgentRun, run.id) is None
    assert (
        await db_session.execute(
            select(AgentRunStep).where(AgentRunStep.agent_run_id == run.id)
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(AgentEvent).where(AgentEvent.agent_run_id == run.id)
        )
    ).scalar_one_or_none() is None
