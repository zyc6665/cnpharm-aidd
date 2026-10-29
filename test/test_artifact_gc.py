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
