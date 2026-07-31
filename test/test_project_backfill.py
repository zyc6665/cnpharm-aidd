"""Legacy resource to research project backfill tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models.agent import AgentRun
from app.models.files import File
from app.models.projects import Project, ProjectMember
from app.models.users import User, UserRole, UserStatus
from app.models.workflows import ResearchBoard, WorkflowDefinition, WorkflowRun, WorkflowTemplate


@pytest.mark.asyncio
async def test_backfill_legacy_resources_is_idempotent_and_preserves_history():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = User(
            email="legacy@example.com",
            password_hash="hashed-password",
            display_name="Legacy User",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        db.add(user)
        await db.flush()

        original_created_at = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        resources = [
            File(
                owner_id=user.id,
                filename="protein.pdb",
                size_bytes=42,
                sha256="a" * 64,
                storage_path="legacy/protein.pdb",
                created_at=original_created_at,
            ),
            AgentRun(
                user_id=user.id,
                message="Find pockets",
                intent="pocket_detection",
                input_type="protein_structure",
                created_at=original_created_at,
            ),
            WorkflowDefinition(
                user_id=user.id,
                name="Legacy definition",
                template_id="legacy-pocket",
                created_at=original_created_at,
            ),
            WorkflowTemplate(
                owner_id=user.id,
                name="Legacy template",
                created_at=original_created_at,
            ),
            WorkflowRun(
                owner_id=user.id,
                name="Legacy run",
                created_at=original_created_at,
            ),
            ResearchBoard(
                owner_id=user.id,
                name="Legacy board",
                content={"nodes": [{"id": "note-1", "text": "keep me"}]},
                created_at=original_created_at,
            ),
        ]
        db.add_all(resources)
        await db.commit()

        from app.services.project_migration import backfill_legacy_projects

        first = await backfill_legacy_projects(db)
        second = await backfill_legacy_projects(db)

        projects = (await db.execute(select(Project))).scalars().all()
        memberships = (await db.execute(select(ProjectMember))).scalars().all()
        assert len(projects) == 1
        assert len(memberships) == 1
        assert memberships[0].role == "owner"
        assert first.projects_created == 1
        assert first.resources_linked == 6
        assert second.projects_created == 0
        assert second.resources_linked == 0

        for resource in resources:
            await db.refresh(resource)
            assert resource.project_id == projects[0].id
            assert resource.created_at.replace(tzinfo=timezone.utc) == original_created_at

        board = resources[-1]
        assert board.content == {"nodes": [{"id": "note-1", "text": "keep me"}]}

    await engine.dispose()
