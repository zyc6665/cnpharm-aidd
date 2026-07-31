"""Project conversation, event resume, and plan approval API tests."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def conversation_db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def conversation_users(conversation_db: AsyncSession) -> dict[str, User]:
    users = {}
    for key in ("owner", "runner", "editor", "outsider"):
        user = User(
            email=f"{key}@example.com",
            password_hash="hashed-password",
            display_name=key,
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        conversation_db.add(user)
        users[key] = user
    await conversation_db.commit()
    return users


@pytest_asyncio.fixture
async def conversation_client(
    conversation_db: AsyncSession,
    conversation_users: dict[str, User],
):
    async def override_get_db():
        yield conversation_db

    async def override_get_current_user(authorization: str | None = Header(default=None)) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in conversation_users:
            return conversation_users[token]
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
        json={"name": "AIDD study", "goal": "Find ligandable pockets"},
    )
    assert response.status_code == 200
    return response.json()["data"]


async def _add_member(client: httpx.AsyncClient, project_id: str, key: str, role: str) -> None:
    response = await client.post(
        f"/api/v1/projects/{project_id}/members",
        headers={"Authorization": "Bearer owner"},
        json={"email": f"{key}@example.com", "role": role},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_messages_are_immutable_and_history_edit_creates_branch(
    conversation_client: httpx.AsyncClient,
):
    project = await _create_project(conversation_client)
    headers = {"Authorization": "Bearer owner"}
    first = await conversation_client.post(
        f"/api/v1/projects/{project['id']}/conversations",
        headers=headers,
        json={"title": "Pocket analysis"},
    )
    second = await conversation_client.post(
        f"/api/v1/projects/{project['id']}/conversations",
        headers=headers,
        json={"title": "Ligand design"},
    )
    assert first.status_code == second.status_code == 200

    conversation = first.json()["data"]
    message_response = await conversation_client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={"role": "user", "content": [{"type": "text", "text": "Use chain A"}]},
    )
    assert message_response.status_code == 200
    original = message_response.json()["data"]

    branch_response = await conversation_client.post(
        f"/api/v1/messages/{original['id']}/branch",
        headers=headers,
        json={"content": [{"type": "text", "text": "Use chain B"}]},
    )
    assert branch_response.status_code == 200
    branch_data = branch_response.json()["data"]
    assert branch_data["message"]["parent_message_id"] == original["id"]
    assert branch_data["branch"]["forked_from_message_id"] == original["id"]

    messages = await conversation_client.get(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
    )
    assert messages.status_code == 200
    by_id = {item["id"]: item for item in messages.json()["data"]["items"]}
    assert by_id[original["id"]]["plain_text"] == "Use chain A"
    assert branch_data["message"]["plain_text"] == "Use chain B"


@pytest.mark.asyncio
async def test_agent_events_resume_after_sequence_and_hide_runs_from_outsiders(
    conversation_client: httpx.AsyncClient,
    conversation_db: AsyncSession,
    conversation_users: dict[str, User],
):
    from app.models.agent import AgentRun
    from app.models.conversations import AgentEvent

    project = await _create_project(conversation_client)
    run = AgentRun(
        project_id=project["id"],
        user_id=conversation_users["owner"].id,
        message="Find pockets",
        intent="pocket_detection",
        input_type="protein_structure",
    )
    conversation_db.add(run)
    await conversation_db.flush()
    conversation_db.add_all(
        [
            AgentEvent(agent_run_id=run.id, sequence=sequence, event_type="execution_progress", payload={"progress": sequence * 10})
            for sequence in (1, 2, 3)
        ]
    )
    await conversation_db.commit()

    response = await conversation_client.get(
        f"/api/v1/agent-runs/{run.id}/events?after_sequence=1",
        headers={"Authorization": "Bearer owner"},
    )
    assert response.status_code == 200
    assert [item["sequence"] for item in response.json()["data"]["items"]] == [2, 3]

    hidden = await conversation_client.get(
        f"/api/v1/agent-runs/{run.id}/events",
        headers={"Authorization": "Bearer outsider"},
    )
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_only_owner_or_runner_can_approve_plan(
    conversation_client: httpx.AsyncClient,
    conversation_db: AsyncSession,
    conversation_users: dict[str, User],
):
    from app.models.conversations import PlanVersion

    project = await _create_project(conversation_client)
    await _add_member(conversation_client, project["id"], "runner", "runner")
    await _add_member(conversation_client, project["id"], "editor", "editor")
    plans = [
        PlanVersion(
            project_id=project["id"],
            created_by=conversation_users["owner"].id,
            version=version,
            content={"steps": [{"tool": "lvpocket"}]},
            risk_level="medium",
        )
        for version in (1, 2)
    ]
    conversation_db.add_all(plans)
    await conversation_db.commit()

    forbidden = await conversation_client.post(
        f"/api/v1/plan-versions/{plans[0].id}/approve",
        headers={"Authorization": "Bearer editor"},
        json={"comment": "Looks fine"},
    )
    assert forbidden.status_code == 403

    approved = await conversation_client.post(
        f"/api/v1/plan-versions/{plans[1].id}/approve",
        headers={"Authorization": "Bearer runner"},
        json={"comment": "Approved for execution"},
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "approved"
    assert approved.json()["data"]["decision"]["reviewer_id"] == conversation_users["runner"].id
