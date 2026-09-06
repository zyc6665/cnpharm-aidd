from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    File,
    Organization,
    Project,
    Task,
    TaskInput,
    Tool,
    ToolVersion,
    User,
)
from app.models.files import File as FileModel  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.tasks import TaskInput as TaskInputModel  # noqa: E402
from app.models.tools import Tool as ToolModel  # noqa: E402
from app.models.tools import ToolProviderType, ToolStatus  # noqa: E402
from app.models.tools import ToolVersion as ToolVersionModel  # noqa: E402
from app.models.users import User as UserModel  # noqa: E402
from app.models.users import UserRole, UserStatus  # noqa: E402
from app.schemas.tasks import TaskCreate, TaskInputSchema  # noqa: E402
from app.tasks.service import create_and_schedule_tool_task  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_task_create_accepts_standard_input_uploads():
    payload = TaskCreate(
        tool_id="tool-1",
        standard_input_uploads={"protein": "file-1"},
    )

    assert payload.standard_input_uploads == {"protein": "file-1"}


def test_task_input_schema_accepts_standard_input_uploads():
    payload = TaskInputSchema(
        params={},
        standard_input_uploads={"ligand": "file-2"},
    )

    assert payload.standard_input_uploads == {"ligand": "file-2"}


@pytest.mark.asyncio
async def test_create_task_projects_standard_uploads_to_builtin_inputs(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: True)

    owner = UserModel(
        email="standard-upload@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(owner)
    await db_session.flush()

    tool = ToolModel(
        owner_id=owner.id,
        name="Protein Preparation",
        slug="builtin-protein-preparation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersionModel(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "builtin",
            "builtin_slug": "builtin-protein-preparation",
            "artifacts": {
                "inputs": [
                    {"name": "protein", "type": "protein_structure@1", "required": True}
                ],
                "outputs": [],
            },
        },
        is_active=True,
        deprecated=False,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    tool.current_version = version

    protein_file = FileModel(
        owner_id=owner.id,
        filename="uploaded-protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=12,
        sha256=hashlib.sha256(b"ATOM upload\n").hexdigest(),
        storage_path="/tmp/uploaded-protein.pdb",
        source_type=FileSourceType.UPLOAD.value,
    )
    db_session.add(protein_file)
    await db_session.flush()

    scheduled: list[tuple[str, str]] = []
    direct_runner = SimpleNamespace(
        schedule_task=lambda *, task_id, tool_version_id: scheduled.append(
            (task_id, tool_version_id)
        )
    )

    task = await create_and_schedule_tool_task(
        db=db_session,
        current_user=owner,
        task_data=TaskCreate(
            tool_id=tool.id,
            standard_input_uploads={"protein": protein_file.id},
        ),
        direct_runner=direct_runner,
    )

    task_input = (
        await db_session.execute(
            select(TaskInputModel).where(TaskInputModel.task_id == task.id)
        )
    ).scalar_one()

    assert scheduled == [(str(task.id), str(version.id))]
    assert task.extra_data["standard_input_uploads"] == {"protein": protein_file.id}
    assert task_input.file_ids == [protein_file.id]
    assert task_input.params["builtin_inputs"] == {"protein_structure@1": protein_file.id}
