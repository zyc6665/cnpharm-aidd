"""Project conversation, event resume, and plan approval API tests."""

from __future__ import annotations

import hashlib

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.database.base import Base
from app.database.session import get_db
from app.execution.contracts import ExecutionHandle, ExecutionState
from app.main import app
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.tool_packages import ToolPackage, ToolPackageVersion
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def conversation_db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, autoflush=False
    )
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


class RecordingExecutionPort:
    def __init__(self) -> None:
        self.requests = []

    async def submit(self, request):
        self.requests.append(request)
        return ExecutionHandle(
            execution_id="execution-project-1", state=ExecutionState.QUEUED
        )


@pytest_asyncio.fixture
async def conversation_execution_port() -> RecordingExecutionPort:
    return RecordingExecutionPort()


@pytest_asyncio.fixture
async def conversation_client(
    conversation_db: AsyncSession,
    conversation_users: dict[str, User],
    conversation_execution_port: RecordingExecutionPort,
):
    from app.api.v1.conversations import get_project_agent_execution_port

    async def override_get_db():
        yield conversation_db

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in conversation_users:
            return conversation_users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_project_agent_execution_port] = (
        lambda: conversation_execution_port
    )
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


async def _add_member(
    client: httpx.AsyncClient, project_id: str, key: str, role: str
) -> None:
    response = await client.post(
        f"/api/v1/projects/{project_id}/members",
        headers={"Authorization": "Bearer owner"},
        json={"email": f"{key}@example.com", "role": role},
    )
    assert response.status_code == 200


async def _seed_lvpocket_package(
    db: AsyncSession,
    owner: User,
) -> ToolPackageVersion:
    package = ToolPackage(
        owner_id=owner.id,
        slug="lvpocket-pocket-prediction",
        name="LVpocket",
        status="published",
    )
    db.add(package)
    await db.flush()
    version = ToolPackageVersion(
        package_id=package.id,
        version="1.0.0",
        manifest={
            "variants": [
                {
                    "name": "nvidia-cuda",
                    "executor_types": ["remote_job"],
                    "resources": {"devices": ["nvidia.com/gpu"], "driver": ">=535"},
                }
            ]
        },
        manifest_digest="b" * 64,
        is_signed=True,
        validation_status="valid",
    )
    db.add(version)
    await db.flush()
    package.current_version_id = version.id
    await db.commit()
    return version


async def _seed_protein_artifact(
    db: AsyncSession,
    owner: User,
    project_id: str,
) -> ArtifactVersion:
    artifact = Artifact(
        project_id=project_id,
        created_by=owner.id,
        artifact_type="protein_structure",
        semantic_type="protein_pdb",
        name="target.pdb",
    )
    db.add(artifact)
    await db.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename="target.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"protein").hexdigest(),
        storage_key="projects/pocket-study/target.pdb",
        status="available",
    )
    db.add(version)
    await db.flush()
    artifact.latest_version_id = version.id
    await db.commit()
    return version


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
            AgentEvent(
                agent_run_id=run.id,
                sequence=sequence,
                event_type="execution_progress",
                payload={"progress": sequence * 10},
            )
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
    assert (
        approved.json()["data"]["decision"]["reviewer_id"]
        == conversation_users["runner"].id
    )


@pytest.mark.asyncio
async def test_project_conversation_can_start_agent_run_and_approval_submits_execution(
    conversation_client: httpx.AsyncClient,
    conversation_db: AsyncSession,
    conversation_users: dict[str, User],
    conversation_execution_port: RecordingExecutionPort,
):
    from app.models.conversations import AgentEvent
    from sqlalchemy import select

    project = await _create_project(conversation_client)
    await _seed_lvpocket_package(conversation_db, conversation_users["owner"])
    protein = await _seed_protein_artifact(
        conversation_db,
        conversation_users["owner"],
        project["id"],
    )
    conversation_response = await conversation_client.post(
        f"/api/v1/projects/{project['id']}/conversations",
        headers={"Authorization": "Bearer owner"},
        json={"title": "Pocket analysis"},
    )
    conversation = conversation_response.json()["data"]

    started = await conversation_client.post(
        f"/api/v1/projects/{project['id']}/conversations/{conversation['id']}/agent-runs",
        headers={"Authorization": "Bearer owner"},
        json={
            "goal": "Find pockets in chain A",
            "protein_artifact_version_id": protein.id,
        },
    )

    assert started.status_code == 200
    started_data = started.json()["data"]
    assert started_data["status"] == "awaiting_approval"
    assert started_data["plan_version"]["status"] == "pending"
    assert started_data["plan_version"]["content"]["goal"] == "Find pockets in chain A"

    approved = await conversation_client.post(
        f"/api/v1/plan-versions/{started_data['plan_version']['id']}/approve",
        headers={"Authorization": "Bearer owner"},
        json={"comment": "Approved"},
    )

    assert approved.status_code == 200
    assert approved.json()["data"]["execution"]["execution_id"] == "execution-project-1"
    assert len(conversation_execution_port.requests) == 1
    request = conversation_execution_port.requests[0]
    assert request.project_id == project["id"]
    assert request.inputs[0].artifact_version_id == protein.id
    events = (
        (
            await conversation_db.execute(
                select(AgentEvent)
                .where(AgentEvent.agent_run_id == started_data["id"])
                .order_by(AgentEvent.sequence)
            )
        )
        .scalars()
        .all()
    )
    assert [event.event_type for event in events] == [
        "plan_created",
        "approval_required",
        "execution_submitted",
        "execution_queued",
    ]
