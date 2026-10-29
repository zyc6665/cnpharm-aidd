"""ArtifactVersion 来源字段与幂等写入测试（Task 3a）。

覆盖：
- ``artifact_versions`` 迁移后具备四个新列，``storage_tier`` 默认 ``'standard'``，
  以及 ``(artifact_id, sha256) WHERE status='available'`` 部分唯一索引存在；
- ``upsert_version`` 写入后 ``source_task_id`` / ``source_attempt_id`` /
  ``source_tool_version_id`` 落库，并回填 ``Artifact.source_task_id``；
- 同一 ``(task_id, sha256)`` 二次调用返回同一 version 且 ``created=False``；
- 取号冲突时走重试分支（SQLite 无行锁，这里用「首次返回过期版本号制造唯一约束
  冲突」测机制，不测真实并发时序，见注释）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models import (  # noqa: F401
    Artifact,
    ArtifactLineage,
    ArtifactVersion,
    ArtifactVersionFile,
    File,
    Organization,
    Project,
    Task,
    Tool,
    ToolVersion,
    User,
)
from app.models.tasks import TaskStatus
from app.models.tools import ToolStatus
from app.models.users import UserRole, UserStatus
from app.services import artifact_writer
from app.services.artifact_writer import ArtifactSource, upsert_version


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(db: AsyncSession) -> tuple[User, Project, Task]:
    user = User(
        email="artifact-source@example.com",
        password_hash="hashed",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    organization = Organization(name="Source Lab", slug="source-lab")
    db.add_all([user, organization])
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=user.id,
        name="Source project",
        status="active",
    )
    db.add(project)
    await db.flush()
    tool = Tool(
        owner_id=user.id,
        name="Source Tool",
        slug="source-tool",
        status=ToolStatus.PUBLISHED.value,
    )
    db.add(tool)
    await db.flush()
    tool_version = ToolVersion(tool_id=tool.id, version="1.0.0", config={"type": "builtin"})
    db.add(tool_version)
    await db.flush()
    tool.current_version_id = tool_version.id
    task = Task(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=tool_version.id,
        status=TaskStatus.SUCCESS.value,
        extra_data={"project_id": project.id, "execution_attempt_id": "attempt-7"},
    )
    db.add(task)
    await db.commit()
    return user, project, task


def _new_artifact(project: Project, user: User) -> Artifact:
    return Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        name="protein.pdb",
    )


@pytest.mark.asyncio
async def test_artifact_versions_has_source_columns_default_tier_and_partial_index(
    db_session: AsyncSession,
) -> None:
    def _read_schema(sync_session) -> tuple[dict[str, dict], dict[str, dict], str | None]:
        inspector = inspect(sync_session.get_bind())
        columns = {column["name"]: column for column in inspector.get_columns("artifact_versions")}
        indexes = {index["name"]: index for index in inspector.get_indexes("artifact_versions")}
        default = columns.get("storage_tier", {}).get("default")
        return columns, indexes, default

    columns, indexes, storage_tier_default = await db_session.run_sync(_read_schema)

    assert {"source_task_id", "source_attempt_id", "source_tool_version_id", "storage_tier"} <= set(
        columns
    )
    assert columns["source_task_id"]["nullable"] is True
    assert columns["source_attempt_id"]["nullable"] is True
    assert columns["source_tool_version_id"]["nullable"] is True
    assert columns["storage_tier"]["nullable"] is False
    assert "standard" in str(storage_tier_default)
    assert "uq_artifact_versions_artifact_sha256" in indexes
    assert bool(indexes["uq_artifact_versions_artifact_sha256"]["unique"]) is True

    # 真写一行，确认 storage_tier 由数据库/ORM 默认填充为 'standard'。
    user, project, _task = await _seed(db_session)
    artifact = _new_artifact(project, user)
    db_session.add(artifact)
    await db_session.flush()
    version, created = await upsert_version(
        db_session,
        artifact=artifact,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=3,
        sha256="a" * 64,
        storage_key="organizations/o/projects/p/artifacts/a/1/protein.pdb",
        created_by=user.id,
    )
    await db_session.commit()
    await db_session.refresh(version)
    assert created is True
    assert version.storage_tier == "standard"


@pytest.mark.asyncio
async def test_upsert_version_persists_source_fields(db_session: AsyncSession) -> None:
    user, project, task = await _seed(db_session)
    artifact = _new_artifact(project, user)
    db_session.add(artifact)
    await db_session.flush()

    version, created = await upsert_version(
        db_session,
        artifact=artifact,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=3,
        sha256="b" * 64,
        storage_key="k/b",
        created_by=user.id,
        source=ArtifactSource(
            task_id=str(task.id),
            attempt_id="attempt-7",
            tool_version_id=str(task.tool_version_id),
        ),
    )
    await db_session.commit()
    await db_session.refresh(version)
    await db_session.refresh(artifact)

    assert created is True
    assert version.source_task_id == str(task.id)
    assert version.source_attempt_id == "attempt-7"
    assert version.source_tool_version_id == str(task.tool_version_id)
    assert artifact.source_task_id == str(task.id)


@pytest.mark.asyncio
async def test_upsert_version_is_idempotent_for_same_task_and_sha(
    db_session: AsyncSession,
) -> None:
    user, project, task = await _seed(db_session)
    artifact = _new_artifact(project, user)
    db_session.add(artifact)
    await db_session.flush()
    source = ArtifactSource(task_id=str(task.id))

    first, first_created = await upsert_version(
        db_session,
        artifact=artifact,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=3,
        sha256="c" * 64,
        storage_key="k/c-first",
        created_by=user.id,
        source=source,
    )
    second, second_created = await upsert_version(
        db_session,
        artifact=artifact,
        filename="renamed.pdb",
        content_type="chemical/x-pdb",
        size_bytes=3,
        sha256="c" * 64,
        storage_key="k/c-second",
        created_by=user.id,
        source=source,
    )
    await db_session.commit()

    assert first_created is True
    assert second_created is False
    assert first.id == second.id
    total = await db_session.scalar(
        select(func.count(ArtifactVersion.id)).where(ArtifactVersion.artifact_id == artifact.id)
    )
    assert total == 1


@pytest.mark.asyncio
async def test_upsert_version_retries_when_version_number_collides(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, project, _task = await _seed(db_session)
    artifact = _new_artifact(project, user)
    db_session.add(artifact)
    await db_session.flush()
    # 先落一个占位版本（version=1），为后面制造取号冲突。
    await upsert_version(
        db_session,
        artifact=artifact,
        filename="first.pdb",
        content_type="chemical/x-pdb",
        size_bytes=1,
        sha256="d" * 64,
        storage_key="k/d",
        created_by=user.id,
    )
    await db_session.commit()

    real_max = artifact_writer._max_version_number
    calls = {"count": 0}

    async def flaky_max(db: AsyncSession, artifact_id: str) -> int:
        calls["count"] += 1
        if calls["count"] == 1:
            # 模拟「读到过期最大值」导致 version=1 与占位版本撞唯一约束。
            return 0
        return await real_max(db, artifact_id)

    monkeypatch.setattr(artifact_writer, "_max_version_number", flaky_max)

    version, created = await upsert_version(
        db_session,
        artifact=artifact,
        filename="second.pdb",
        content_type="chemical/x-pdb",
        size_bytes=1,
        sha256="e" * 64,
        storage_key="k/e",
        created_by=user.id,
    )
    await db_session.commit()

    assert created is True
    assert version.version == 2
    assert calls["count"] >= 2
