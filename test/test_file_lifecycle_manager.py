"""文件生命周期管理器测试。"""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.common.time import utcnow
from app.database.base import Base
from app.files.lifecycle_manager import FileLifecycleManager
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.files import File, FileSourceType


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """创建隔离数据库会话。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


def make_file(filename: str, size_bytes: int, **overrides) -> File:
    """构造文件记录。"""
    return File(
        filename=filename,
        content_type="text/plain",
        size_bytes=size_bytes,
        sha256=f"sha256-{filename}",
        storage_backend="local",
        storage_path=f"/tmp/{filename}",
        source_type=FileSourceType.UPLOAD.value,
        **overrides,
    )


@pytest.mark.asyncio
async def test_file_statistics_sum_size_bytes(db_session: AsyncSession) -> None:
    """文件统计应聚合当前 size_bytes 字段。"""
    now = utcnow()
    db_session.add_all(
        [
            make_file("active-a.txt", 100),
            make_file("active-b.txt", 300, is_permanent=True),
            make_file("expiring.txt", 200, expires_at=now + timedelta(days=1)),
            make_file("expired.txt", 400, expires_at=now - timedelta(days=1)),
            make_file("deleted.txt", 900, deleted_at=now),
        ]
    )
    await db_session.commit()

    stats = await FileLifecycleManager(db_session).get_file_statistics()

    assert stats.total_files == 4
    assert stats.total_size_bytes == 1000
    assert stats.average_file_size == 250
    assert stats.permanent_files == 1
    assert stats.expiring_soon == 1
    assert stats.expired_pending_cleanup == 1


@pytest.mark.asyncio
async def test_cleanup_expired_files_reports_size_bytes_and_uses_record_backend(
    db_session: AsyncSession,
) -> None:
    file_record = make_file(
        "expired.txt",
        4096,
        expires_at=utcnow() - timedelta(days=1),
        reference_count=0,
    )
    db_session.add(file_record)
    await db_session.commit()

    class FakeStorage:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete(self, path: str) -> bool:
            self.deleted.append(path)
            return True

    storage = FakeStorage()
    manager = FileLifecycleManager(db_session, storage_backend=storage)
    manager._check_active_tasks = lambda _file_id: _empty_tasks()

    result = await manager.cleanup_expired_files()

    assert result.cleaned_count == 1
    assert result.freed_bytes == 4096
    assert storage.deleted == ["/tmp/expired.txt"]


async def _empty_tasks() -> list[str]:
    return []
