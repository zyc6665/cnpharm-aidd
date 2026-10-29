"""RBAC matrix and guard tests (plan §4, Task 2).

Covers the declarative truth table for every project role × action, plus the
platform-admin bypass that turns a would-be 404 into a 200.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
import httpx
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import projects as _project_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _user_models  # noqa: F401,E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services.rbac import (  # noqa: E402
    PROJECT_ACTIONS,
    PROJECT_ROLE_RANK,
    require_project_action,
    role_allows,
)


ROLE_ACTION_EXPECTED = {
    "viewer": {"read": True, "run": False, "write": False, "admin": False},
    "runner": {"read": True, "run": True, "write": False, "admin": False},
    "editor": {"read": True, "run": True, "write": True, "admin": False},
    "owner": {"read": True, "run": True, "write": True, "admin": True},
}


def test_role_rank_is_strictly_ordered() -> None:
    assert PROJECT_ROLE_RANK == {"viewer": 1, "runner": 2, "editor": 3, "owner": 4}
    assert set(PROJECT_ACTIONS) == {"read", "run", "write", "admin"}


@pytest.mark.parametrize("role", list(ROLE_ACTION_EXPECTED))
@pytest.mark.parametrize("action", ["read", "run", "write", "admin"])
def test_role_allows_truth_table(role: str, action: str) -> None:
    assert role_allows(role, action) is ROLE_ACTION_EXPECTED[role][action]


def test_role_allows_fails_closed_for_unknown_inputs() -> None:
    assert role_allows(None, "read") is False
    assert role_allows("admin", "read") is False  # admin is not a project role
    assert role_allows("viewer", "unknown") is False


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
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _create_user(db: AsyncSession, email: str, role: str) -> User:
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
async def scene(db_session: AsyncSession) -> dict[str, object]:
    users = {}
    for role in ("viewer", "runner", "editor", "owner"):
        users[role] = await _create_user(db_session, f"{role}@example.com", UserRole.USER.value)
    users["outsider"] = await _create_user(db_session, "outsider@example.com", UserRole.USER.value)
    users["admin"] = await _create_user(
        db_session, "admin@example.com", UserRole.ADMIN.value
    )
    organization = Organization(name="RBAC Lab", slug="rbac-lab")
    db_session.add(organization)
    await db_session.flush()
    project = Project(
        organization_id=organization.id,
        created_by=users["owner"].id,
        name="RBAC project",
        status="active",
    )
    db_session.add(project)
    await db_session.flush()
    for role in ("viewer", "runner", "editor", "owner"):
        db_session.add(
            ProjectMember(
                project_id=project.id, user_id=users[role].id, role=role
            )
        )
    await db_session.commit()
    await db_session.refresh(project)
    return {"users": users, "project": project}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["viewer", "runner", "editor", "owner"])
@pytest.mark.parametrize("action", ["read", "run", "write", "admin"])
async def test_require_project_action_matrix(
    db_session: AsyncSession, scene: dict[str, object], role: str, action: str
) -> None:
    users = scene["users"]
    project = scene["project"]
    expected = ROLE_ACTION_EXPECTED[role][action]
    if expected:
        resolved_project, membership = await require_project_action(
            db_session,
            project_id=project.id,
            user=users[role],
            action=action,
        )
        assert resolved_project.id == project.id
        assert membership is not None and membership.role == role
    else:
        with pytest.raises(HTTPException) as exc_info:
            await require_project_action(
                db_session,
                project_id=project.id,
                user=users[role],
                action=action,
            )
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_non_member_gets_404(db_session: AsyncSession, scene: dict[str, object]) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_project_action(
            db_session,
            project_id=scene["project"].id,
            user=scene["users"]["outsider"],
            action="read",
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["read", "run", "write", "admin"])
async def test_admin_bypasses_membership(
    db_session: AsyncSession, scene: dict[str, object], action: str
) -> None:
    admin = scene["users"]["admin"]
    project = scene["project"]
    resolved_project, membership = await require_project_action(
        db_session,
        project_id=project.id,
        user=admin,
        action=action,
    )
    assert resolved_project.id == project.id
    # Admin has no ProjectMember row, so membership is legitimately None.
    assert membership is None


@pytest.mark.asyncio
async def test_unknown_action_is_rejected(db_session: AsyncSession, scene: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        await require_project_action(
            db_session,
            project_id=scene["project"].id,
            user=scene["users"]["owner"],
            action="destroy",
        )


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, scene: dict[str, object]):
    users = scene["users"]

    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None)
    ) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in users:
            return users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_can_read_non_member_project_via_api(
    api_client: httpx.AsyncClient, scene: dict[str, object]
) -> None:
    project = scene["project"]
    admin_response = await api_client.get(
        f"/api/v1/projects/{project.id}",
        headers={"Authorization": "Bearer admin"},
    )
    outsider_response = await api_client.get(
        f"/api/v1/projects/{project.id}",
        headers={"Authorization": "Bearer outsider"},
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["data"]["membership"] is None
    assert outsider_response.status_code == 404

