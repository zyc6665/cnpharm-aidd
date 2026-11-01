"""产物查询必须按**版本级**来源（``ArtifactVersion.source_task_id``）。

回归背景
--------
``Artifact`` 是跨任务共享的逻辑实体：同一项目内同一 ``artifact_type`` + 同一标识
只保留一条记录，后来的任务在它下面追加版本。因此 ``Artifact.source_task_id``
记的是**首个创建者**——按它过滤，非首建任务的结果页、导出报告、追溯包都会是
「一条产物都没有」，而这些产物其实都正常入库了。

本文件守住三件事：
1. 任务 B 复用任务 A 创建的 ``Artifact`` 追加 ``version=2`` 后，
   ``artifact_outputs_for_task(B)`` 只返回 B 的那条版本；
2. 同一任务产出的多个版本都要返回（导出报告与结果页共用同一份数据）；
3. 结果详情 API 的 ``_artifact_outputs`` 跟着走版本级来源，不再漏。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models import (  # noqa: F401
    Artifact,
    ArtifactVersion,
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
from app.services.artifact_outputs import artifact_outputs_for_task
from app.services.artifact_writer import ArtifactSource, upsert_version


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(db: AsyncSession) -> tuple[User, Project, ToolVersion, Task, Task]:
    """建一个项目 + 一条共享 Artifact + 两个任务（A 首建、B 追加）。"""

    user = User(
        email="artifacts@example.com",
        password_hash="x",
        display_name="owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()

    org = Organization(name="Org", slug="org")
    db.add(org)
    await db.flush()

    project = Project(
        organization_id=org.id, created_by=user.id, name="P", status="active"
    )
    db.add(project)
    await db.flush()

    tool = Tool(
        owner_id=user.id,
        name="molp-pc",
        slug="molp-pc-artifacts-test",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db.add(tool)
    await db.flush()
    tool_version = ToolVersion(
        tool_id=tool.id, version="1.0.0", config={"type": "k8s_job"}, is_active=True
    )
    db.add(tool_version)
    await db.flush()

    def _task(name: str) -> Task:
        return Task(
            user_id=user.id,
            tool_id=tool.id,
            tool_version_id=tool_version.id,
            name=name,
            status=TaskStatus.SUCCESS.value,
            priority="normal",
            progress=100.0,
        )

    task_a, task_b = _task("first"), _task("second")
    db.add_all([task_a, task_b])
    await db.flush()
    return user, project, tool_version, task_a, task_b


async def _shared_artifact(db: AsyncSession, *, user: User, project: Project) -> Artifact:
    artifact = Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type="molecule_table",
        semantic_type="molecule_table",
        name="properties",
    )
    db.add(artifact)
    await db.flush()
    return artifact


@pytest.mark.asyncio
async def test_second_task_sees_its_own_version_only(db_session: AsyncSession) -> None:
    user, project, _tv, task_a, task_b = await _seed(db_session)
    artifact = await _shared_artifact(db_session, user=user, project=project)

    first, _ = await upsert_version(
        db_session,
        artifact=artifact,
        filename="properties.csv",
        content_type="text/csv",
        size_bytes=10,
        sha256="1" * 64,
        storage_key="k/1",
        created_by=user.id,
        source=ArtifactSource(task_id=str(task_a.id)),
    )
    second, _ = await upsert_version(
        db_session,
        artifact=artifact,
        filename="properties.csv",
        content_type="text/csv",
        size_bytes=20,
        sha256="2" * 64,
        storage_key="k/2",
        created_by=user.id,
        source=ArtifactSource(task_id=str(task_b.id)),
    )
    await db_session.commit()

    outputs_a = await artifact_outputs_for_task(db_session, task_id=str(task_a.id))
    outputs_b = await artifact_outputs_for_task(db_session, task_id=str(task_b.id))

    # 关键断言：逻辑产物是同一条，但两个任务各自只看到自己产出的版本。
    assert {o.artifact_id for o in outputs_a} == {str(artifact.id)}
    assert {o.artifact_id for o in outputs_b} == {str(artifact.id)}
    assert [o.version_id for o in outputs_a] == [str(first.id)]
    assert [o.version_id for o in outputs_b] == [str(second.id)]
    assert outputs_b[0].version == 2
    assert outputs_b[0].size_bytes == 20


@pytest.mark.asyncio
async def test_all_versions_of_same_task_are_returned(db_session: AsyncSession) -> None:
    user, project, _tv, task_a, _task_b = await _seed(db_session)
    artifact = await _shared_artifact(db_session, user=user, project=project)

    made: list[str] = []
    for index, digest in enumerate(("a" * 64, "b" * 64), start=1):
        version, _ = await upsert_version(
            db_session,
            artifact=artifact,
            filename=f"properties-{index}.csv",
            content_type="text/csv",
            size_bytes=index,
            sha256=digest,
            storage_key=f"k/{index}",
            created_by=user.id,
            source=ArtifactSource(task_id=str(task_a.id)),
        )
        made.append(str(version.id))
    await db_session.commit()

    outputs = await artifact_outputs_for_task(db_session, task_id=str(task_a.id))
    assert [o.version_id for o in outputs] == made
    assert [o.version for o in outputs] == [1, 2]


@pytest.mark.asyncio
async def test_results_api_lists_artifacts_for_non_first_task(
    db_session: AsyncSession,
) -> None:
    """结果详情 API 走版本级来源——非首建任务也必须有产物。"""

    from app.api.v1.results import _artifact_outputs

    user, project, _tv, task_a, task_b = await _seed(db_session)
    artifact = await _shared_artifact(db_session, user=user, project=project)
    await upsert_version(
        db_session,
        artifact=artifact,
        filename="properties.csv",
        content_type="text/csv",
        size_bytes=10,
        sha256="3" * 64,
        storage_key="k/3",
        created_by=user.id,
        source=ArtifactSource(task_id=str(task_a.id)),
    )
    await upsert_version(
        db_session,
        artifact=artifact,
        filename="properties.csv",
        content_type="text/csv",
        size_bytes=30,
        sha256="4" * 64,
        storage_key="k/4",
        created_by=user.id,
        source=ArtifactSource(task_id=str(task_b.id)),
    )
    await db_session.commit()

    entries_a = await _artifact_outputs(db_session, str(task_a.id))
    entries_b = await _artifact_outputs(db_session, str(task_b.id))

    assert [entry["version"] for entry in entries_a] == [1]
    assert [entry["version"] for entry in entries_b] == [2]
    assert entries_b[0]["size_bytes"] == 30
    assert entries_b[0]["artifact_type"] == "molecule_table"
