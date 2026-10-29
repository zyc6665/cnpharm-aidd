"""TaskInputSnapshot → ArtifactLineage 回溯写边测试（Task 3a）。

覆盖：``upsert_version`` 落库后按 ``TaskInputSnapshot`` 的
``entity_type='artifact_version'`` 写出 ``derived_from`` 边；重复写入不产生重复边；
不会写出自环（输入版本等于输出本身时跳过）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
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
from app.models.traceability import TaskInputSnapshot
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
        email="lineage@example.com",
        password_hash="hashed",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    organization = Organization(name="Lineage Lab", slug="lineage-lab")
    db.add_all([user, organization])
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=user.id,
        name="Lineage project",
        status="active",
    )
    db.add(project)
    await db.flush()
    tool = Tool(
        owner_id=user.id,
        name="Lineage Tool",
        slug="lineage-tool",
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
        extra_data={"project_id": project.id},
    )
    db.add(task)
    await db.commit()
    return user, project, task


def _new_artifact(project: Project, user: User, name: str) -> Artifact:
    return Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        name=name,
    )


async def _add_input_version(
    db: AsyncSession, artifact: Artifact, user: User, sha: str, number: int
) -> ArtifactVersion:
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=user.id,
        version=number,
        filename="input.pdb",
        content_type="chemical/x-pdb",
        size_bytes=3,
        sha256=sha,
        storage_key=f"inputs/{sha}",
        status="available",
        validation_status="passed",
        manifest_json={},
        summary_json={},
        metrics_json={},
    )
    db.add(version)
    await db.flush()
    return version


async def _add_snapshot(
    db: AsyncSession, task: Task, entity_id: str, role: str, ordinal: int
) -> TaskInputSnapshot:
    snapshot = TaskInputSnapshot(
        task_id=task.id,
        entity_type="artifact_version",
        entity_id=entity_id,
        input_role=role,
        ordinal=ordinal,
        sha256="0" * 64,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


@pytest.mark.asyncio
async def test_upsert_version_writes_derived_from_edges(db_session: AsyncSession) -> None:
    user, project, task = await _seed(db_session)
    input_artifact = _new_artifact(project, user, "inputs.pdb")
    db_session.add(input_artifact)
    await db_session.flush()
    receptor = await _add_input_version(db_session, input_artifact, user, "1" * 64, 1)
    ligand = await _add_input_version(db_session, input_artifact, user, "2" * 64, 2)
    await _add_snapshot(db_session, task, str(receptor.id), "RECEPTOR", 0)
    await _add_snapshot(db_session, task, str(ligand.id), "LIGAND", 1)

    output_artifact = _new_artifact(project, user, "complex.pdb")
    db_session.add(output_artifact)
    await db_session.flush()
    version, created = await upsert_version(
        db_session,
        artifact=output_artifact,
        filename="complex.pdb",
        content_type="chemical/x-pdb",
        size_bytes=9,
        sha256="9" * 64,
        storage_key="k/complex",
        created_by=user.id,
        source=ArtifactSource(task_id=str(task.id)),
    )
    await db_session.commit()

    assert created is True
    edges = (
        await db_session.scalars(
            select(ArtifactLineage).where(ArtifactLineage.output_version_id == version.id)
        )
    ).all()
    assert {edge.input_version_id for edge in edges} == {receptor.id, ligand.id}
    assert all(edge.relation_type == "derived_from" for edge in edges)


@pytest.mark.asyncio
async def test_repeated_lineage_write_does_not_duplicate_edges(db_session: AsyncSession) -> None:
    user, project, task = await _seed(db_session)
    input_artifact = _new_artifact(project, user, "inputs.pdb")
    db_session.add(input_artifact)
    await db_session.flush()
    receptor = await _add_input_version(db_session, input_artifact, user, "3" * 64, 1)
    await _add_snapshot(db_session, task, str(receptor.id), "RECEPTOR", 0)

    output_artifact = _new_artifact(project, user, "complex.pdb")
    db_session.add(output_artifact)
    await db_session.flush()
    version, _created = await upsert_version(
        db_session,
        artifact=output_artifact,
        filename="complex.pdb",
        content_type="chemical/x-pdb",
        size_bytes=9,
        sha256="8" * 64,
        storage_key="k/complex-2",
        created_by=user.id,
        source=ArtifactSource(task_id=str(task.id)),
    )
    await db_session.commit()

    # 再显式重写一次，ON CONFLICT DO NOTHING 应保证不产生重复边。
    await artifact_writer._write_source_lineage(
        db_session,
        artifact=output_artifact,
        version=version,
        source=ArtifactSource(task_id=str(task.id)),
        created_by=user.id,
    )
    await db_session.commit()

    total = await db_session.scalar(
        select(func.count(ArtifactLineage.id)).where(ArtifactLineage.output_version_id == version.id)
    )
    assert total == 1


@pytest.mark.asyncio
async def test_self_loop_edge_is_not_written(db_session: AsyncSession) -> None:
    user, project, task = await _seed(db_session)
    output_artifact = _new_artifact(project, user, "complex.pdb")
    db_session.add(output_artifact)
    await db_session.flush()
    version, _created = await upsert_version(
        db_session,
        artifact=output_artifact,
        filename="complex.pdb",
        content_type="chemical/x-pdb",
        size_bytes=9,
        sha256="7" * 64,
        storage_key="k/complex-3",
        created_by=user.id,
    )
    # 让快照把输出自身当作输入，制造自环场景。
    await _add_snapshot(db_session, task, str(version.id), "RECEPTOR", 0)
    await db_session.commit()

    await artifact_writer._write_source_lineage(
        db_session,
        artifact=output_artifact,
        version=version,
        source=ArtifactSource(task_id=str(task.id)),
        created_by=user.id,
    )
    await db_session.commit()

    self_edges = await db_session.scalar(
        select(func.count(ArtifactLineage.id)).where(
            ArtifactLineage.output_version_id == version.id,
            ArtifactLineage.input_version_id == version.id,
        )
    )
    assert self_edges == 0
