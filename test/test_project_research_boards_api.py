"""Project-scoped research board ACL and reference validation tests."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.research_boards import (
    create_research_board,
    get_research_board,
    list_research_boards,
)
from app.database.base import Base
from app.models.artifacts import Artifact
from app.models.projects import Organization, Project, ProjectMember
from app.models.users import User
from app.schemas.research_boards import ResearchBoardCreate


@pytest_asyncio.fixture
async def project_board_db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def make_user(email: str, role: str = "user") -> User:
    return User(
        email=email,
        password_hash="hashed-password",
        display_name=email.split("@")[0],
        role=role,
    )


async def create_project(
    db: AsyncSession,
    *,
    owner: User,
    name: str,
    member: User | None = None,
    member_role: str = "viewer",
) -> Project:
    organization = Organization(name=name, slug=name.lower().replace(" ", "-"))
    db.add(organization)
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name=name,
        status="active",
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    if member is not None:
        db.add(
            ProjectMember(project_id=project.id, user_id=member.id, role=member_role)
        )
    await db.commit()
    return project


@pytest.mark.asyncio
async def test_project_member_can_list_and_read_project_board(
    project_board_db: AsyncSession,
):
    owner = make_user("owner@example.com")
    viewer = make_user("viewer@example.com")
    outsider = make_user("outsider@example.com")
    project_board_db.add_all([owner, viewer, outsider])
    await project_board_db.commit()
    project = await create_project(
        project_board_db,
        owner=owner,
        name="Pocket Study",
        member=viewer,
        member_role="viewer",
    )

    created = await create_research_board(
        ResearchBoardCreate(name="Project board", project_id=project.id),
        owner,
        project_board_db,
    )
    listed = await list_research_boards(
        page=1,
        page_size=20,
        project_id=project.id,
        current_user=viewer,
        db=project_board_db,
    )
    loaded = await get_research_board(created["data"]["id"], viewer, project_board_db)

    assert [item["id"] for item in listed["data"]["items"]] == [created["data"]["id"]]
    assert loaded["data"]["project_id"] == project.id
    with pytest.raises(HTTPException) as exc:
        await get_research_board(created["data"]["id"], outsider, project_board_db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_project_board_rejects_cross_project_artifact_reference(
    project_board_db: AsyncSession,
):
    owner = make_user("owner@example.com")
    project_board_db.add(owner)
    await project_board_db.commit()
    source_project = await create_project(project_board_db, owner=owner, name="Source")
    other_project = await create_project(project_board_db, owner=owner, name="Other")
    artifact = Artifact(
        project_id=other_project.id,
        created_by=owner.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        name="other.pdb",
    )
    project_board_db.add(artifact)
    await project_board_db.commit()

    with pytest.raises(HTTPException) as exc:
        await create_research_board(
            ResearchBoardCreate(
                name="Invalid artifact",
                project_id=source_project.id,
                content={
                    "nodes": [
                        {
                            "id": "artifact-1",
                            "type": "artifact",
                            "position": {"x": 0, "y": 0},
                            "artifact_id": artifact.id,
                        }
                    ],
                    "edges": [],
                    "viewport": {"x": 0, "y": 0, "zoom": 1},
                },
            ),
            owner,
            project_board_db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_legacy_owner_board_access_still_works(project_board_db: AsyncSession):
    owner = make_user("owner@example.com")
    other = make_user("other@example.com")
    admin = make_user("admin@example.com", role="admin")
    project_board_db.add_all([owner, other, admin])
    await project_board_db.commit()

    created = await create_research_board(
        ResearchBoardCreate(name="Legacy board"),
        owner,
        project_board_db,
    )

    loaded = await get_research_board(created["data"]["id"], owner, project_board_db)
    assert loaded["data"]["project_id"] is None
    assert (await get_research_board(created["data"]["id"], admin, project_board_db))[
        "data"
    ]["id"] == created["data"]["id"]
    with pytest.raises(HTTPException) as exc:
        await get_research_board(created["data"]["id"], other, project_board_db)
    assert exc.value.status_code == 404
