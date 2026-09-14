"""Run legacy input projection module tests."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.models import File, Organization, Project, User  # noqa: E402,F401
from app.models.files import File as FileModel  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.users import User as UserModel  # noqa: E402
from app.models.users import UserRole, UserStatus  # noqa: E402
from app.services.run_legacy_projection import (  # noqa: E402
    existing_input_file_fields,
    project_file_to_legacy_params,
)


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
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _create_owner(db: AsyncSession) -> UserModel:
    owner = UserModel(
        email="run-legacy-projection@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(owner)
    await db.flush()
    return owner


async def _create_file(
    db: AsyncSession,
    owner: UserModel,
    *,
    filename: str,
) -> FileModel:
    content = f"ATOM {filename}\n".encode()
    file_record = FileModel(
        owner_id=owner.id,
        project_id="project-1",
        filename=filename,
        content_type="chemical/x-pdb",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_path=f"/tmp/{filename}",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    db.add(file_record)
    await db.flush()
    return file_record


@pytest.mark.asyncio
async def test_project_file_to_legacy_params_projects_builtin_inputs(
    db_session: AsyncSession,
) -> None:
    params = {"builtin_inputs": {"existing": "file-0"}}

    await project_file_to_legacy_params(
        db_session,
        tool_version=SimpleNamespace(config={"type": "builtin"}),
        input_slot={"name": "protein", "type": "protein_structure@1"},
        file_id="file-1",
        params=params,
    )

    assert params["builtin_inputs"] == {
        "existing": "file-0",
        "protein_structure@1": "file-1",
    }


@pytest.mark.asyncio
async def test_project_file_to_legacy_params_projects_ssh_file_field(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    file_record = await _create_file(
        db_session,
        owner,
        filename="prepared protein.pdb",
    )
    params = {"input_files": {"protein_a_pdb": "input/existing.pdb"}}
    used_fields = existing_input_file_fields(params)

    await project_file_to_legacy_params(
        db_session,
        tool_version=SimpleNamespace(
            config={
                "type": "ssh_job",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "protein_a_pdb": {"type": "string", "format": "file"},
                        "protein_b_pdb": {"type": "string", "format": "file"},
                    },
                },
            }
        ),
        input_slot={"name": "protein_b", "type": "protein_structure@1"},
        file_id=file_record.id,
        params=params,
        used_fields=used_fields,
    )

    assert params["input_files"] == {
        "protein_a_pdb": "input/existing.pdb",
        "protein_b_pdb": "input/prepared protein.pdb",
    }
    assert used_fields == {"protein_a_pdb", "protein_b_pdb"}
