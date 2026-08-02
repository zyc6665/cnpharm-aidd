"""Standard request.v1 builder tests."""

from __future__ import annotations

import hashlib
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

from app.database.base import Base
from app.execution.request_builder import (
    StandardExecutionBuildContext,
    StandardRequestBuilderError,
    build_standard_execution_request,
)
from app.models import (  # noqa: F401
    Artifact,
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
from app.models.artifacts import Artifact as ArtifactModel
from app.models.artifacts import ArtifactVersion as ArtifactVersionModel
from app.models.artifacts import ArtifactVersionFile as ArtifactVersionFileModel
from app.models.files import File as FileModel
from app.models.files import FileSourceType
from app.models.tasks import Task as TaskModel
from app.models.tasks import TaskStatus
from app.models.tools import Tool as ToolModel
from app.models.tools import ToolStatus
from app.models.tools import ToolVersion as ToolVersionModel
from app.models.users import User as UserModel
from app.models.users import UserRole, UserStatus
from app.tool_packages.schemas import ToolPackageV2Manifest


def minimal_runtime_manifest(slug: str) -> dict:
    return {
        "python": "3.10",
        "executor_support": ["ssh_docker_exec"],
        "selection_policy": "test runtime fixture",
        "artifacts": {
            "primary": {
                "kind": "container",
                "image": f"registry.example/sciminer/{slug}:1.0.0",
                "image_digest": "sha256:test",
            },
            "fallback": {
                "kind": "conda_pack",
                "uri": f"artifacts://model-envs/{slug}/1.0.0/conda-env.tar.gz",
                "sha256": "test",
            },
        },
        "weights": {
            "manifest_uri": f"artifacts://model-weights/{slug}/1.0.0/weights.json",
            "manifest_sha256": "test",
        },
        "cache_policy": {
            "key_fields": ["metadata.slug", "metadata.version"],
            "mutable_host_paths_forbidden": True,
        },
    }


@pytest_asyncio.fixture
async def request_builder_db() -> AsyncSession:
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


def _manifest(*, inputs: list[dict] | None = None) -> ToolPackageV2Manifest:
    slug = "standard-request-tool"
    return ToolPackageV2Manifest.model_validate(
        {
            "api_version": "aidd.sciminer/tool-package.v2",
            "kind": "ToolPackage",
            "metadata": {
                "slug": slug,
                "name": "Standard Request Tool",
                "version": "1.0.0",
            },
            "artifacts": {
                "inputs": inputs
                or [{"name": "protein", "type": "protein_structure@1", "required": True}],
                "outputs": [{"name": "report", "type": "run_report@1"}],
            },
            "parameters_schema": {"type": "object"},
            "runtime": minimal_runtime_manifest(slug),
            "variants": [
                {
                    "name": "cpu",
                    "accelerator": "cpu",
                    "executor_types": ["cli"],
                    "entrypoint": ["/app/runner/entrypoint.sh"],
                }
            ],
        }
    )


async def _seed_task(db: AsyncSession) -> TaskModel:
    user = UserModel(
        email="request-builder@example.com",
        password_hash="hashed",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    tool = ToolModel(
        owner_id="pending",
        name="Standard Request Tool",
        slug="standard-request-tool",
        status=ToolStatus.PUBLISHED.value,
    )
    db.add(user)
    await db.flush()
    tool.owner_id = user.id
    db.add(tool)
    await db.flush()
    version = ToolVersionModel(tool_id=tool.id, version="1.0.0", config={"type": "cli"})
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    task = TaskModel(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        status=TaskStatus.PENDING.value,
    )
    db.add(task)
    await db.flush()
    return task


async def _seed_standard_version(
    db: AsyncSession,
    *,
    tmp_path: Path,
    user_id: str,
    type_ref: str,
    artifact_name: str,
    role_contents: dict[str, bytes],
) -> ArtifactVersionModel:
    standard_type, version_text = type_ref.split("@", 1)
    artifact = ArtifactModel(
        project_id="project-1",
        created_by=user_id,
        artifact_type=standard_type,
        semantic_type=standard_type,
        standard_type=standard_type,
        standard_version=int(version_text),
        name=artifact_name,
    )
    db.add(artifact)
    await db.flush()
    version = ArtifactVersionModel(
        artifact_id=artifact.id,
        created_by=user_id,
        version=1,
        filename=f"{artifact_name}.manifest.json",
        content_type="application/json",
        size_bytes=2,
        sha256="0" * 64,
        storage_key=f"legacy/{artifact_name}.manifest.json",
        validation_status="passed",
        validation_errors=[],
        manifest_json={"type": type_ref, "metadata": {"source": artifact_name}},
        summary_json={},
        metrics_json={},
    )
    db.add(version)
    await db.flush()

    for index, (role, content) in enumerate(role_contents.items()):
        suffix = ".json" if role.endswith("_json") else ".pdb"
        source_path = tmp_path / "storage" / artifact_name / f"{role}{suffix}"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        file_record = FileModel(
            project_id="project-1",
            owner_id=user_id,
            filename=source_path.name,
            content_type="application/json" if suffix == ".json" else "chemical/x-pdb",
            size_bytes=len(content),
            sha256=digest,
            storage_path=str(source_path),
            source_type=FileSourceType.TOOL_OUTPUT.value,
        )
        db.add(file_record)
        await db.flush()
        db.add(
            ArtifactVersionFileModel(
                artifact_version_id=version.id,
                role=role,
                file_id=file_record.id,
                is_primary=index == 0,
                sort_order=index,
            )
        )

    artifact.latest_version_id = version.id
    await db.flush()
    return version


@pytest.mark.asyncio
async def test_builder_stages_files_by_manifest_input_name(
    request_builder_db: AsyncSession,
    tmp_path: Path,
):
    task = await _seed_task(request_builder_db)
    protein_version = await _seed_standard_version(
        request_builder_db,
        tmp_path=tmp_path,
        user_id=str(task.user_id),
        type_ref="protein_structure@1",
        artifact_name="protein",
        role_contents={
            "structure_file": b"ATOM      1  N   ALA A   1\n",
            "metadata_json": b'{"chain_ids":["A"]}',
        },
    )

    request = await build_standard_execution_request(
        request_builder_db,
        task=task,
        tool_package_manifest=_manifest(),
        input_bindings={"protein": protein_version.id},
        parameters={"threshold": 0.5},
        work_dir=tmp_path / "work",
        execution_context=StandardExecutionBuildContext(variant="cpu", accelerator="cpu"),
    )

    assert list(request.inputs) == ["protein"]
    assert request.inputs["protein"].type == "protein_structure@1"
    assert request.inputs["protein"].metadata == {"source": "protein"}
    assert request.inputs["protein"].files["structure_file"].path == (
        "input/protein/structure_file.pdb"
    )
    assert (tmp_path / "work/input/protein/structure_file.pdb").read_bytes().startswith(b"ATOM")
    assert request.parameters == {"threshold": 0.5}
    assert request.task.tool_slug == "standard-request-tool"


@pytest.mark.asyncio
async def test_builder_allows_same_standard_type_bound_to_distinct_input_names(
    request_builder_db: AsyncSession,
    tmp_path: Path,
):
    task = await _seed_task(request_builder_db)
    target = await _seed_standard_version(
        request_builder_db,
        tmp_path=tmp_path,
        user_id=str(task.user_id),
        type_ref="protein_structure@1",
        artifact_name="target",
        role_contents={"structure_file": b"target", "metadata_json": b"{}"},
    )
    reference = await _seed_standard_version(
        request_builder_db,
        tmp_path=tmp_path,
        user_id=str(task.user_id),
        type_ref="protein_structure@1",
        artifact_name="reference",
        role_contents={"structure_file": b"reference", "metadata_json": b"{}"},
    )

    request = await build_standard_execution_request(
        request_builder_db,
        task=task,
        tool_package_manifest=_manifest(
            inputs=[
                {"name": "target", "type": "protein_structure@1", "required": True},
                {"name": "reference", "type": "protein_structure@1", "required": True},
            ]
        ),
        input_bindings={"target": target.id, "reference": reference.id},
        parameters={},
        work_dir=tmp_path / "work",
        execution_context=StandardExecutionBuildContext(variant="cpu", accelerator="cpu"),
    )

    assert set(request.inputs) == {"target", "reference"}
    assert request.inputs["target"].files["structure_file"].path.startswith("input/target/")
    assert request.inputs["reference"].files["structure_file"].path.startswith("input/reference/")
    target_path = tmp_path / "work" / request.inputs["target"].files["structure_file"].path
    assert target_path.read_bytes() == b"target"
    assert (
        tmp_path / "work" / request.inputs["reference"].files["structure_file"].path
    ).read_bytes() == b"reference"


@pytest.mark.asyncio
async def test_builder_rejects_missing_required_input_before_runner_starts(
    request_builder_db: AsyncSession,
    tmp_path: Path,
):
    task = await _seed_task(request_builder_db)

    with pytest.raises(StandardRequestBuilderError, match="Missing required input"):
        await build_standard_execution_request(
            request_builder_db,
            task=task,
            tool_package_manifest=_manifest(),
            input_bindings={},
            parameters={},
            work_dir=tmp_path / "work",
            execution_context=StandardExecutionBuildContext(variant="cpu", accelerator="cpu"),
        )


@pytest.mark.asyncio
async def test_builder_rejects_artifact_version_type_mismatch(
    request_builder_db: AsyncSession,
    tmp_path: Path,
):
    task = await _seed_task(request_builder_db)
    pocket_version = await _seed_standard_version(
        request_builder_db,
        tmp_path=tmp_path,
        user_id=str(task.user_id),
        type_ref="binding_pocket@1",
        artifact_name="pocket",
        role_contents={
            "residue_pocket_pdb": b"residue",
            "atom_pocket_pdb": b"atom",
            "pocket_metadata_json": b"{}",
        },
    )

    with pytest.raises(StandardRequestBuilderError, match="expects protein_structure@1"):
        await build_standard_execution_request(
            request_builder_db,
            task=task,
            tool_package_manifest=_manifest(),
            input_bindings={"protein": pocket_version.id},
            parameters={},
            work_dir=tmp_path / "work",
            execution_context=StandardExecutionBuildContext(variant="cpu", accelerator="cpu"),
        )
