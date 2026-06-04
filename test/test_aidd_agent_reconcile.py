"""AIDD agent task reconciliation tests."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.service import reconcile_waiting_agent_steps  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.models import agent as _agent_models  # noqa: F401,E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.agent import AgentRun, AgentRunStep  # noqa: E402
from app.models.files import File as FileModel, FileSourceType  # noqa: E402
from app.models.tasks import Task, TaskOutput, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402


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


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    user_record = User(
        email="owner@example.com",
        password_hash="hashed-password",
        display_name="Owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user_record)
    await db_session.commit()
    await db_session.refresh(user_record)
    return user_record


async def create_tool(db_session: AsyncSession, owner: User, *, slug: str, name: str) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name=name,
        slug=slug,
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
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest.mark.asyncio
async def test_successful_step_extracts_output_and_schedules_downstream(
    db_session: AsyncSession,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lvpocket = await create_tool(
        db_session,
        user,
        slug="lvpocket-pocket-prediction",
        name="LVpocket",
    )
    await create_tool(
        db_session,
        user,
        slug="gcdm-pocket-generation",
        name="STD-Diff",
    )

    input_file = FileModel(
        owner_id=user.id,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"protein").hexdigest(),
        source_type=FileSourceType.UPLOAD.value,
        storage_path="/tmp/protein.pdb",
    )
    output_file = FileModel(
        owner_id=user.id,
        filename="best_pocket.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"pocket").hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path="/tmp/best_pocket.pdb",
    )
    db_session.add_all([input_file, output_file])
    await db_session.flush()

    task = Task(
        user_id=user.id,
        tool_id=lvpocket.id,
        tool_version_id=lvpocket.current_version_id,
        status=TaskStatus.SUCCESS.value,
        progress=1.0,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(
        TaskOutput(
            task_id=task.id,
            result={"ok": True},
            file_ids=[output_file.id],
            output_type="file",
        )
    )

    run = AgentRun(
        user_id=user.id,
        message="生成分子",
        intent="generate_molecules_from_protein",
        status="waiting_task",
        input_type="protein_pdb",
        input_file_id=input_file.id,
        requested_outputs=["generated_ligand"],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    first_step = AgentRunStep(
        agent_run_id=run.id,
        step_key="pocket_prediction",
        tool_slug="lvpocket-pocket-prediction",
        tool_id=lvpocket.id,
        task_id=task.id,
        status="waiting_task",
        sort_order=0,
        semantic_inputs={"protein_pdb": "agent_input"},
        params={},
    )
    second_step = AgentRunStep(
        agent_run_id=run.id,
        step_key="molecule_generation",
        tool_slug="gcdm-pocket-generation",
        status="pending",
        sort_order=1,
        depends_on_step_ids=["pocket_prediction"],
        semantic_inputs={"pocket_pdb": "step:pocket_prediction:pocket_pdb"},
        params={"params.n_samples": 8},
    )
    db_session.add_all([first_step, second_step])
    await db_session.commit()

    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        return SimpleNamespace(id="task-generation", tool_id=task_data.tool_id)

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )

    count = await reconcile_waiting_agent_steps(db_session, run_id=run.id)

    assert count == 1
    refreshed_first = await db_session.get(AgentRunStep, first_step.id)
    refreshed_second = await db_session.get(AgentRunStep, second_step.id)
    assert refreshed_first.status == "success"
    assert refreshed_first.semantic_outputs["pocket_pdb"]["file_id"] == output_file.id
    assert refreshed_second.status == "waiting_task"
    assert refreshed_second.task_id == "task-generation"


@pytest.mark.asyncio
async def test_failed_task_marks_agent_run_failure(
    db_session: AsyncSession,
    user: User,
) -> None:
    lvpocket = await create_tool(
        db_session,
        user,
        slug="lvpocket-pocket-prediction",
        name="LVpocket",
    )
    task = Task(
        user_id=user.id,
        tool_id=lvpocket.id,
        tool_version_id=lvpocket.current_version_id,
        status=TaskStatus.FAILURE.value,
        progress=0.5,
        error_message="boom",
    )
    db_session.add(task)
    await db_session.flush()
    run = AgentRun(
        user_id=user.id,
        message="生成分子",
        intent="generate_molecules_from_protein",
        status="waiting_task",
        input_type="protein_pdb",
        requested_outputs=["generated_ligand"],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    step = AgentRunStep(
        agent_run_id=run.id,
        step_key="pocket_prediction",
        tool_slug="lvpocket-pocket-prediction",
        tool_id=lvpocket.id,
        task_id=task.id,
        status="waiting_task",
        sort_order=0,
    )
    db_session.add(step)
    await db_session.commit()

    count = await reconcile_waiting_agent_steps(db_session, run_id=run.id)

    assert count == 1
    refreshed_run = await db_session.get(AgentRun, run.id)
    refreshed_step = await db_session.get(AgentRunStep, step.id)
    assert refreshed_run.status == "failure"
    assert refreshed_step.status == "failure"
    assert refreshed_step.error_message == "boom"
