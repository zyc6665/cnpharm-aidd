"""Artifact GC 与项目删除对象清理测试（计划 §5.6）。"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.common.time import utcnow
from app.database.base import Base
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.files import File
from app.models.projects import Organization, Project
from app.models.tasks import TaskInput, TaskOutput
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def gc_db(tmp_path) -> AsyncSession:
    # 用文件型 SQLite 而不是 StaticPool 内存库：多个测试各自的事件循环下，
    # 单连接内存库偶尔会出现会话/连接跨 loop 的 DetachedInstanceError。
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'gc.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_project(db: AsyncSession) -> tuple[User, Project]:
    user = User(
        email="gc@example.com",
        password_hash="hashed",
        display_name="gc",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    organization = Organization(name="GC Lab", slug="gc-lab")
    db.add_all([user, organization])
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=user.id,
        name="GC Project",
        status="active",
    )
    db.add(project)
    await db.flush()
    return user, project


def _file(
    *,
    project_id: str,
    owner_id: str,
    name: str,
    created_at,
    size: int = 3,
    source_type: str = "tool_output",
) -> File:
    return File(
        project_id=project_id,
        owner_id=owner_id,
        filename=name,
        content_type="application/octet-stream",
        size_bytes=size,
        sha256="f" * 64,
        storage_backend="local",
        storage_path=f"storage/{name}",
        source_type=source_type,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_collect_orphan_files_only_removes_expired_unreferenced_files(
    gc_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services import artifact_gc

    user, project = await _seed_project(gc_db)
    now = utcnow()
    old = now - timedelta(days=40)

    orphan = _file(project_id=project.id, owner_id=user.id, name="orphan.bin", created_at=old)
    failing = _file(project_id=project.id, owner_id=user.id, name="failing.bin", created_at=old)
    referenced = _file(project_id=project.id, owner_id=user.id, name="kept.bin", created_at=old)
    recent = _file(project_id=project.id, owner_id=user.id, name="recent.bin", created_at=now)
    gc_db.add_all([orphan, failing, referenced, recent])
    await gc_db.flush()

    artifact = Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        name="kept.bin",
    )
    gc_db.add(artifact)
    await gc_db.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=user.id,
        version=1,
        filename="kept.bin",
        size_bytes=3,
        sha256="f" * 64,
        storage_key="storage/kept.bin",
        status="available",
    )
    gc_db.add(version)
    await gc_db.flush()
    gc_db.add(
        ArtifactVersionFile(
            artifact_version_id=version.id,
            role="primary",
            file_id=referenced.id,
            is_primary=True,
        )
    )
    await gc_db.commit()

    deleted_paths: list[str] = []

    async def fake_delete(record, storage_backend=None):
        if record.filename == "failing.bin":
            raise RuntimeError("object storage timeout")
        deleted_paths.append(record.storage_path)

    monkeypatch.setattr(artifact_gc, "delete_stored_content", fake_delete)

    removed = await artifact_gc.collect_orphan_files(gc_db, retention_days=30, now=now)

    assert removed == 1
    assert deleted_paths == ["storage/orphan.bin"]
    remaining = set(
        (await gc_db.execute(select(File.filename))).scalars().all()
    )
    # 失败的仍在（下一轮重试），被引用与未到期的绝不能删。
    assert remaining == {"failing.bin", "kept.bin", "recent.bin"}


@pytest.mark.asyncio
async def test_collect_keeps_expired_user_upload_even_if_unreferenced(
    gc_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """普通用户上传（source_type=upload）绝不能被产物 GC 回收。

    ``POST /files/upload`` 的 File 通常只被 ``TaskInput.file_ids`` 引用，
    不会出现在 ``artifact_version_files``；若按「无版本引用 + 超期」删，
    会直接删掉用户上传的输入文件。
    """
    from app.services import artifact_gc

    user, project = await _seed_project(gc_db)
    old = utcnow() - timedelta(days=40)
    upload = _file(
        project_id=project.id,
        owner_id=user.id,
        name="user-upload.bin",
        created_at=old,
        source_type="upload",
    )
    gc_db.add(upload)
    await gc_db.commit()

    deleted: list[str] = []

    async def fake_delete(record, storage_backend=None):
        deleted.append(record.storage_path)

    monkeypatch.setattr(artifact_gc, "delete_stored_content", fake_delete)

    removed = await artifact_gc.collect_orphan_files(gc_db, retention_days=30)

    assert removed == 0
    assert deleted == []
    assert await gc_db.scalar(select(File).where(File.id == upload.id)) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "task_input"),
    [(TaskInput, True), (TaskOutput, False)],
    ids=["task_input", "task_output"],
)
async def test_collect_keeps_tool_output_referenced_by_task(
    gc_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    model,
    task_input: bool,
):
    """``TaskInput/TaskOutput.file_ids`` 是 JSON 数组、无外键，GC 必须逐条兜底。"""
    from app.services import artifact_gc

    user, project = await _seed_project(gc_db)
    old = utcnow() - timedelta(days=40)
    output = _file(
        project_id=project.id,
        owner_id=user.id,
        name="task-referenced.bin",
        created_at=old,
        source_type="tool_output",
    )
    gc_db.add(output)
    await gc_db.flush()

    task_id = str(uuid4())
    if task_input:
        gc_db.add(TaskInput(task_id=task_id, params={}, file_ids=[output.id]))
    else:
        gc_db.add(TaskOutput(task_id=task_id, file_ids=[output.id]))
    await gc_db.commit()

    deleted: list[str] = []

    async def fake_delete(record, storage_backend=None):
        deleted.append(record.storage_path)

    monkeypatch.setattr(artifact_gc, "delete_stored_content", fake_delete)

    removed = await artifact_gc.collect_orphan_files(gc_db, retention_days=30)

    assert removed == 0
    assert deleted == []
    assert await gc_db.scalar(select(File).where(File.id == output.id)) is not None


@pytest.mark.asyncio
async def test_project_delete_removes_artifact_objects_before_rows(
    gc_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.api.v1 import projects as projects_api

    user, project = await _seed_project(gc_db)
    artifact = Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        name="target.pdb",
    )
    gc_db.add(artifact)
    await gc_db.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=user.id,
        version=1,
        filename="target.pdb",
        size_bytes=3,
        sha256="a" * 64,
        storage_key="artifacts/target.pdb",
        status="available",
    )
    gc_db.add(version)
    await gc_db.commit()

    deleted_keys: list[str] = []

    class FakeStorage:
        async def delete(self, path: str) -> bool:
            deleted_keys.append(path)
            return True

    monkeypatch.setattr(projects_api, "get_storage_backend", lambda: FakeStorage())

    await projects_api._delete_project_related_rows(gc_db, project_id=project.id)
    await gc_db.commit()

    assert deleted_keys == ["artifacts/target.pdb"]
    assert await gc_db.scalar(select(Artifact).where(Artifact.id == artifact.id)) is None
    assert await gc_db.scalar(select(ArtifactVersion).where(ArtifactVersion.id == version.id)) is None


@pytest.mark.asyncio
async def test_project_delete_removes_artifact_version_files_before_versions(
    gc_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """回归 A1：ArtifactVersionFile 外键无 ondelete，删除顺序必须先子后父。"""
    from app.api.v1 import projects as projects_api

    user, project = await _seed_project(gc_db)
    artifact = Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        name="target.pdb",
    )
    gc_db.add(artifact)
    await gc_db.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=user.id,
        version=1,
        filename="target.pdb",
        size_bytes=3,
        sha256="b" * 64,
        storage_key="artifacts/target.pdb",
        status="available",
    )
    file_row = File(
        project_id=None,
        owner_id=user.id,
        filename="target.pdb",
        content_type="application/octet-stream",
        size_bytes=3,
        sha256="c" * 64,
        storage_backend="local",
        storage_path="storage/target.pdb",
        source_type="tool_output",
    )
    gc_db.add_all([version, file_row])
    await gc_db.flush()
    version_file = ArtifactVersionFile(
        artifact_version_id=version.id,
        role="primary",
        file_id=file_row.id,
    )
    gc_db.add(version_file)
    await gc_db.commit()

    class FakeStorage:
        async def delete(self, path: str) -> bool:
            return True

    monkeypatch.setattr(projects_api, "get_storage_backend", lambda: FakeStorage())
    # 避免真正触碰本地磁盘；本用例只验证行清理顺序。
    async def fake_delete(record, storage_backend=None):
        return None

    monkeypatch.setattr(projects_api, "delete_stored_content", fake_delete)

    await projects_api._delete_project_related_rows(gc_db, project_id=project.id)
    await gc_db.commit()

    assert (
        await gc_db.scalar(
            select(ArtifactVersionFile).where(
                ArtifactVersionFile.artifact_version_id == version.id
            )
        )
        is None
    )
    assert await gc_db.scalar(select(ArtifactVersion).where(ArtifactVersion.id == version.id)) is None


@pytest.mark.asyncio
async def test_project_delete_removes_project_file_objects_and_rows(
    gc_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """回归 A2：项目内非 tool_output 的 File 必须删对象并删行，而不是置 NULL。"""
    from app.api.v1 import projects as projects_api

    user, project = await _seed_project(gc_db)
    project_file = File(
        project_id=project.id,
        owner_id=user.id,
        filename="input.csv",
        content_type="text/csv",
        size_bytes=3,
        sha256="d" * 64,
        storage_backend="local",
        storage_path="storage/input.csv",
        source_type="USER_INPUT",
    )
    other_file = File(
        project_id=None,
        owner_id=user.id,
        filename="keep.csv",
        content_type="text/csv",
        size_bytes=3,
        sha256="e" * 64,
        storage_backend="local",
        storage_path="storage/keep.csv",
        source_type="USER_INPUT",
    )
    gc_db.add_all([project_file, other_file])
    await gc_db.commit()

    deleted_ids: list[str] = []

    async def fake_delete(record, storage_backend=None):
        deleted_ids.append(record.id)

    monkeypatch.setattr(projects_api, "delete_stored_content", fake_delete)

    await projects_api._delete_project_related_rows(gc_db, project_id=project.id)
    await gc_db.commit()

    assert deleted_ids == [project_file.id]
    assert await gc_db.scalar(select(File).where(File.id == project_file.id)) is None
    # 其他项目/无项目文件不受影响
    assert await gc_db.scalar(select(File).where(File.id == other_file.id)) is not None


@pytest.mark.asyncio
async def test_project_delete_skips_file_still_referenced_by_other_project_artifact(
    gc_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """回归 A2：同一 sha256 去重会让 File 行被多个项目共用，删除本项目时
    不能删掉仍被其他项目 ArtifactVersionFile 引用的 File 行（PG 上会 FK 500）。"""
    from app.api.v1 import projects as projects_api

    user, project = await _seed_project(gc_db)
    other_project = Project(
        organization_id=project.organization_id,
        created_by=user.id,
        name="Other GC Project",
        status="active",
    )
    gc_db.add(other_project)
    await gc_db.flush()

    shared_file = File(
        project_id=project.id,
        owner_id=user.id,
        filename="shared.csv",
        content_type="text/csv",
        size_bytes=3,
        sha256="1" * 64,
        storage_backend="local",
        storage_path="storage/shared.csv",
        source_type="USER_INPUT",
    )
    unreferenced_file = File(
        project_id=project.id,
        owner_id=user.id,
        filename="only-here.csv",
        content_type="text/csv",
        size_bytes=3,
        sha256="2" * 64,
        storage_backend="local",
        storage_path="storage/only-here.csv",
        source_type="USER_INPUT",
    )
    gc_db.add_all([shared_file, unreferenced_file])
    await gc_db.flush()

    def _artifact(project_id: str, name: str) -> Artifact:
        return Artifact(
            project_id=project_id,
            created_by=user.id,
            artifact_type="dataset",
            semantic_type="dataset",
            name=name,
        )

    def _version(artifact: Artifact, sha256: str, storage_key: str) -> ArtifactVersion:
        return ArtifactVersion(
            artifact_id=artifact.id,
            created_by=user.id,
            version=1,
            filename=f"{artifact.name}.csv",
            size_bytes=3,
            sha256=sha256,
            storage_key=storage_key,
            status="available",
        )

    artifact_a = _artifact(project.id, "project-a")
    artifact_b = _artifact(other_project.id, "project-b")
    gc_db.add_all([artifact_a, artifact_b])
    await gc_db.flush()
    version_a = _version(artifact_a, "a" * 64, "artifacts/a.csv")
    version_b = _version(artifact_b, "b" * 64, "artifacts/b.csv")
    gc_db.add_all([version_a, version_b])
    await gc_db.flush()
    version_file_a = ArtifactVersionFile(
        artifact_version_id=version_a.id,
        role="primary",
        file_id=shared_file.id,
    )
    version_file_b = ArtifactVersionFile(
        artifact_version_id=version_b.id,
        role="primary",
        file_id=shared_file.id,
    )
    gc_db.add_all([version_file_a, version_file_b])
    await gc_db.commit()

    deleted_ids: list[str] = []

    async def fake_delete(record, storage_backend=None):
        deleted_ids.append(record.id)

    class FakeStorage:
        async def delete(self, path: str) -> bool:
            return True

    monkeypatch.setattr(projects_api, "delete_stored_content", fake_delete)
    monkeypatch.setattr(projects_api, "get_storage_backend", lambda: FakeStorage())

    await projects_api._delete_project_related_rows(gc_db, project_id=project.id)
    await gc_db.commit()

    # 被其他项目产物引用的共享 File 必须保留，且对象不能删。
    assert deleted_ids == [unreferenced_file.id]
    assert await gc_db.scalar(select(File).where(File.id == shared_file.id)) is not None
    assert (
        await gc_db.scalar(
            select(ArtifactVersionFile).where(ArtifactVersionFile.id == version_file_b.id)
        )
        is not None
    )
    # 本项目独占且无产物引用的 File 正常删除并删对象。
    assert await gc_db.scalar(select(File).where(File.id == unreferenced_file.id)) is None
    assert await gc_db.scalar(select(ArtifactVersionFile).where(ArtifactVersionFile.id == version_file_a.id)) is None
