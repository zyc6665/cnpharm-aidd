"""Standard Artifact persistence service tests."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.execution.result_parser import ParsedStandardResult, parse_standard_result
from app.execution.standard_contracts import DeclaredArtifactOutput
from app.models import (  # noqa: F401
    Artifact,
    ArtifactLineage,
    ArtifactVersion,
    ArtifactVersionFile,
    File,
    Organization,
    Project,
    Task,
    Tool,
    ToolVersion,
    User,
)
from app.models.artifacts import ArtifactVersion as ArtifactVersionModel
from app.models.artifacts import ArtifactVersionFile as ArtifactVersionFileModel
from app.models.files import File as FileModel, FileSourceType
from app.models.tasks import TaskStatus
from app.models.tools import ToolStatus
from app.models.users import UserRole, UserStatus
from app.services.standard_artifacts import (
    StandardArtifactPersistenceError,
    create_artifact_versions_from_parsed_result,
    standard_artifact_result_summary,
)


def _write_file(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    return tmp_path / "output"


@pytest.fixture
def binding_result_path(output_dir: Path) -> Path:
    residue_sha = _write_file(output_dir / "artifacts/pocket/residue.pdb", b"residue")
    atom_sha = _write_file(output_dir / "artifacts/pocket/atom.pdb", b"atom")
    metadata_sha = _write_file(output_dir / "artifacts/pocket/metadata.json", b"{}")
    report_sha = _write_file(output_dir / "reports/report.json", b'{"ok": true}')
    path = output_dir / "result.json"
    path.write_text(
        json.dumps(
            {
                "result_version": "aidd.sciminer/result.v2",
                "artifacts": {
                    "pocket": {
                        "name": "Top pocket",
                        "type": "binding_pocket@1",
                        "files": {
                            "residue_pocket_pdb": {
                                "path": "artifacts/pocket/residue.pdb",
                                "sha256": residue_sha,
                            },
                            "atom_pocket_pdb": {
                                "path": "artifacts/pocket/atom.pdb",
                                "sha256": atom_sha,
                            },
                            "pocket_metadata_json": {
                                "path": "artifacts/pocket/metadata.json",
                                "sha256": metadata_sha,
                            },
                        },
                    },
                    "report": {
                        "name": "Run report",
                        "type": "run_report@1",
                        "files": {
                            "report_json": {
                                "path": "reports/report.json",
                                "sha256": report_sha,
                            }
                        },
                    },
                },
                "relations": [
                    {"from": "report", "to": "pocket", "type": "describes"}
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def ligand_result_path(output_dir: Path) -> Path:
    first_sha = _write_file(output_dir / "ligands/001.sdf", b"ligand 1")
    second_sha = _write_file(output_dir / "ligands/002.sdf", b"ligand 2")
    path = output_dir / "result.json"
    path.write_text(
        json.dumps(
            {
                "result_version": "aidd.sciminer/result.v2",
                "artifacts": {
                    "generated_ligands": [
                        {
                            "name": "ligand_001",
                            "type": "ligand_structure@1",
                            "files": {
                                "structure_file": {
                                    "path": "ligands/001.sdf",
                                    "sha256": first_sha,
                                }
                            },
                        },
                        {
                            "name": "ligand_002",
                            "type": "ligand_structure@1",
                            "files": {
                                "structure_file": {
                                    "path": "ligands/002.sdf",
                                    "sha256": second_sha,
                                }
                            },
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest_asyncio.fixture
async def standard_db() -> AsyncSession:
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


async def _seed_task(db: AsyncSession) -> Task:
    user = User(
        email="standard-artifacts@example.com",
        password_hash="hashed",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    organization = Organization(name="Standard Lab", slug="standard-lab")
    db.add_all([user, organization])
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=user.id,
        name="Standard artifacts",
        status="active",
    )
    db.add(project)
    await db.flush()
    tool = Tool(
        owner_id=user.id,
        name="Standard Tool",
        slug="standard-tool",
        status=ToolStatus.PUBLISHED.value,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(tool_id=tool.id, version="1.0.0", config={"type": "builtin"})
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    task = Task(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        status=TaskStatus.SUCCESS.value,
        extra_data={"project_id": project.id},
    )
    db.add(task)
    await db.commit()
    return task


@pytest.mark.asyncio
async def test_service_persists_binding_pocket_with_file_roles(
    standard_db: AsyncSession,
    binding_result_path: Path,
    output_dir: Path,
):
    task = await _seed_task(standard_db)
    parsed = parse_standard_result(
        result_path=binding_result_path,
        output_dir=output_dir,
        declared_outputs=[
            DeclaredArtifactOutput(name="pocket", type="binding_pocket@1"),
            DeclaredArtifactOutput(name="report", type="run_report@1"),
        ],
    )

    result = await create_artifact_versions_from_parsed_result(
        standard_db,
        task=task,
        parsed_result=parsed,
    )

    pocket_version_id = result.artifact_version_ids_by_ref["pocket"]
    loaded = (
        await standard_db.execute(
            select(ArtifactVersionModel)
            .options(selectinload(ArtifactVersionModel.files))
            .where(ArtifactVersionModel.id == pocket_version_id)
        )
    ).scalar_one()
    lineage_count = await standard_db.scalar(select(func.count(ArtifactLineage.id)))

    assert result.artifact_ids_by_ref["pocket"] == loaded.artifact_id
    assert standard_artifact_result_summary(result)["artifact_ids_by_ref"]["pocket"] == loaded.artifact_id
    assert loaded.validation_status == "passed"
    assert loaded.manifest_json["type"] == "binding_pocket@1"
    assert {file.role for file in loaded.files} == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }
    assert lineage_count == 1


@pytest.mark.asyncio
async def test_service_persists_cardinality_many_outputs(
    standard_db: AsyncSession,
    ligand_result_path: Path,
    output_dir: Path,
):
    task = await _seed_task(standard_db)
    parsed = parse_standard_result(
        result_path=ligand_result_path,
        output_dir=output_dir,
        declared_outputs=[
            DeclaredArtifactOutput(
                name="generated_ligands",
                type="ligand_structure@1",
                cardinality="many",
            )
        ],
    )

    result = await create_artifact_versions_from_parsed_result(
        standard_db,
        task=task,
        parsed_result=parsed,
    )

    assert set(result.artifact_version_ids_by_ref) == {
        "generated_ligands[0]",
        "generated_ligands[1]",
    }
    role_count = await standard_db.scalar(select(func.count(ArtifactVersionFileModel.id)))
    assert role_count == 2


@pytest.mark.asyncio
async def test_service_can_use_precollected_file_records(
    standard_db: AsyncSession,
    ligand_result_path: Path,
    output_dir: Path,
):
    task = await _seed_task(standard_db)
    parsed = parse_standard_result(
        result_path=ligand_result_path,
        output_dir=output_dir,
        declared_outputs=[
            DeclaredArtifactOutput(
                name="generated_ligands",
                type="ligand_structure@1",
                cardinality="many",
            )
        ],
    )
    existing_file = FileModel(
        project_id=task.extra_data["project_id"],
        owner_id=task.user_id,
        filename="001.sdf",
        content_type="chemical/x-mdl-sdfile",
        size_bytes=8,
        sha256=parsed.artifacts[0].files["structure_file"].sha256,
        storage_path="/durable/storage/001.sdf",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    standard_db.add(existing_file)
    await standard_db.flush()

    def resolve_file(artifact, role, parsed_file):
        if artifact.index == 0:
            return existing_file
        return FileModel(
            project_id=task.extra_data["project_id"],
            owner_id=task.user_id,
            filename=Path(parsed_file.path).name,
            content_type="chemical/x-mdl-sdfile",
            size_bytes=8,
            sha256=parsed_file.sha256,
            storage_path=f"/durable/storage/{Path(parsed_file.path).name}",
            source_type=FileSourceType.TOOL_OUTPUT.value,
        )

    result = await create_artifact_versions_from_parsed_result(
        standard_db,
        task=task,
        parsed_result=parsed,
        file_record_resolver=resolve_file,
    )

    loaded_file = await standard_db.get(FileModel, existing_file.id)
    first_version = await standard_db.get(
        ArtifactVersionModel,
        result.artifact_version_ids_by_ref["generated_ligands[0]"],
    )

    assert loaded_file.file_meta["standard_artifact_role"] == "structure_file"
    assert first_version.storage_key == "/durable/storage/001.sdf"


@pytest.mark.asyncio
async def test_service_rejects_invalid_relation_type(standard_db: AsyncSession):
    task = await _seed_task(standard_db)
    parsed = ParsedStandardResult(
        artifacts=[],
        relations=[{"from": "a", "to": "b", "type": "include"}],
        summary={},
        metrics={},
    )

    with pytest.raises(StandardArtifactPersistenceError, match="Unknown relation type"):
        await create_artifact_versions_from_parsed_result(
            standard_db,
            task=task,
            parsed_result=parsed,
        )
