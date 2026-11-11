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
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.models.workflows import WorkflowDefinition
from app.logging.audit import AuditAction, ResourceType, get_audit_logger


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
async def test_project_overview_returns_project_scoped_resources(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
):
    project = await _create_project(api_client)
    owner = users["owner"]
    tool = Tool(owner_id=owner.id, name="LVpocket", slug="lvpocket", status="published")
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(tool_id=tool.id, version="1.0", config={})
    db_session.add(version)
    await db_session.flush()
    db_session.add(
        Task(
            user_id=owner.id,
            tool_id=tool.id,
            tool_version_id=version.id,
            name="项目口袋识别",
            status=TaskStatus.RUNNING.value,
            progress=35,
            extra_data={"project_id": project["id"]},
        )
    )
    artifact = Artifact(
        project_id=project["id"],
        created_by=owner.id,
        artifact_type="binding_pocket",
        semantic_type="binding_pocket",
        standard_type="binding_pocket",
        standard_version=1,
        name="EGFR pocket",
    )
    db_session.add(artifact)
    await db_session.flush()
    artifact_version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename="egfr-pocket.pdb",
        content_type="chemical/x-pdb",
        size_bytes=2048,
        sha256="a" * 64,
        storage_key="artifacts/egfr-pocket.pdb",
        status="available",
    )
    db_session.add(artifact_version)
    await db_session.flush()
    artifact.latest_version_id = artifact_version.id
    db_session.add_all(
        [
            WorkflowDefinition(
                project_id=project["id"],
                user_id=owner.id,
                name="口袋到分子生成",
                canvas_preset_id="project-workflow",
                nodes=[],
                edges=[],
                selected_tool_by_node={},
                artifact_bindings_by_node={},
                status="draft",
            ),
        ]
    )
    await db_session.commit()

    response = await api_client.get(
        f"/api/v1/projects/{project['id']}/overview",
        headers={"Authorization": "Bearer owner"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project"]["id"] == project["id"]
    assert data["counts"] == {
        "artifacts": 1,
        "tasks": 1,
        "workflows": 1,
        "targets": 0,
        "structures": 0,
        "pockets": 0,
        "candidates": 0,
        "candidate_sets": 0,
    }
    assert data["tasks"][0]["name"] == "项目口袋识别"
    assert data["tasks"][0]["status"] == "running"
    assert data["artifacts"][0]["latest_version"]["id"] == artifact_version.id
    assert data["workflows"][0]["name"] == "口袋到分子生成"


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
async def test_owner_can_manage_project_members(api_client: httpx.AsyncClient):
    project = await _create_project(api_client)
    add_response = await api_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers={"Authorization": "Bearer owner"},
        json={"email": "other@example.com", "role": "viewer"},
    )
    assert add_response.status_code == 200
    member_id = add_response.json()["data"]["id"]

    list_response = await api_client.get(
        f"/api/v1/projects/{project['id']}/members",
        headers={"Authorization": "Bearer owner"},
    )
    assert list_response.status_code == 200
    members = list_response.json()["data"]["items"]
    assert [(item["email"], item["role"]) for item in members] == [
        ("owner@example.com", "owner"),
        ("other@example.com", "viewer"),
    ]

    update_response = await api_client.patch(
        f"/api/v1/projects/{project['id']}/members/{member_id}",
        headers={"Authorization": "Bearer owner"},
        json={"role": "runner"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["role"] == "runner"

    forbidden_response = await api_client.delete(
        f"/api/v1/projects/{project['id']}/members/{member_id}",
        headers={"Authorization": "Bearer other"},
    )
    assert forbidden_response.status_code == 403

    delete_response = await api_client.delete(
        f"/api/v1/projects/{project['id']}/members/{member_id}",
        headers={"Authorization": "Bearer owner"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["id"] == member_id

    owner_membership_id = project["membership"]["id"]
    remove_owner_response = await api_client.delete(
        f"/api/v1/projects/{project['id']}/members/{owner_membership_id}",
        headers={"Authorization": "Bearer owner"},
    )
    assert remove_owner_response.status_code == 400


@pytest.mark.asyncio
async def test_owner_can_add_project_member_by_username(
    api_client: httpx.AsyncClient,
):
    project = await _create_project(api_client)
    response = await api_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers={"Authorization": "Bearer owner"},
        json={"username": "other", "role": "viewer"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["username"] == "other"
    assert payload["email"] == "other@example.com"


@pytest.mark.asyncio
async def test_owner_can_archive_project_and_default_list_hides_it(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    project = await _create_project(api_client)

    events: list = []
    audit_logger = get_audit_logger()
    monkeypatch.setattr(audit_logger, "enable_file_logging", False)
    monkeypatch.setattr(audit_logger, "enable_db_logging", True)
    monkeypatch.setattr(audit_logger, "_db_writer", events.append)

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

    # 归档是「从列表里移走」，不是终态：详情必须能打开，否则用户连看看都做不到。
    detail_response = await api_client.get(
        f"/api/v1/projects/{project['id']}",
        headers={"Authorization": "Bearer owner"},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["status"] == "archived"

    # 撤销归档后回到默认列表。
    unarchive_response = await api_client.post(
        f"/api/v1/projects/{project['id']}/unarchive",
        headers={"Authorization": "Bearer owner"},
    )
    assert unarchive_response.status_code == 200
    assert unarchive_response.json()["data"]["status"] == "active"

    restored_list = await api_client.get(
        "/api/v1/projects",
        headers={"Authorization": "Bearer owner"},
    )
    assert [item["id"] for item in restored_list.json()["data"]["items"]] == [project["id"]]

    # 重复撤销归档要明确报冲突，而不是静默把 active 又写一遍——
    # 静默成功会让前端以为「归档中」的状态被采纳，掩盖真实的并发操作。
    repeated = await api_client.post(
        f"/api/v1/projects/{project['id']}/unarchive",
        headers={"Authorization": "Bearer owner"},
    )
    assert repeated.status_code == 409

    archive_events = [
        event
        for event in events
        if event.resource_type is ResourceType.PROJECT and event.resource_id == project["id"]
    ]
    assert [event.extra["status"] for event in archive_events] == ["archived", "active"]
    assert all(event.action is AuditAction.UPDATE for event in archive_events)
    assert archive_events[0].resource_name == project["name"]



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


