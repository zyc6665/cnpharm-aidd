"""ArtifactVersion 来源字段与幂等写入测试（Task 3a）。

覆盖：
- ``artifact_versions`` 迁移后具备四个新列，``storage_tier`` 默认 ``'standard'``，
  且**不再**有 ``(artifact_id, sha256)`` 内容唯一索引（只追加留痕表）；
- ``upsert_version`` 写入后 ``source_task_id`` / ``source_attempt_id`` /
  ``source_tool_version_id`` 落库，并回填 ``Artifact.source_task_id``；
- 同一 ``(task_id, sha256)`` 二次调用返回同一 version 且 ``created=False``；
- 不同 task_id、同 sha256 各自得到独立 version 与各自来源，且两条 lineage 边都在；
- 上传路径（``source=None``）同 sha256 二次调用复用同一 version、``created=False``、
  不触发唯一约束报错；
- 取号冲突时走重试分支（SQLite 无行锁，这里用「首次返回过期版本号制造唯一约束
  冲突」测机制，不测真实并发时序，见注释）。
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, inspect, select, text
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
from app.services.artifact_lineage_graph import artifact_lineage_graph_data
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


async def _add_snapshot(db: AsyncSession, task: Task, entity_id: str) -> TaskInputSnapshot:
    snapshot = TaskInputSnapshot(
        task_id=task.id,
        entity_type="artifact_version",
        entity_id=entity_id,
        input_role="RECEPTOR",
        ordinal=0,
        sha256="0" * 64,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


@pytest.mark.asyncio
async def test_artifact_versions_has_source_columns_default_tier_and_no_content_unique_index(
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
    # 只追加留痕表：不再有 (artifact_id, sha256) 内容唯一索引。
    assert "uq_artifact_versions_artifact_sha256" not in indexes

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
    input_artifact = _new_artifact(project, user)
    db_session.add(input_artifact)
    await db_session.flush()
    input_version = await _add_input_version(db_session, input_artifact, user, "0" * 64, 1)
    await _add_snapshot(db_session, task, str(input_version.id))
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
    # 同任务重放不应重复写 lineage 边。
    edge_total = await db_session.scalar(
        select(func.count(ArtifactLineage.id)).where(
            ArtifactLineage.output_version_id == first.id
        )
    )
    assert edge_total == 1


@pytest.mark.asyncio
async def test_upsert_version_keeps_separate_versions_per_task_for_same_sha(
    db_session: AsyncSession,
) -> None:
    """两个不同任务产出同样字节：各自一个 version、来源正确、各自 lineage 边都在。"""
    user, project, task1 = await _seed(db_session)
    task2 = Task(
        user_id=user.id,
        tool_id=task1.tool_id,
        tool_version_id=task1.tool_version_id,
        status=TaskStatus.SUCCESS.value,
        extra_data={"project_id": project.id},
    )
    db_session.add(task2)
    await db_session.flush()

    input_artifact = _new_artifact(project, user)
    db_session.add(input_artifact)
    await db_session.flush()
    input1 = await _add_input_version(db_session, input_artifact, user, "1" * 64, 1)
    input2 = await _add_input_version(db_session, input_artifact, user, "2" * 64, 2)
    await _add_snapshot(db_session, task1, str(input1.id))
    await _add_snapshot(db_session, task2, str(input2.id))

    output_artifact = _new_artifact(project, user)
    db_session.add(output_artifact)
    await db_session.flush()
    common = dict(
        filename="same.pdb",
        content_type="chemical/x-pdb",
        size_bytes=9,
        sha256="f" * 64,
        created_by=user.id,
    )

    v1, c1 = await upsert_version(
        db_session,
        artifact=output_artifact,
        storage_key="k/task1",
        source=ArtifactSource(task_id=str(task1.id)),
        **common,
    )
    v2, c2 = await upsert_version(
        db_session,
        artifact=output_artifact,
        storage_key="k/task2",
        source=ArtifactSource(task_id=str(task2.id)),
        **common,
    )
    await db_session.commit()

    assert c1 is True
    assert c2 is True
    assert v1.id != v2.id
    assert v1.source_task_id == str(task1.id)
    assert v2.source_task_id == str(task2.id)
    # 同字节不同版本复用同一个存储 blob。
    assert v2.storage_key == v1.storage_key

    edges1 = (
        await db_session.scalars(
            select(ArtifactLineage).where(ArtifactLineage.output_version_id == v1.id)
        )
    ).all()
    edges2 = (
        await db_session.scalars(
            select(ArtifactLineage).where(ArtifactLineage.output_version_id == v2.id)
        )
    ).all()
    assert {edge.input_version_id for edge in edges1} == {input1.id}
    assert {edge.input_version_id for edge in edges2} == {input2.id}


@pytest.mark.asyncio
async def test_upsert_version_upload_path_dedups_same_sha_without_integrity_error(
    db_session: AsyncSession,
) -> None:
    """上传路径（source=None）同 sha 二次调用：复用同一 version，不抛 IntegrityError。"""
    user, project, _task = await _seed(db_session)
    artifact = _new_artifact(project, user)
    db_session.add(artifact)
    await db_session.flush()
    kwargs = dict(
        filename="upload.bin",
        content_type="application/octet-stream",
        size_bytes=3,
        sha256="9" * 64,
        storage_key="k/upload",
        created_by=user.id,
    )

    first, first_created = await upsert_version(db_session, artifact=artifact, **kwargs)
    second, second_created = await upsert_version(db_session, artifact=artifact, **kwargs)
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


@pytest.mark.asyncio
async def test_attach_version_files_skips_roles_that_already_exist(
    db_session: AsyncSession,
) -> None:
    from app.models.artifacts import ArtifactVersionFile
    from app.models.files import File as FileModel
    from app.services.artifact_writer import attach_version_files

    user, project, _task = await _seed(db_session)
    artifact = _new_artifact(project, user)
    db_session.add(artifact)
    await db_session.flush()
    version = await _add_input_version(db_session, artifact, user, "a" * 64, 1)

    primary = FileModel(
        owner_id=user.id,
        project_id=project.id,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=3,
        sha256="a" * 64,
        storage_backend="local",
        storage_path="storage/aa/protein.pdb",
        source_type="upload",
    )
    metadata = FileModel(
        owner_id=user.id,
        project_id=project.id,
        filename="protein.metadata_json.json",
        content_type="application/json",
        size_bytes=2,
        sha256="b" * 64,
        storage_backend="local",
        storage_path="storage/bb/meta.json",
        source_type="upload",
    )
    db_session.add_all([primary, metadata])
    await db_session.flush()

    files = [
        ("structure_file", primary.id, True),
        ("metadata_json", metadata.id, False),
    ]
    written = await attach_version_files(db_session, version=version, files=files)
    assert written == ["structure_file", "metadata_json"]

    # An idempotent replay re-derives the same roles: nothing new is written and the
    # unique constraint (artifact_version_id, role) is never violated.
    again = await attach_version_files(db_session, version=version, files=files)
    assert again == []
    total = (
        await db_session.execute(
            select(func.count())
            .select_from(ArtifactVersionFile)
            .where(ArtifactVersionFile.artifact_version_id == version.id)
        )
    ).scalar_one()
    assert total == 2


# ---------------------------------------------------------------------------
# 重试产生的新版本：同任务、不同尝试（attempt）→ 不同 version、attempt_id 不同
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_produces_new_version_with_different_attempt_id(
    db_session: AsyncSession,
) -> None:
    user, project, task = await _seed(db_session)
    artifact = _new_artifact(project, user)
    db_session.add(artifact)
    await db_session.flush()
    common = dict(
        artifact=artifact,
        filename="out.pdb",
        content_type="chemical/x-pdb",
        size_bytes=3,
        created_by=user.id,
    )

    v1, c1 = await upsert_version(
        db_session,
        storage_key="k/attempt-1",
        sha256="1" * 64,
        source=ArtifactSource(task_id=str(task.id), attempt_id="attempt-1"),
        **common,
    )
    # 同任务重试：新尝试产出新内容 → 独立版本，attempt_id 不同。
    v2, c2 = await upsert_version(
        db_session,
        storage_key="k/attempt-2",
        sha256="2" * 64,
        source=ArtifactSource(task_id=str(task.id), attempt_id="attempt-2"),
        **common,
    )
    await db_session.commit()

    assert c1 is True and c2 is True
    assert v1.id != v2.id
    assert v1.source_task_id == str(task.id) == v2.source_task_id
    assert v1.source_attempt_id == "attempt-1"
    assert v2.source_attempt_id == "attempt-2"
    assert v1.source_attempt_id != v2.source_attempt_id


# ---------------------------------------------------------------------------
# 回填迁移：把 artifact 级 source_task_id 复制到历史 NULL 版本；只回填 task，不回填 attempt
# ---------------------------------------------------------------------------


def _load_backfill_sql() -> str:
    path = (
        BACKEND_ROOT
        / "alembic/versions/20261104_01_backfill_artifact_version_source.py"
    )
    spec = importlib.util.spec_from_file_location("backfill_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BACKFILL_SQL


@pytest.mark.asyncio
async def test_backfill_migration_copies_artifact_source_to_historical_versions(
    db_session: AsyncSession,
) -> None:
    user, project, task = await _seed(db_session)
    # artifact A：有 artifact 级来源；两个历史版本 source 为 NULL → 应被回填。
    artifact_a = _new_artifact(project, user)
    artifact_a.source_task_id = str(task.id)
    db_session.add(artifact_a)
    await db_session.flush()
    va1 = await _add_input_version(db_session, artifact_a, user, "a1" * 32, 1)
    va2 = await _add_input_version(db_session, artifact_a, user, "a2" * 32, 2)
    # artifact B：artifact 级来源也为 NULL；其版本应保持 NULL（不能凭空造来源）。
    artifact_b = _new_artifact(project, user)
    db_session.add(artifact_b)
    await db_session.flush()
    vb = await _add_input_version(db_session, artifact_b, user, "b1" * 32, 1)
    await db_session.commit()

    async def _null_count() -> int:
        return await db_session.scalar(
            select(func.count())
            .select_from(ArtifactVersion)
            .where(ArtifactVersion.source_task_id.is_(None))
        )

    assert await _null_count() == 3

    backfill_sql = _load_backfill_sql()
    await db_session.execute(text(backfill_sql))
    await db_session.commit()
    for version in (va1, va2, vb):
        await db_session.refresh(version)

    # 历史版本退化到 artifact 级来源（best-effort）。
    assert va1.source_task_id == str(task.id)
    assert va2.source_task_id == str(task.id)
    # artifact 无来源的行保持 NULL。
    assert vb.source_task_id is None
    # 绝不回填 attempt（历史没有该信息，假值比 NULL 更糟）。
    assert va1.source_attempt_id is None
    assert va2.source_attempt_id is None
    assert vb.source_attempt_id is None
    assert await _null_count() == 1

    # 幂等：再跑一次不改变任何行。
    await db_session.execute(text(backfill_sql))
    await db_session.commit()
    assert await _null_count() == 1


# ---------------------------------------------------------------------------
# produced_by 读取侧：优先版本级 source_task_id，缺失回退 artifact 级
# ---------------------------------------------------------------------------


def _ns_version(
    version_id: str,
    *,
    source_task_id: str | None = None,
    source_attempt_id: str | None = None,
    number: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=version_id,
        version=number,
        filename=f"{version_id}.pdb",
        content_type="chemical/x-pdb",
        size_bytes=1,
        sha256="a" * 64,
        status="available",
        validation_status="passed",
        created_at=None,
        source_task_id=source_task_id,
        source_attempt_id=source_attempt_id,
    )


def _ns_artifact(
    artifact_id: str,
    *,
    source_task_id: str | None,
    versions: list[SimpleNamespace],
) -> SimpleNamespace:
    return SimpleNamespace(
        id=artifact_id,
        project_id="project-1",
        name=f"{artifact_id}.pdb",
        artifact_type="protein_structure",
        semantic_type="protein_structure@1",
        standard_type="protein_structure",
        standard_version=1,
        source_task_id=source_task_id,
        latest_version_id=versions[-1].id,
        created_at=None,
        updated_at=None,
        versions=versions,
    )


def _produced_by_edge_pairs(graph: dict) -> set[tuple[str, str]]:
    return {
        (edge["source"], edge["target"])
        for edge in graph["edges"]
        if edge["kind"] == "produced_by"
    }


def test_produced_by_prefers_version_level_over_artifact_level() -> None:
    # 故意构造两者不一致：artifact 级=task-artifact，版本级=task-version。
    # 必须取版本级——版本级有值时绝不能被 artifact 级覆盖。
    version = _ns_version(
        "v1", source_task_id="task-version", source_attempt_id="att-1"
    )
    artifact = _ns_artifact("a1", source_task_id="task-artifact", versions=[version])

    graph = artifact_lineage_graph_data(
        project_id="project-1",
        artifacts=[artifact],
        lineages=[],
        tasks_by_id={},
    )

    assert _produced_by_edge_pairs(graph) == {("task:task-version", "version:v1")}
    node = {n["id"]: n for n in graph["nodes"]}["version:v1"]
    assert node["source_task_id"] == "task-version"
    assert node["source_attempt_id"] == "att-1"


def test_produced_by_falls_back_to_artifact_level_when_version_source_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="app.services.artifact_lineage_graph")
    version = _ns_version("v2")  # 版本级来源为 NULL（历史/未回填）
    artifact = _ns_artifact("a2", source_task_id="task-artifact", versions=[version])

    graph = artifact_lineage_graph_data(
        project_id="project-1",
        artifacts=[artifact],
        lineages=[],
        tasks_by_id={},
    )

    assert _produced_by_edge_pairs(graph) == {("task:task-artifact", "version:v2")}
    # 回退有可观测性：应打出一条 debug 日志（带 artifact_id / version_id）。
    assert any(
        "falls back to artifact-level" in record.getMessage()
        and "a2" in record.getMessage()
        and "v2" in record.getMessage()
        for record in caplog.records
    )


def test_produced_by_omits_edge_when_both_sources_missing() -> None:
    version = _ns_version("v3")
    artifact = _ns_artifact("a3", source_task_id=None, versions=[version])

    graph = artifact_lineage_graph_data(
        project_id="project-1",
        artifacts=[artifact],
        lineages=[],
        tasks_by_id={},
    )

    assert _produced_by_edge_pairs(graph) == set()

