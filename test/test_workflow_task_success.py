"""Workflow task success application tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tools as _tools_models  # noqa: F401
from app.models import users as _users_models  # noqa: F401
from app.models.files import File as FileModel, FileSourceType
from app.models.tasks import Task, TaskOutput, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.services.workflow_task_success import apply_successful_task_outputs


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


async def create_owner(db_session: AsyncSession) -> User:
    owner = User(
        email="owner@example.com",
        password_hash="hashed-password",
        display_name="owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(owner)
    await db_session.flush()
    return owner


async def create_pocket_tool(db_session: AsyncSession, owner: User) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name="LVpocket",
        slug="lvpocket-pocket-prediction",
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
    await db_session.flush()
    return tool


@pytest.mark.asyncio
async def test_apply_successful_task_outputs_marks_state_and_lineage(
    db_session: AsyncSession,
) -> None:
    owner = await create_owner(db_session)
    tool = await create_pocket_tool(db_session, owner)
    output_file = FileModel(
        owner_id=owner.id,
        filename="best_pocket.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"pocket").hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path=str(Path("/tmp/best_pocket.pdb")),
        is_public=False,
    )
    task = Task(
        user_id=owner.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        status=TaskStatus.SUCCESS.value,
        extra_data={"project_id": "project-123"},
    )
    db_session.add_all([output_file, task])
    await db_session.flush()
    task_output = TaskOutput(
        task_id=task.id,
        result={"ok": True},
        file_ids=[output_file.id],
    )
    db_session.add(task_output)
    await db_session.flush()
    task.outputs = task_output

    run = SimpleNamespace(project_id=None, status="waiting_task", error_message=None, finished_at=None)
    state = {"status": "waiting_task", "tool_slug": tool.slug, "artifact_outputs": []}
    node_states = {"pocket_prediction": state}
    artifact_lineage = {}

    await apply_successful_task_outputs(
        db_session,
        run=run,
        node_states=node_states,
        artifact_lineage=artifact_lineage,
        node_id="pocket_prediction",
        state=state,
        task=task,
    )

    await db_session.flush()
    await db_session.refresh(output_file)
    assert run.project_id == "project-123"
    assert state["status"] == "success"
    assert state["semantic_outputs"]["pocket_pdb"]["file_id"] == output_file.id
    assert state["output_file_ids"] == [output_file.id]
    assert state["missing_outputs"] == []
    assert artifact_lineage["pocket_prediction"]["pocket_pdb"]["file_id"] == output_file.id
    assert output_file.file_meta["semantic_type"] == "pocket_pdb"
    assert output_file.file_meta["semantic_source"] == "workflow_output"
