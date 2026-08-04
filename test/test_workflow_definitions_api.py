import sys
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1.workflows import (  # noqa: E402
    create_workflow_definition,
    delete_workflow_definition,
    get_workflow_definition,
    list_workflow_definitions,
    update_workflow_definition,
)
from app.database.base import Base  # noqa: E402
from app.models import projects as _projects, users as _users, workflows as _workflows  # noqa: F401,E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.users import User  # noqa: E402
from app.schemas.workflows import WorkflowDefinitionCreate, WorkflowDefinitionUpdate  # noqa: E402


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session

    await engine.dispose()


def _user(email: str) -> User:
    return User(
        email=email,
        password_hash="test",
        display_name=email.split("@")[0],
        status="active",
    )


def _payload(name: str = "AIDD workflow") -> WorkflowDefinitionCreate:
    return WorkflowDefinitionCreate(
        name=name,
        canvas_preset_id="aidd-template",
        nodes=[{"id": "input-protein", "position": {"x": 96, "y": 120}}],
        edges=[{"id": "edge-1", "source": "input-protein", "target": "tool-pocket"}],
        selected_tool_by_node={"tool-pocket": "pocket-explorer"},
        artifact_bindings_by_node={"tool-pocket": {"protein": "file-1"}},
    )


async def _create_project(db_session, owner: User, name: str = "EGFR research") -> Project:
    organization = Organization(name=f"{name} org", slug=name.lower().replace(" ", "-"))
    project = Project(
        organization=organization,
        created_by=owner.id,
        name=name,
        goal="Find ligandable pockets",
        status="active",
    )
    db_session.add_all([organization, project])
    await db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    await db_session.commit()
    return project


@pytest.mark.asyncio
async def test_create_list_update_and_delete_workflow_definition(db_session):
    user = _user("owner@example.com")
    db_session.add(user)
    await db_session.commit()

    created = await create_workflow_definition(_payload(), user, db_session)
    created_id = created["data"]["id"]

    listed = await list_workflow_definitions(page=1, page_size=20, current_user=user, db=db_session)
    assert listed["data"]["total"] == 1
    assert listed["data"]["items"][0]["name"] == "AIDD workflow"

    loaded = await get_workflow_definition(created_id, user, db_session)
    assert loaded["data"]["selected_tool_by_node"]["tool-pocket"] == "pocket-explorer"

    updated = await update_workflow_definition(
        created_id,
        WorkflowDefinitionUpdate(name="Saved canvas", nodes=[{"id": "tool-pocket"}]),
        user,
        db_session,
    )
    assert updated["data"]["name"] == "Saved canvas"
    assert updated["data"]["nodes"][0]["id"] == "tool-pocket"

    deleted = await delete_workflow_definition(created_id, user, db_session)
    assert deleted["message"] == "工作流已删除"

    with pytest.raises(HTTPException) as exc:
        await get_workflow_definition(created_id, user, db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_workflow_definition_access_is_limited_to_owner(db_session):
    owner = _user("owner@example.com")
    other = _user("other@example.com")
    db_session.add_all([owner, other])
    await db_session.commit()

    created = await create_workflow_definition(_payload("Private workflow"), owner, db_session)

    listed = await list_workflow_definitions(page=1, page_size=20, current_user=other, db=db_session)
    assert listed["data"]["total"] == 0

    with pytest.raises(HTTPException) as exc:
        await get_workflow_definition(created["data"]["id"], other, db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_workflow_definitions_can_be_scoped_to_project(db_session):
    owner = _user("owner@example.com")
    db_session.add(owner)
    await db_session.flush()
    project = await _create_project(db_session, owner)

    project_payload = _payload("Project draft").model_copy(
        update={"project_id": project.id}
    )
    created = await create_workflow_definition(project_payload, owner, db_session)
    assert created["data"]["project_id"] == project.id

    global_created = await create_workflow_definition(
        _payload("Global workflow"), owner, db_session
    )
    assert global_created["data"]["project_id"] is None

    listed = await list_workflow_definitions(
        page=1,
        page_size=20,
        project_id=project.id,
        current_user=owner,
        db=db_session,
    )

    assert listed["data"]["total"] == 1
    assert listed["data"]["items"][0]["name"] == "Project draft"
    assert listed["data"]["items"][0]["project_id"] == project.id


@pytest.mark.asyncio
async def test_project_members_can_read_project_workflow_definitions(db_session):
    owner = _user("owner@example.com")
    member = _user("member@example.com")
    db_session.add_all([owner, member])
    await db_session.flush()
    project = await _create_project(db_session, owner)
    db_session.add(ProjectMember(project_id=project.id, user_id=member.id, role="editor"))
    await db_session.commit()

    project_payload = _payload("Shared project draft").model_copy(
        update={"project_id": project.id}
    )
    created = await create_workflow_definition(project_payload, owner, db_session)

    listed = await list_workflow_definitions(
        page=1,
        page_size=20,
        project_id=project.id,
        current_user=member,
        db=db_session,
    )
    loaded = await get_workflow_definition(created["data"]["id"], member, db_session)

    assert listed["data"]["total"] == 1
    assert listed["data"]["items"][0]["id"] == created["data"]["id"]
    assert loaded["data"]["name"] == "Shared project draft"


@pytest.mark.asyncio
async def test_project_workflow_definition_requires_membership(db_session):
    owner = _user("owner@example.com")
    outsider = _user("outsider@example.com")
    db_session.add_all([owner, outsider])
    await db_session.flush()
    project = await _create_project(db_session, owner)

    payload = _payload("Unauthorized draft").model_copy(
        update={"project_id": project.id}
    )

    with pytest.raises(HTTPException) as create_exc:
        await create_workflow_definition(payload, outsider, db_session)
    assert create_exc.value.status_code == 404

    with pytest.raises(HTTPException) as list_exc:
        await list_workflow_definitions(
            page=1,
            page_size=20,
            project_id=project.id,
            current_user=outsider,
            db=db_session,
        )
    assert list_exc.value.status_code == 404
