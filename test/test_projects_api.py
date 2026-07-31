"""Research project API tests."""

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
