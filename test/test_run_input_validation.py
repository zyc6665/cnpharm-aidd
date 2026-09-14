"""Run input validation module tests."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

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

from app.common.exceptions import (  # noqa: E402
    NotFoundException,
    ValidationException,
)
from app.database.base import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    Artifact,
    ArtifactVersion,
    File,
    Organization,
    Project,
    User,
)
from app.models.artifacts import Artifact as ArtifactModel  # noqa: E402
from app.models.artifacts import (  # noqa: E402
    ArtifactVersion as ArtifactVersionModel,
)
from app.models.files import File as FileModel  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.users import User as UserModel  # noqa: E402
from app.models.users import UserRole, UserStatus  # noqa: E402
from app.services.run_input_validation import (  # noqa: E402
    append_existing_file_id,
    dedupe_ordered,
    input_bindings_requiring_validation,
    require_existing_file_id,
    validate_standard_input_bindings,
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
        email="run-input-validation@example.com",
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
    project_id: str | None = "project-1",
) -> FileModel:
    content = b"ATOM file\n"
    file_record = FileModel(
        owner_id=owner.id,
        project_id=project_id,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_path="/tmp/protein.pdb",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    db.add(file_record)
    await db.flush()
    return file_record


async def _create_artifact_version(
    db: AsyncSession,
    owner: UserModel,
    *,
    project_id: str,
) -> ArtifactVersionModel:
    artifact = ArtifactModel(
        project_id=project_id,
        created_by=owner.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        standard_type="protein_structure",
        standard_version=1,
        name="protein",
    )
    db.add(artifact)
    await db.flush()

    version = ArtifactVersionModel(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename="protein.manifest.json",
        content_type="application/json",
        size_bytes=2,
        sha256=hashlib.sha256(b"{}").hexdigest(),
        storage_key="artifacts/protein.manifest.json",
        validation_status="passed",
        validation_errors=[],
        manifest_json={},
        summary_json={},
        metrics_json={},
    )
    db.add(version)
    await db.flush()
    artifact.latest_version_id = version.id
    await db.flush()
    return version


def test_input_bindings_requiring_validation_filters_workflow_slots() -> None:
    result = input_bindings_requiring_validation(
        {"plain": "version-1", "prepared": "version-2"},
        {
            "plain": {"name": "plain", "type": "protein_structure@1"},
            "prepared": {
                "name": "prepared",
                "type": "protein_structure@1",
                "readiness_policy": "require_prepared",
            },
        },
        accepts_standard_bindings=False,
        surface="workflow_node",
    )

    assert result == {"prepared": "version-2"}
    assert input_bindings_requiring_validation(
        {"plain": "version-1"},
        {},
        accepts_standard_bindings=False,
        surface="tool_detail",
    ) == {"plain": "version-1"}


@pytest.mark.asyncio
async def test_validate_standard_input_bindings_checks_project_ownership(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    version = await _create_artifact_version(
        db_session,
        owner,
        project_id="project-2",
    )

    with pytest.raises(ValidationException) as exc_info:
        await validate_standard_input_bindings(
            db_session,
            project_id="project-1",
            input_bindings={"protein": version.id},
        )

    assert exc_info.value.detail == {
        "mismatched_artifact_version_ids": [version.id]
    }


@pytest.mark.asyncio
async def test_file_validation_checks_project_and_deduplicates(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    file_record = await _create_file(db_session, owner, project_id="project-1")
    file_ids: list[str] = []
    seen_file_ids: set[str] = set()

    await require_existing_file_id(
        db_session,
        file_id=file_record.id,
        project_id="project-1",
    )
    await append_existing_file_id(
        db_session,
        file_ids=file_ids,
        seen_file_ids=seen_file_ids,
        file_id=file_record.id,
        label="protein",
    )
    await append_existing_file_id(
        db_session,
        file_ids=file_ids,
        seen_file_ids=seen_file_ids,
        file_id=file_record.id,
        label="protein",
    )

    assert file_ids == [file_record.id]
    assert dedupe_ordered([file_record.id, "", file_record.id, "file-2"]) == [
        file_record.id,
        "file-2",
    ]

    with pytest.raises(NotFoundException):
        await append_existing_file_id(
            db_session,
            file_ids=[],
            seen_file_ids=set(),
            file_id="missing-file",
            label="missing",
        )
