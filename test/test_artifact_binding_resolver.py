"""Artifact binding resolver policy tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    Artifact,
    ArtifactVersion,
    ArtifactVersionFile,
    File,
    Organization,
    Project,
    User,
)
from app.models.artifacts import Artifact as ArtifactModel  # noqa: E402
from app.models.artifacts import ArtifactVersion as ArtifactVersionModel  # noqa: E402
from app.models.artifacts import ArtifactVersionFile as ArtifactVersionFileModel  # noqa: E402
from app.models.files import File as FileModel  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.users import User as UserModel  # noqa: E402
from app.models.users import UserRole, UserStatus  # noqa: E402
from app.services.artifact_binding_resolver import (  # noqa: E402
    resolve_artifact_binding,
    resolve_artifact_binding_policy,
)


@pytest_asyncio.fixture
async def resolver_db() -> AsyncSession:
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


async def _seed_prepared_protein_version(
    db: AsyncSession,
) -> tuple[ArtifactVersionModel, FileModel]:
    user = UserModel(
        email="binding-resolver@example.com",
        password_hash="hashed",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()

    artifact = ArtifactModel(
        project_id="project-1",
        created_by=user.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        standard_type="protein_structure",
        standard_version=1,
        name="prepared protein",
    )
    db.add(artifact)
    await db.flush()

    version = ArtifactVersionModel(
        artifact_id=artifact.id,
        created_by=user.id,
        version=1,
        filename="prepared-protein.manifest.json",
        content_type="application/json",
        size_bytes=2,
        sha256="0" * 64,
        storage_key="legacy/prepared-protein.manifest.json",
        validation_status="passed",
        validation_errors=[],
        manifest_json={
            "type": "protein_structure@1",
            "metadata": {"preparation_status": "prepared"},
        },
        summary_json={},
        metrics_json={},
    )
    db.add(version)
    await db.flush()

    structure_file = FileModel(
        project_id="project-1",
        owner_id=user.id,
        filename="structure.pdb",
        content_type="chemical/x-pdb",
        size_bytes=4,
        sha256="1" * 64,
        storage_path="/tmp/structure.pdb",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    prepared_file = FileModel(
        project_id="project-1",
        owner_id=user.id,
        filename="prepared.pdb",
        content_type="chemical/x-pdb",
        size_bytes=4,
        sha256="2" * 64,
        storage_path="/tmp/prepared.pdb",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    db.add_all([structure_file, prepared_file])
    await db.flush()
    db.add_all(
        [
            ArtifactVersionFileModel(
                artifact_version_id=version.id,
                role="structure_file",
                file_id=structure_file.id,
                is_primary=True,
                sort_order=0,
            ),
            ArtifactVersionFileModel(
                artifact_version_id=version.id,
                role="prepared_pdb",
                file_id=prepared_file.id,
                sort_order=1,
            ),
        ]
    )
    artifact.latest_version_id = version.id
    await db.flush()
    return version, prepared_file


def test_raw_protein_that_requires_preparation_returns_preparation_decision() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "protein",
            "type": "protein_structure@1",
            "readiness_policy": "require_prepared",
        },
        artifact_type="protein_structure@1",
        available_roles={"structure_file"},
        metadata={"preparation_status": "raw"},
    )

    assert decision.status == "needs_preparation"
    assert decision.input_name == "protein"
    assert decision.standard_type == "protein_structure@1"
    assert decision.selected_role is None
    assert decision.suggested_tool_slug == "builtin-protein-preparation"


def test_prepared_protein_selects_prepared_pdb_for_prepared_policy() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "protein",
            "type": "protein_structure@1",
            "readiness_policy": "require_prepared",
        },
        artifact_type="protein_structure@1",
        available_roles={"structure_file", "prepared_pdb"},
        metadata={"preparation_status": "prepared"},
    )

    assert decision.status == "ready"
    assert decision.selected_role == "prepared_pdb"
    assert decision.suggested_tool_slug is None


def test_receptor_policy_selects_receptor_pdbqt() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "receptor",
            "type": "protein_structure@1",
            "readiness_policy": "require_receptor",
        },
        artifact_type="protein_structure@1",
        available_roles={"structure_file", "prepared_pdb", "receptor_pdbqt"},
        metadata={"preparation_status": "prepared"},
    )

    assert decision.status == "ready"
    assert decision.selected_role == "receptor_pdbqt"


def test_ligand_policy_prefers_3d_sdf() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "ligand",
            "type": "ligand_structure@1",
            "readiness_policy": "prefer_3d_ligand",
        },
        artifact_type="ligand_structure@1",
        available_roles={"structure_file", "structure_3d_sdf"},
        metadata={"structure_3d_source": "pubchem_3d"},
    )

    assert decision.status == "ready"
    assert decision.selected_role == "structure_3d_sdf"


def test_ligand_policy_converts_2d_only_ligand() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "ligand",
            "type": "ligand_structure@1",
            "readiness_policy": "prefer_3d_ligand",
        },
        artifact_type="ligand_structure@1",
        available_roles={"structure_2d_sdf"},
        metadata={"structure_3d_source": "2d_only"},
    )

    assert decision.status == "needs_conversion"
    assert decision.selected_role is None
    assert decision.suggested_tool_slug == "builtin-rdkit-conformer"


def test_type_mismatch_is_invalid() -> None:
    decision = resolve_artifact_binding_policy(
        input_slot={
            "name": "protein",
            "type": "protein_structure@1",
            "readiness_policy": "allow_raw",
        },
        artifact_type="ligand_structure@1",
        available_roles={"structure_file"},
        metadata={},
    )

    assert decision.status == "invalid"
    assert decision.selected_role is None
    assert decision.suggested_tool_slug is None


@pytest.mark.asyncio
async def test_resolver_loads_artifact_version_roles_from_database(
    resolver_db: AsyncSession,
) -> None:
    version, prepared_file = await _seed_prepared_protein_version(resolver_db)

    decision = await resolve_artifact_binding(
        resolver_db,
        input_slot={
            "name": "protein",
            "type": "protein_structure@1",
            "readiness_policy": "require_prepared",
        },
        candidate_artifact_version_id=version.id,
    )

    assert decision.status == "ready"
    assert decision.input_name == "protein"
    assert decision.standard_type == "protein_structure@1"
    assert decision.selected_role == "prepared_pdb"
    assert decision.selected_file_id == prepared_file.id
    assert decision.artifact_version_id == version.id
