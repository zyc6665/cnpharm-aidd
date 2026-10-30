"""A｜产物三列身份收口：解析器 / 三条写入服务路径 / DB CHECK 守护测试。

覆盖：
- ``resolve_identity`` / ``resolve_identity_full`` 各分支（标准、非标准、``@vN`` 剥离、
  非法类型、类型冲突、版本冲突）；
- 三个真正构造 ``Artifact`` 行的写入服务路径：``artifact_writer.upsert_artifact``、
  ``services.artifacts.create_artifact``、``standard_artifacts._persist_artifact``
  ——构造写入后读回，断言三列满足不变量；
- SQLite 上 DB CHECK 生效：直接插入违反 ``standard_type`` 不变量的行被拒绝。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.artifact_standards.registry import get_standard_artifact_spec
from app.common.exceptions import ValidationException
from app.database.base import Base
from app.execution.result_parser import ParsedStandardArtifact, ParsedStandardFile
from app.models.artifacts import Artifact
from app.models.files import File as FileModel
from app.services import artifacts as artifact_service
from app.services.artifact_identity import (
    resolve_identity,
    resolve_identity_full,
    split_semantic_version,
)
from app.services.artifact_writer import upsert_artifact
from app.services.standard_artifacts import _persist_artifact


# --------------------------------------------------------------------------- #
# resolve_identity 纯函数分支
# --------------------------------------------------------------------------- #
def test_standard_identity_collapses_three_columns() -> None:
    assert resolve_identity(
        "protein_structure",
        standard_type="protein_structure",
        standard_version=2,
    ) == ("protein_structure", "protein_structure", "protein_structure")
    assert resolve_identity_full(
        "protein_structure",
        standard_type="protein_structure",
        standard_version=2,
    ) == ("protein_structure", "protein_structure", "protein_structure", 2)


def test_semantic_at_version_is_stripped_into_standard_version() -> None:
    assert split_semantic_version("protein_structure@3") == ("protein_structure", 3)
    assert resolve_identity_full(
        "protein_structure",
        semantic_type="protein_structure@3",
    ) == ("protein_structure", "protein_structure", "protein_structure", 3)
    # 三列接口不返回版本，但 semantic 已被剥离。
    assert resolve_identity(
        "protein_structure",
        semantic_type="protein_structure@3",
    ) == ("protein_structure", "protein_structure", "protein_structure")


def test_non_standard_identity_tracks_artifact_type() -> None:
    # 自由子标签降级为 artifact_type，standard_type 保持 NULL。
    assert resolve_identity("dataset", semantic_type="generic_file") == (
        "dataset",
        "dataset",
        None,
    )
    assert resolve_identity_full("dataset", semantic_type="generic_file") == (
        "dataset",
        "dataset",
        None,
        None,
    )
    assert resolve_identity("compound_set") == ("compound_set", "compound_set", None)


def test_invalid_artifact_type_raises() -> None:
    with pytest.raises(ValidationException):
        resolve_identity("not_a_controlled_type")
    with pytest.raises(ValidationException):
        resolve_identity_full("not_a_controlled_type")


def test_artifact_type_standard_type_conflict_raises() -> None:
    with pytest.raises(ValidationException):
        resolve_identity(
            "protein_structure",
            standard_type="molecule_table",
            standard_version=1,
        )


def test_embedded_version_conflict_with_standard_version_raises() -> None:
    with pytest.raises(ValidationException):
        resolve_identity_full(
            "protein_structure",
            semantic_type="protein_structure@2",
            standard_version=3,
        )


# --------------------------------------------------------------------------- #
# 三条写入服务路径：构造写入 → 读回
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def db() -> AsyncSession:
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


def _assert_invariant(row: Artifact) -> None:
    assert row.semantic_type == row.artifact_type
    assert row.standard_type is None or row.standard_type == row.artifact_type


@pytest.mark.asyncio
async def test_upsert_artifact_path_enforces_invariant(db: AsyncSession) -> None:
    # 标准产物：semantic 带 @vN、standard_type/version 显式给出 → 三列收敛、版本进位。
    standard, _ = await upsert_artifact(
        db,
        project_id="project-1",
        artifact_type="protein_structure",
        semantic_type="protein_structure@2",
        name="pocket.pdb",
        created_by="user-1",
        standard_type="protein_structure",
        standard_version=2,
        match_name=True,
    )
    # 非标准产物：自由子标签降级，standard_type 为 NULL。
    plain, _ = await upsert_artifact(
        db,
        project_id="project-1",
        artifact_type="dataset",
        semantic_type="raw_measurements",
        name="data.csv",
        created_by="user-1",
    )
    await db.commit()

    reloaded = {
        row.id: row
        for row in (await db.execute(select(Artifact))).scalars().all()
    }
    standard_row = reloaded[standard.id]
    plain_row = reloaded[plain.id]
    _assert_invariant(standard_row)
    _assert_invariant(plain_row)
    assert standard_row.semantic_type == "protein_structure"
    assert standard_row.standard_type == "protein_structure"
    assert standard_row.standard_version == 2
    assert plain_row.standard_type is None
    assert plain_row.semantic_type == "dataset"


@pytest.mark.asyncio
async def test_create_artifact_upload_path_enforces_invariant(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_store(db_session, *, project, user, filename, content, content_type, expires_at):
        record = FileModel(
            project_id=project.id,
            owner_id=user.id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            sha256="0" * 64,
            storage_path=f"/tmp/fake/{filename}",
        )
        db_session.add(record)
        await db_session.flush()
        return record

    monkeypatch.setattr(artifact_service, "_store_uploaded_file", fake_store)

    created = await artifact_service.create_artifact(
        db,
        project=SimpleNamespace(id="project-1"),
        user=SimpleNamespace(id="user-1"),
        filename="payload.bin",
        content=b"payload",
        content_type="application/octet-stream",
        artifact_type="dataset",
        semantic_type="generic_file",
    )

    row = (
        await db.execute(select(Artifact).where(Artifact.id == created.id))
    ).scalar_one()
    _assert_invariant(row)
    assert row.artifact_type == "dataset"
    assert row.semantic_type == "dataset"
    assert row.standard_type is None


@pytest.mark.asyncio
async def test_standard_persist_path_enforces_invariant(db: AsyncSession) -> None:
    ref = "protein_structure@1"
    spec = get_standard_artifact_spec(ref)
    primary_role = next((role.role for role in spec.file_roles if role.primary), None) or (
        spec.file_roles[0].role
    )

    file_record = FileModel(
        project_id="project-1",
        owner_id="user-1",
        filename="model.pdb",
        content_type="chemical/x-pdb",
        size_bytes=123,
        sha256="a" * 64,
        storage_path="/tmp/fake/model.pdb",
    )
    db.add(file_record)
    await db.flush()

    parsed_file = ParsedStandardFile(
        role=primary_role,
        path=Path("/tmp/fake/model.pdb"),
        relative_path="model.pdb",
        sha256="a" * 64,
        content_type="chemical/x-pdb",
    )
    parsed = ParsedStandardArtifact(
        output_name="protein",
        type=ref,
        name="model.pdb",
        files={primary_role: parsed_file},
    )
    task = SimpleNamespace(
        id="task-1",
        user_id="user-1",
        extra_data={},
        tool_version_id=None,
    )

    def resolve_file(_artifact, _role, _parsed_file):
        return file_record

    _ref_key, artifact_id, _version_id, _file_ids = await _persist_artifact(
        db,
        task=task,
        project_id="project-1",
        user_id="user-1",
        artifact=parsed,
        file_record_resolver=resolve_file,
    )
    await db.commit()

    row = (
        await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    ).scalar_one()
    _assert_invariant(row)
    assert row.artifact_type == "protein_structure"
    assert row.semantic_type == "protein_structure"
    assert row.standard_type == "protein_structure"
    assert row.standard_version == 1


# --------------------------------------------------------------------------- #
# DB CHECK 守护
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_db_check_rejects_standard_type_mismatch(db: AsyncSession) -> None:
    db.add(
        Artifact(
            project_id="project-1",
            created_by="user-1",
            artifact_type="protein_structure",
            semantic_type="protein_structure",
            standard_type="molecule_table",  # 违反 CHECK
            name="bad",
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()
