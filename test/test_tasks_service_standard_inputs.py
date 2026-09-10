from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.execution.request_builder import (  # noqa: E402
    StandardExecutionBuildContext,
    build_standard_execution_request,
)
from app.models import (  # noqa: E402,F401
    Artifact,
    ArtifactVersion,
    ArtifactVersionFile,
    File,
    Organization,
    Project,
    Task,
    TaskInput,
    Tool,
    ToolVersion,
    User,
)
from app.models.artifacts import Artifact as ArtifactModel  # noqa: E402
from app.models.artifacts import ArtifactVersion as ArtifactVersionModel  # noqa: E402
from app.models.artifacts import ArtifactVersionFile as ArtifactVersionFileModel  # noqa: E402
from app.models.files import File as FileModel  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.tasks import TaskInput as TaskInputModel  # noqa: E402
from app.models.tools import Tool as ToolModel  # noqa: E402
from app.models.tools import ToolProviderType, ToolStatus  # noqa: E402
from app.models.tools import ToolVersion as ToolVersionModel  # noqa: E402
from app.models.users import User as UserModel  # noqa: E402
from app.models.users import UserRole, UserStatus  # noqa: E402
from app.schemas.tasks import TaskCreate, TaskInputSchema  # noqa: E402
from app.tasks.service import create_and_schedule_tool_task  # noqa: E402
from app.tool_packages.schemas import ToolPackageV2Manifest  # noqa: E402


def _minimal_tool_package_v2_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "molp-pc",
            "name": "MolP-PC",
            "version": "2.0.0",
            "description": "Predict molecule properties",
        },
        "artifacts": {
            "inputs": [
                {"name": "molecules", "type": "molecule_table@1", "required": True}
            ],
            "outputs": [
                {"name": "properties", "type": "molecule_table@1", "required": True}
            ],
        },
        "parameters_schema": {"type": "object", "properties": {}, "required": []},
        "runtime": {
            "python": "3.10",
            "executor_support": ["ssh_docker_exec"],
            "selection_policy": "test runtime fixture",
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": "registry.example/sciminer/molp-pc:2.0.0",
                    "image_digest": "sha256:test",
                },
                "fallback": {
                    "kind": "conda_pack",
                    "uri": "artifacts://model-envs/molp-pc/2.0.0/conda-env.tar.gz",
                    "sha256": "test",
                },
            },
            "weights": {
                "manifest_uri": "artifacts://model-weights/molp-pc/2.0.0/weights.json",
                "manifest_sha256": "test",
            },
            "cache_policy": {
                "key_fields": ["metadata.slug", "metadata.version"],
                "mutable_host_paths_forbidden": True,
            },
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["cli"],
                "entrypoint": ["python", "run.py"],
            }
        ],
    }


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_task_create_accepts_standard_input_uploads():
    payload = TaskCreate(
        tool_id="tool-1",
        standard_input_uploads={"protein": "file-1"},
    )

    assert payload.standard_input_uploads == {"protein": "file-1"}


def test_task_input_schema_accepts_standard_input_uploads():
    payload = TaskInputSchema(
        params={},
        standard_input_uploads={"ligand": "file-2"},
    )

    assert payload.standard_input_uploads == {"ligand": "file-2"}


