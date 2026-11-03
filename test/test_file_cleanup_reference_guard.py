"""过期文件清理的引用守卫测试。

回归背景：生产每小时定时任务曾走一份 naive 硬删实现，直接
``delete_stored_content`` + ``db.delete(file)``，既不看 TaskInput/TaskOutput/
ArtifactVersionFile 引用，也不看 ``is_permanent``/``deleted_at``，会把运行中任务的
输入文件和产物 blob 直接删掉。本文件锁定安全实现（``FileLifecycleManager``）的行为：

* 被 ArtifactVersionFile / TaskInput / TaskOutput 引用的过期文件不删、不软删；
* 永久文件不删；
* 无引用的过期文件只软删（置 ``deleted_at``），blob 仍在；
* 重复执行幂等（第二次不再软删）；
* 单条异常不中断整批。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - 注册全部表到 Base.metadata
from app.common.time import utcnow
from app.database.base import Base
from app.files.file_records import file_storage_path
from app.files.lifecycle_manager import FileLifecycleManager
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.files import File, FileSourceType
from app.models.projects import Organization, Project
from app.models.tasks import TaskInput
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def db(tmp_path) -> AsyncSession:
    """隔离的文件型 SQLite 会话（避免多事件循环下内存库跨 loop 的坑）。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cleanup.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session
    await engine.dispose()


def _file(name: str, *, expires_in_days: float = -1, **overrides) -> File:
    storage_path = overrides.pop("storage_path", f"storage/{name}")
    return File(
        filename=name,
        content_type="application/octet-stream",
        size_bytes=3,
        sha256=f"sha-{name}",
        storage_backend="local",
        storage_path=storage_path,
        source_type=FileSourceType.UPLOAD.value,
        expires_at=utcnow() + timedelta(days=expires_in_days),
        **overrides,
    )


async def _seed_artifact_version(db: AsyncSession) -> ArtifactVersion:
    user = User(
        email="cleanup@example.com",
        password_hash="hashed",
        display_name="cleanup",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    organization = Organization(name="Cleanup Lab", slug="cleanup-lab")
    db.add_all([user, organization])
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=user.id,
        name="Cleanup Project",
        status="active",
    )
    db.add(project)
    await db.flush()
    artifact = Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type="dataset",
        semantic_type="dataset",
        name="expired-artifact",
    )
    db.add(artifact)
    await db.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=user.id,
        version=1,
        filename="expired-artifact.csv",
        size_bytes=3,
        sha256="a" * 64,
        storage_key="artifacts/expired-artifact.csv",
        status="available",
    )
    db.add(version)
    await db.flush()
    return version


@pytest.mark.asyncio
async def test_expired_file_referenced_by_artifact_version_is_kept(db: AsyncSession) -> None:
    """① 被 ArtifactVersionFile 引用的过期文件既不删也不软删。"""
    version = await _seed_artifact_version(db)
    expired = _file("artifact-referenced.bin")
    db.add(expired)
    await db.flush()
    db.add(
        ArtifactVersionFile(
            artifact_version_id=version.id,
            role="primary",
            file_id=expired.id,
            is_primary=True,
        )
    )
    await db.commit()
    expired_id = expired.id

    result = await FileLifecycleManager(db).cleanup_expired_files()

    assert result.scanned == 1
    assert result.skipped_referenced == 1
    assert result.soft_deleted == 0
    refreshed = await db.get(File, expired_id)
    assert refreshed is not None
    assert refreshed.deleted_at is None


@pytest.mark.asyncio
async def test_expired_file_referenced_by_task_input_is_kept(db: AsyncSession) -> None:
    """② 被 TaskInput.file_ids 引用的过期文件不删。"""
    expired = _file("task-input.bin")
    db.add(expired)
    await db.flush()
    db.add(TaskInput(task_id="task-1", params={}, file_ids=[expired.id]))
    await db.commit()
    expired_id = expired.id

    result = await FileLifecycleManager(db).cleanup_expired_files()

    assert result.skipped_referenced == 1
    assert result.soft_deleted == 0
    refreshed = await db.get(File, expired_id)
    assert refreshed is not None
    assert refreshed.deleted_at is None


@pytest.mark.asyncio
async def test_expired_permanent_file_is_kept(db: AsyncSession) -> None:
    """③ is_permanent 的过期文件不删。"""
    permanent = _file("permanent.bin", is_permanent=True)
    db.add(permanent)
    await db.commit()
    permanent_id = permanent.id

    result = await FileLifecycleManager(db).cleanup_expired_files()

    assert result.skipped_permanent == 1
    assert result.soft_deleted == 0
    refreshed = await db.get(File, permanent_id)
    assert refreshed is not None
    assert refreshed.deleted_at is None


@pytest.mark.asyncio
async def test_unreferenced_expired_file_is_soft_deleted_but_blob_survives(
    db: AsyncSession, tmp_path
) -> None:
    """④ 无引用的过期文件被软删，但落盘 blob 仍在。"""
    blob = tmp_path / "unreferenced.bin"
    blob.write_bytes(b"still-here")
    expired = _file("unreferenced.bin", storage_path=str(blob))
    db.add(expired)
    await db.commit()
    expired_id = expired.id

    result = await FileLifecycleManager(db).cleanup_expired_files()

    assert result.soft_deleted == 1
    assert result.skipped_referenced == 0
    refreshed = await db.get(File, expired_id)
    assert refreshed is not None
    assert refreshed.deleted_at is not None
    # blob 未被删除：软删不动物理对象。
    assert file_storage_path(refreshed).exists()
    assert blob.read_bytes() == b"still-here"


@pytest.mark.asyncio
async def test_cleanup_is_idempotent(db: AsyncSession) -> None:
    """⑤ 重复执行幂等：第二次不再软删同一文件。"""
    expired = _file("idempotent.bin")
    db.add(expired)
    await db.commit()
    expired_id = expired.id

    manager = FileLifecycleManager(db)
    first = await manager.cleanup_expired_files()
    second = await manager.cleanup_expired_files()

    assert first.soft_deleted == 1
    assert second.soft_deleted == 0
    refreshed = await db.get(File, expired_id)
    assert refreshed is not None
    assert refreshed.deleted_at is not None


@pytest.mark.asyncio
async def test_single_failure_does_not_abort_batch(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⑥ 单条处理抛异常不会中断整批，其余文件仍被软删。"""
    db.add_all([_file("ok-1.bin"), _file("boom.bin"), _file("ok-2.bin")])
    await db.commit()

    manager = FileLifecycleManager(db)
    original = manager._process_expired_file

    async def flaky(file, reference_sources, *, now, dry_run):
        if file.filename == "boom.bin":
            raise RuntimeError("simulated per-file failure")
        return await original(file, reference_sources, now=now, dry_run=dry_run)

    monkeypatch.setattr(manager, "_process_expired_file", flaky)

    result = await manager.cleanup_expired_files()

    assert result.failed == 1
    assert result.soft_deleted == 2
    assert result.errors and result.errors[0]["filename"] == "boom.bin"

    states = {
        filename: deleted_at
        for filename, deleted_at in (
            (await db.execute(select(File.filename, File.deleted_at))).all()
        )
    }
    assert states["boom.bin"] is None
    assert states["ok-1.bin"] is not None
    assert states["ok-2.bin"] is not None
