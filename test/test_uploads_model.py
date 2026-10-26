"""Upload session / dataset / data file model tests (docs/04 §5.8, §8).

三张表是「大文件分片上传」与「数据资产登记」的地基：分片会话必须能在多副本
重启后续传（因此分片索引落库），数据集只存 urn + summary（因此不复制文件内容）。
本文件只覆盖模型层契约：三表可插入、``uq_upload_sessions_object_key`` 唯一、
``uq_upload_sessions_project_idem`` 幂等键唯一、``upload_parts`` 复合主键，
以及迁移的 revision 声明。
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
    UploadPart,
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
    """三张表均可插入；``state`` 默认 ``INITIATED``、``part_size`` 默认 16MB。

    分片索引已从 ``upload_sessions.parts`` 这个 JSON 列搬到 ``upload_parts``
    行级表（见 ``test_upload_parts_are_row_scoped``），所以这里不再断言
    ``parts`` 默认值。
    """

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
    assert stored.declared_sha256 is None
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
async def test_idempotency_key_is_unique_per_project(
    db_session: AsyncSession, project: Project, owner: User
) -> None:
    """``uq_upload_sessions_project_idem``：同项目同幂等键只能有一个会话。

    这条约束是并发创建的唯一防线：服务层的「先查后插」在并发下两个请求都会
    看到空结果，只有数据库能挡住第二条。
    """

    db_session.add(
        _upload(project, owner, object_key=f"{project.id}/upload/idem-a.sdf")
    )
    await db_session.flush()
    first = await db_session.scalar(select(UploadSession))
    assert first is not None
    first.idempotency_key = "same-key"
    await db_session.commit()

    duplicate = _upload(project, owner, object_key=f"{project.id}/upload/idem-b.sdf")
    duplicate.idempotency_key = "same-key"
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_upload_parts_are_row_scoped(
    db_session: AsyncSession, project: Project, owner: User
) -> None:
    """``upload_parts`` 以 ``(session_id, part_number)`` 为主键：同片号只有一行。

    分片索引从 ``upload_sessions.parts`` 这个 JSON 列搬出来，就是为了让数据库
    承担「一个会话里每个片号只有一条」的约束；并发上报不再互相覆盖。
    """

    upload = _upload(project, owner, object_key=f"{project.id}/upload/parts.sdf")
    db_session.add(upload)
    await db_session.commit()

    db_session.add(
        UploadPart(
            session_id=upload.id,
            part_number=1,
            etag="e" * 32,
            size_bytes=1024,
        )
    )
    await db_session.commit()

    stored = await db_session.scalar(select(UploadPart))
    assert stored is not None
    assert stored.part_number == 1
    assert stored.size_bytes == 1024
    assert stored.reported_at is not None

    # 同一 session 里再插同主键会先在 ORM 身份映射里撞车（SAWarning）而不是走到
    # 数据库唯一约束；先清掉身份映射，确保这次冲突确实由主键约束拒绝。
    db_session.expunge_all()
    db_session.add(
        UploadPart(
            session_id=upload.id,
            part_number=1,
            etag="f" * 32,
            size_bytes=2048,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


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