@pytest.mark.asyncio
async def test_create_task_projects_standard_uploads_to_builtin_inputs(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: True)

    owner = UserModel(
        email="standard-upload@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(owner)
    await db_session.flush()

    tool = ToolModel(
        owner_id=owner.id,
        name="Protein Preparation",
        slug="builtin-protein-preparation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersionModel(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "builtin",
            "builtin_slug": "builtin-protein-preparation",
            "artifacts": {
                "inputs": [
                    {"name": "protein", "type": "protein_structure@1", "required": True}
                ],
                "outputs": [],
            },
        },
        is_active=True,
        deprecated=False,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    tool.current_version = version

    protein_file = FileModel(
        owner_id=owner.id,
        filename="uploaded-protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=12,
        sha256=hashlib.sha256(b"ATOM upload\n").hexdigest(),
        storage_path="/tmp/uploaded-protein.pdb",
        source_type=FileSourceType.UPLOAD.value,
    )
    db_session.add(protein_file)
    await db_session.flush()

    scheduled: list[tuple[str, str]] = []
    direct_runner = SimpleNamespace(
        schedule_task=lambda *, task_id, tool_version_id: scheduled.append(
            (task_id, tool_version_id)
        )
    )

    task = await create_and_schedule_tool_task(
        db=db_session,
        current_user=owner,
        task_data=TaskCreate(
            tool_id=tool.id,
            standard_input_uploads={"protein": protein_file.id},
        ),
        direct_runner=direct_runner,
    )

    task_input = (
        await db_session.execute(
            select(TaskInputModel).where(TaskInputModel.task_id == task.id)
        )
    ).scalar_one()

    assert scheduled == [(str(task.id), str(version.id))]
    assert task.extra_data["standard_input_uploads"] == {"protein": protein_file.id}
    assert task_input.file_ids == [protein_file.id]
    assert task_input.params["builtin_inputs"] == {"protein_structure@1": protein_file.id}


@pytest.mark.asyncio
async def test_tool_package_v2_standard_uploads_materialize_to_input_bindings(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: True)

    owner = UserModel(
        email="tool-package-standard-upload@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(owner)
    await db_session.flush()

    tool = ToolModel(
        owner_id=owner.id,
        name="MolP-PC",
        slug="molp-pc",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersionModel(
        tool_id=tool.id,
        version="2.0.0",
        config={
            "type": "ssh_job",
            "tool_package_manifest": _minimal_tool_package_v2_manifest(),
        },
        is_active=True,
        deprecated=False,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    tool.current_version = version

    molecule_content = b"smiles,name\nCCO,e\n"
    molecule_path = tmp_path / "molecules.csv"
    molecule_path.write_bytes(molecule_content)
    molecule_file = FileModel(
        owner_id=owner.id,
        filename="molecules.csv",
        content_type="text/csv",
        size_bytes=len(molecule_content),
        sha256=hashlib.sha256(molecule_content).hexdigest(),
        storage_path=str(molecule_path),
        source_type=FileSourceType.UPLOAD.value,
    )
    db_session.add(molecule_file)
    await db_session.flush()

    scheduled: list[tuple[str, str]] = []
    direct_runner = SimpleNamespace(
        schedule_task=lambda *, task_id, tool_version_id: scheduled.append(
            (task_id, tool_version_id)
        )
    )

    task = await create_and_schedule_tool_task(
        db=db_session,
        current_user=owner,
        task_data=TaskCreate(
            tool_id=tool.id,
            standard_input_uploads={"molecules": molecule_file.id},
        ),
        direct_runner=direct_runner,
    )

    task_input = (
        await db_session.execute(
            select(TaskInputModel).where(TaskInputModel.task_id == task.id)
        )
    ).scalar_one()
    artifact_version = (
        await db_session.execute(select(ArtifactVersionModel))
    ).scalar_one()
    artifact = await db_session.get(ArtifactModel, artifact_version.artifact_id)
    version_file = (
        await db_session.execute(
            select(ArtifactVersionFileModel).where(ArtifactVersionFileModel.role == "table_file")
        )
    ).scalar_one()
    version_files = (await db_session.execute(select(ArtifactVersionFileModel))).scalars().all()

    assert scheduled == [(str(task.id), str(version.id))]
    assert task.extra_data["project_id"]
    assert task.extra_data["standard_input_uploads"] == {"molecules": molecule_file.id}
    assert task.extra_data["input_bindings"] == {"molecules": artifact_version.id}
    assert task_input.file_ids == []
    assert artifact is not None
    assert artifact.project_id == task.extra_data["project_id"]
    assert artifact.standard_type == "molecule_table"
    assert artifact.standard_version == 1
    assert artifact.latest_version_id == artifact_version.id
    assert artifact_version.manifest_json["type"] == "molecule_table@1"
    assert artifact_version.manifest_json["input_name"] == "molecules"
    assert version_file.role == "table_file"
    assert version_file.file_id == molecule_file.id
    assert version_file.is_primary is True
    assert {item.role for item in version_files} == {"table_file", "metadata_json"}

    request = await build_standard_execution_request(
        db_session,
        task=task,
        tool_package_manifest=ToolPackageV2Manifest.model_validate(
            _minimal_tool_package_v2_manifest()
        ),
        input_bindings=task.extra_data["input_bindings"],
        parameters={},
        work_dir=tmp_path / "run",
        execution_context=StandardExecutionBuildContext(variant="cpu", accelerator="cpu"),
    )

    assert set(request.inputs["molecules"].files) == {"table_file", "metadata_json"}
