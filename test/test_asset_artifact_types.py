"""资产根 Artifact 的受控类型枚举（Task 5 §7.1）。

守四件事：

1. 8 个受控类型是**唯一真源**，且标准注册表里出现过的 ``type`` 必须全部落在其中
   （防止标准 yaml 新增类型后与资产枚举悄悄漂移）。
2. 历史别名能被归一为合法类型；无法归一的旧值返回 ``None``，供探测显式告警，
   而不是静默改写/丢弃。
3. 模型层 CHECK 约束会拒绝非法 ``artifact_type``——覆盖包括执行回传在内的全部写入路径。
4. Pydantic 入口校验把非法值挡成 422，而不是让它落到数据库变成 500。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.artifact_standards.asset_types import (  # noqa: E402
    ASSET_ARTIFACT_TYPES,
    ASSET_ARTIFACT_TYPE_SET,
    ASSET_ARTIFACT_TYPE_CHECK_SQL,
    is_asset_artifact_type,
    normalize_asset_artifact_type,
)
from app.artifact_standards.registry import load_standard_artifact_specs  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.models.artifacts import Artifact  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.schemas.artifacts import ArtifactMetadata  # noqa: E402

EXPECTED_TYPES = {
    "compound_set",
    "protein_structure",
    "binding_pocket",
    "ligand_structure",
    "molecule_table",
    "md_trajectory",
    "run_report",
    "dataset",
}


def test_asset_types_are_exactly_the_eight_controlled_values() -> None:
    assert set(ASSET_ARTIFACT_TYPES) == EXPECTED_TYPES
    assert len(ASSET_ARTIFACT_TYPES) == 8
    assert ASSET_ARTIFACT_TYPE_SET == EXPECTED_TYPES


def test_every_standard_registry_type_is_a_valid_asset_type() -> None:
    """标准 yaml 的 ``type`` 必须全部落在 8 值内，否则枚举与 registry 已漂移。"""
    specs = load_standard_artifact_specs()
    assert specs, "标准注册表不应为空"
    extra = {spec.type for spec in specs.values()} - ASSET_ARTIFACT_TYPE_SET
    assert not extra, f"标准注册表出现资产枚举之外的类型：{sorted(extra)}"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("protein_structure", "protein_structure"),
        ("dataset", "dataset"),
        ("protein_structure@1", "protein_structure"),
        ("database_query_result", "molecule_table"),
        ("protein_pdb", "protein_structure"),
        ("docking_pose", "ligand_structure"),
        ("pocket_result", "binding_pocket"),
        ("file", "run_report"),
        (" custom_vendor_blob ", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_asset_artifact_type(raw: object, expected: str | None) -> None:
    assert normalize_asset_artifact_type(raw) == expected


def test_check_sql_covers_all_eight_values() -> None:
    assert ASSET_ARTIFACT_TYPE_CHECK_SQL.startswith("artifact_type IN (")
    for value in EXPECTED_TYPES:
        assert f"'{value}'" in ASSET_ARTIFACT_TYPE_CHECK_SQL


def test_is_asset_artifact_type_rejects_unknown() -> None:
    assert is_asset_artifact_type("molecule_table") is True
    assert is_asset_artifact_type("database_query_result") is False
    assert is_asset_artifact_type(None) is False


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
        yield session
    await engine.dispose()


async def _build_owner_project(db: AsyncSession) -> tuple[User, Project]:
    user = User(
        email="owner@example.com",
        password_hash="hashed-password",
        display_name="owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()
    organization = Organization(name="Asset org", slug="asset-org")
    db.add(organization)
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=user.id,
        name="Asset program",
        status="active",
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    await db.commit()
    return user, project


@pytest.mark.asyncio
async def test_model_check_constraint_rejects_illegal_artifact_type(
    db_session: AsyncSession,
) -> None:
    user, project = await _build_owner_project(db_session)
    db_session.add(
        Artifact(
            project_id=project.id,
            created_by=user.id,
            artifact_type="database_query_result",
            semantic_type="molecule_table",
            name="非法类型",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_model_accepts_every_controlled_type(db_session: AsyncSession) -> None:
    user, project = await _build_owner_project(db_session)
    for index, artifact_type in enumerate(ASSET_ARTIFACT_TYPES):
        db_session.add(
            Artifact(
                project_id=project.id,
                created_by=user.id,
                artifact_type=artifact_type,
                semantic_type=artifact_type,
                name=f"资产 {index}",
            )
        )
    await db_session.flush()


def test_metadata_schema_rejects_illegal_artifact_type() -> None:
    with pytest.raises(ValidationError):
        ArtifactMetadata(artifact_type="database_query_result", semantic_type="molecule_table")


@pytest.mark.parametrize("artifact_type", sorted(EXPECTED_TYPES))
def test_metadata_schema_accepts_controlled_types(artifact_type: str) -> None:
    metadata = ArtifactMetadata(artifact_type=artifact_type, semantic_type=artifact_type)
    assert metadata.artifact_type == artifact_type
