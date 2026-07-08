"""文件去重统计测试。"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.files.deduplication import FileDeduplicator
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.files import File, FileSourceType


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
        autoflush=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


def make_file(filename: str, size_bytes: int, reference_count: int = 1) -> File:
    return File(
        filename=filename,
        content_type="text/plain",
        size_bytes=size_bytes,
        sha256=f"sha-{filename}",
        storage_backend="local",
        storage_path=f"/tmp/{filename}",
        source_type=FileSourceType.UPLOAD.value,
        reference_count=reference_count,
    )


@pytest.mark.asyncio
async def test_storage_stats_sum_size_bytes_and_saved_space(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            make_file("primary.txt", 100, reference_count=1),
            make_file("shared.txt", 300, reference_count=3),
        ]
    )
    await db_session.commit()

    stats = await FileDeduplicator(db_session).get_storage_stats()

    assert stats["total_files"] == 2
    assert stats["total_size_bytes"] == 400
    assert stats["space_saved_bytes"] == 600
    assert stats["deduplication_ratio"] == 60


@pytest.mark.asyncio
async def test_duplicate_info_uses_size_bytes(db_session: AsyncSession) -> None:
    file_record = make_file("duplicate.txt", 256, reference_count=2)
    db_session.add(file_record)
    await db_session.commit()

    info = await FileDeduplicator(db_session).get_duplicate_info(file_record.sha256)

    assert info is not None
    assert info["file_id"] == file_record.id
    assert info["size"] == 256
    assert info["reference_count"] == 2
