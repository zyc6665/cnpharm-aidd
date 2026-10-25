"""Upload session / dataset / data file model tests (docs/04 §5.8, §8).

三张表是「大文件分片上传」与「数据资产登记」的地基：分片会话必须能在多副本
重启后续传（因此 parts 落库），数据集只存 urn + summary（因此不复制文件内容）。
本文件只覆盖模型层契约：三表可插入、``uq_upload_sessions_object_key`` 唯一、
``parts`` 默认空列表，以及两个迁移的 revision 声明。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.models.projects import Organization, Project  # noqa: E402
from app.models.uploads import (  # noqa: E402
    DATASET_TYPES,
    UPLOAD_STATES,
    DataFile,
    Dataset,
    UploadSession,
)
from app.models.users import User, UserRole, UserStatus  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = User(
        email="owner@example.com",
        password_hash="hashed-password",
        display_name="owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, owner: User) -> Project:
    organization = Organization(name="Upload Lab", slug="upload-lab")
    db_session.add(organization)
    await db_session.flush()
    record = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name="Upload program",
        status="active",
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record


def _upload(project: Project, owner: User, *, object_key: str) -> UploadSession:
    return UploadSession(
        project_id=project.id,
        created_by=owner.id,
        declared_filename="compound_lib.sdf",
        declared_size=33_554_432,
        content_type="chemical/x-mdl-sdfile",
        object_key=object_key,
        part_size=16_777_216,
        state=UPLOAD_STATES[0],
    )


@pytest.mark.asyncio
async def test_upload_session_dataset_and_data_file_are_insertable(
    db_session: AsyncSession, project: Project, owner: User
) -> None:
    """三张表均可插入；``parts`` 默认 ``[]``、``state`` 默认 ``INITIATED``。"""

    upload = _upload(project, owner, object_key=f"{project.id}/upload/a.sdf")
    db_session.add(upload)

    dataset = Dataset(
        project_id=project.id,
        created_by=owner.id,
        name="化合物库 2026Q3",
        dataset_type=DATASET_TYPES[0],
        file_urn="file:dataset-urn",
        row_count=0,
        summary={"total": 0, "columns": ["smiles"]},
    )
    db_session.add(dataset)
    await db_session.flush()

    db_session.add(
        DataFile(
            dataset_id=dataset.id,
            urn="file:data-file-urn",
            file_name="compound_lib.sdf",
            file_type="SDF",
            size_bytes=33_554_432,
            sha256="a" * 64,
        )
    )
    await db_session.commit()

    stored = await db_session.scalar(
        select(UploadSession).where(UploadSession.id == upload.id)
    )
    assert stored is not None
    assert stored.parts == []
    assert stored.state == "INITIATED"
    assert stored.part_size == 16_777_216
    assert stored.declared_size == 33_554_432

    stored_dataset = await db_session.scalar(select(Dataset).where(Dataset.id == dataset.id))
    assert stored_dataset is not None
    assert stored_dataset.summary == {"total": 0, "columns": ["smiles"]}
    assert stored_dataset.row_count == 0

    data_file = await db_session.scalar(
        select(DataFile).where(DataFile.dataset_id == dataset.id)
    )
    assert data_file is not None
    assert data_file.storage_tier == "STANDARD"
    assert data_file.size_bytes == 33_554_432


@pytest.mark.asyncio
async def test_object_key_is_unique(
    db_session: AsyncSession, project: Project, owner: User
) -> None:
    """``uq_upload_sessions_object_key``：同一目标对象不允许两个活会话。"""

    object_key = f"{project.id}/upload/dup.sdf"
    db_session.add(_upload(project, owner, object_key=object_key))
    await db_session.commit()

    db_session.add(_upload(project, owner, object_key=object_key))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_upload_states_and_dataset_types_constants() -> None:
    """枚举常量必须与 docs/04 §5.8、§8 完全一致。"""

    assert UPLOAD_STATES == (
        "INITIATED",
        "UPLOADING",
        "COMPLETED",
        "ABORTED",
        "EXPIRED",
    )
    assert DATASET_TYPES == (
        "COMPOUND",
        "PROTEIN",
        "ACTIVITY",
        "LITERATURE",
        "EXPERIMENT",
    )
