from __future__ import annotations

import hashlib
import json
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
from app.common.exceptions import ValidationException  # noqa: E402
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
from app.tasks.service import create_and_schedule_tool_task, prepare_tool_task_preview  # noqa: E402
from app.tool_packages.schemas import ToolPackageV2Manifest  # noqa: E402


def _minimal_tool_package_v2_manifest(
    *,
    input_name: str = "molecules",
    input_type: str = "molecule_table@1",
    output_name: str = "properties",
    output_type: str = "molecule_table@1",
) -> dict:
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
                {"name": input_name, "type": input_type, "required": True}
            ],
            "outputs": [
                {"name": output_name, "type": output_type, "required": True}
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


async def _create_v2_standard_upload_task(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    input_name: str,
    input_type: str,
    output_type: str = "run_report@1",
    filename: str,
    content: bytes,
    content_type: str,
) -> SimpleNamespace:
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: True)

    owner = UserModel(
        email=f"{input_name}-standard-upload@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(owner)
    await db_session.flush()

    tool = ToolModel(
        owner_id=owner.id,
        name=f"{input_name.title()} Tool",
        slug=f"{input_name}-tool",
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
            "tool_package_manifest": _minimal_tool_package_v2_manifest(
                input_name=input_name,
                input_type=input_type,
                output_name="report",
                output_type=output_type,
            ),
        },
        is_active=True,
        deprecated=False,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    tool.current_version = version

    upload_file = await _create_uploaded_file(
        db_session,
        owner,
        tmp_path,
        filename=filename,
        content_type=content_type,
        content=content,
    )

    task = await create_and_schedule_tool_task(
        db=db_session,
        current_user=owner,
        task_data=TaskCreate(
            tool_id=tool.id,
            standard_input_uploads={input_name: upload_file.id},
        ),
        direct_runner=SimpleNamespace(schedule_task=lambda *, task_id, tool_version_id: None),
    )
    artifact_version = (
        await db_session.execute(select(ArtifactVersionModel))
    ).scalar_one()
    version_files = (await db_session.execute(select(ArtifactVersionFileModel))).scalars().all()
    return SimpleNamespace(
        task=task,
        upload_file=upload_file,
        artifact_version=artifact_version,
        version_files=version_files,
    )


async def _create_uploaded_file(
    db_session: AsyncSession,
    owner: UserModel,
    tmp_path: Path,
    *,
    filename: str,
    content: bytes,
    content_type: str,
) -> FileModel:
    upload_path = tmp_path / filename
    upload_path.write_bytes(content)
    upload_file = FileModel(
        owner_id=owner.id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_path=str(upload_path),
        source_type=FileSourceType.UPLOAD.value,
    )
    db_session.add(upload_file)
    await db_session.flush()
    return upload_file


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
    assert artifact_version.manifest_json["metadata"] == {
        "source": "direct_upload",
        "input_name": "molecules",
        "standard_type": "molecule_table@1",
        "source_filename": "molecules.csv",
        "source_file_id": molecule_file.id,
        "sha256": molecule_file.sha256,
        "source_task_id": molecule_file.id,
        "source_input_ref": "input:molecules",
        "molecule_id_field": "smiles",
        "row_count": 1,
        "column_count": 2,
        "columns": ["smiles", "name"],
    }
    assert version_file.role == "table_file"
    assert version_file.file_id == molecule_file.id
    assert version_file.is_primary is True
    assert {item.role for item in version_files} == {"table_file", "metadata_json"}
    metadata_link = next(item for item in version_files if item.role == "metadata_json")
    metadata_file = await db_session.get(FileModel, metadata_link.file_id)
    assert metadata_file is not None
    assert json.loads(Path(metadata_file.storage_path).read_text(encoding="utf-8")) == (
        artifact_version.manifest_json["metadata"]
    )

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


@pytest.mark.asyncio
async def test_tool_package_v2_standard_uploads_trim_slot_and_file_ids(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: True)

    owner = UserModel(
        email="trim-standard-upload@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(owner)
    await db_session.flush()

    tool = ToolModel(
        owner_id=owner.id,
        name="Trim Standard Upload Tool",
        slug="trim-standard-upload-tool",
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

    molecule_file = await _create_uploaded_file(
        db_session,
        owner,
        tmp_path,
        filename="molecules.csv",
        content_type="text/csv",
        content=b"smiles,name\nCCO,e\n",
    )

    task = await create_and_schedule_tool_task(
        db=db_session,
        current_user=owner,
        task_data=TaskCreate(
            tool_id=tool.id,
            standard_input_uploads={" molecules ": f" {molecule_file.id} "},
        ),
        direct_runner=SimpleNamespace(schedule_task=lambda *, task_id, tool_version_id: None),
    )

    artifact_version = (
        await db_session.execute(select(ArtifactVersionModel))
    ).scalar_one()
    assert task.extra_data["standard_input_uploads"] == {"molecules": molecule_file.id}
    assert task.extra_data["input_bindings"] == {"molecules": artifact_version.id}


@pytest.mark.asyncio
async def test_tool_package_v2_json_molecule_table_upload_generates_table_metadata(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    molecule_content = b'[{"compound_id":"cmp-1","smiles":"CCO"}]'
    context = await _create_v2_standard_upload_task(
        db_session,
        monkeypatch,
        tmp_path,
        input_name="molecules",
        input_type="molecule_table@1",
        output_type="molecule_table@1",
        filename="molecules.json",
        content_type="application/json",
        content=molecule_content,
    )
    molecule_file = context.upload_file

    assert context.artifact_version.manifest_json["metadata"] == {
        "source": "direct_upload",
        "input_name": "molecules",
        "standard_type": "molecule_table@1",
        "source_filename": "molecules.json",
        "source_file_id": molecule_file.id,
        "sha256": molecule_file.sha256,
        "source_task_id": molecule_file.id,
        "source_input_ref": "input:molecules",
        "molecule_id_field": "compound_id",
        "row_count": 1,
        "column_count": 2,
        "columns": ["compound_id", "smiles"],
    }


@pytest.mark.asyncio
async def test_tool_package_v2_protein_upload_generates_core_metadata(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    protein_content = (
        b"ATOM      1  N   MET A   1      11.104  13.207   9.508  1.00 20.00           N\n"
        b"ATOM      2  CA  MET A   1      12.560  13.310   9.620  1.00 20.00           C\n"
    )
    context = await _create_v2_standard_upload_task(
        db_session,
        monkeypatch,
        tmp_path,
        input_name="protein",
        input_type="protein_structure@1",
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        content=protein_content,
    )
    protein_file = context.upload_file
    artifact_version = context.artifact_version

    assert context.task.extra_data["input_bindings"] == {"protein": artifact_version.id}
    assert artifact_version.manifest_json["metadata"] == {
        "source": "direct_upload",
        "input_name": "protein",
        "standard_type": "protein_structure@1",
        "source_filename": "protein.pdb",
        "source_file_id": protein_file.id,
        "sha256": protein_file.sha256,
        "chain_ids": ["A"],
        "residue_count": 1,
        "atom_count": 2,
        "structure_format": "pdb",
        "source_database": "manual",
        "preparation_status": "raw",
    }
    assert {item.role for item in context.version_files} == {"structure_file", "metadata_json"}


@pytest.mark.asyncio
async def test_tool_package_v2_ligand_upload_generates_ligand_id_metadata(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ligand_content = b"example sdf\n$$$$\n"
    context = await _create_v2_standard_upload_task(
        db_session,
        monkeypatch,
        tmp_path,
        input_name="ligand",
        input_type="ligand_structure@1",
        filename="aspirin.sdf",
        content_type="chemical/x-mdl-sdfile",
        content=ligand_content,
    )
    ligand_file = context.upload_file
    artifact_version = context.artifact_version

    assert context.task.extra_data["input_bindings"] == {"ligand": artifact_version.id}
    assert artifact_version.manifest_json["metadata"] == {
        "source": "direct_upload",
        "input_name": "ligand",
        "standard_type": "ligand_structure@1",
        "source_filename": "aspirin.sdf",
        "source_file_id": ligand_file.id,
        "sha256": ligand_file.sha256,
        "ligand_id": "aspirin",
        "source_database": "manual",
    }
    assert {item.role for item in context.version_files} == {"structure_file"}


@pytest.mark.asyncio
async def test_tool_package_v2_standard_upload_rejects_wrong_primary_file_format(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    with pytest.raises(ValidationException, match="标准 Artifact 上传文件格式不匹配"):
        await _create_v2_standard_upload_task(
            db_session,
            monkeypatch,
            tmp_path,
            input_name="protein",
            input_type="protein_structure@1",
            filename="protein.txt",
            content_type="text/plain",
            content=b"not a pdb\n",
        )


@pytest.mark.asyncio
async def test_tool_package_v2_invalid_standard_upload_content_does_not_create_artifact(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    with pytest.raises(ValidationException, match="标准 Artifact 上传内容无效"):
        await _create_v2_standard_upload_task(
            db_session,
            monkeypatch,
            tmp_path,
            input_name="molecules",
            input_type="molecule_table@1",
            output_type="molecule_table@1",
            filename="molecules.csv",
            content_type="text/csv",
            content=b"\n",
        )

    artifacts = (await db_session.execute(select(ArtifactModel))).scalars().all()
    artifact_versions = (await db_session.execute(select(ArtifactVersionModel))).scalars().all()
    tasks = (await db_session.execute(select(Task))).scalars().all()

    assert artifacts == []
    assert artifact_versions == []
    assert tasks == []


@pytest.mark.asyncio
async def test_tool_package_v2_multi_upload_failure_does_not_partially_materialize(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr("app.tasks.service.use_direct_task_execution", lambda: True)

    owner = UserModel(
        email="multi-standard-upload@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(owner)
    await db_session.flush()

    manifest = _minimal_tool_package_v2_manifest(output_type="molecule_table@1")
    manifest["artifacts"]["inputs"].append(
        {"name": "ligand", "type": "ligand_structure@1", "required": True}
    )
    tool = ToolModel(
        owner_id=owner.id,
        name="Multi Input Tool",
        slug="multi-input-tool",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersionModel(
        tool_id=tool.id,
        version="2.0.0",
        config={"type": "ssh_job", "tool_package_manifest": manifest},
        is_active=True,
        deprecated=False,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    tool.current_version = version

    molecule_file = await _create_uploaded_file(
        db_session,
        owner,
        tmp_path,
        filename="molecules.csv",
        content_type="text/csv",
        content=b"smiles,name\nCCO,e\n",
    )
    bad_ligand_file = await _create_uploaded_file(
        db_session,
        owner,
        tmp_path,
        filename="bad-ligand.sdf",
        content_type="chemical/x-mdl-sdfile",
        content=b"not an sdf\n",
    )

    with pytest.raises(ValidationException, match="标准 Artifact 上传内容无效"):
        await create_and_schedule_tool_task(
            db=db_session,
            current_user=owner,
            task_data=TaskCreate(
                tool_id=tool.id,
                standard_input_uploads={
                    "molecules": molecule_file.id,
                    "ligand": bad_ligand_file.id,
                },
            ),
            direct_runner=SimpleNamespace(schedule_task=lambda *, task_id, tool_version_id: None),
        )

    artifacts = (await db_session.execute(select(ArtifactModel))).scalars().all()
    artifact_versions = (await db_session.execute(select(ArtifactVersionModel))).scalars().all()
    tasks = (await db_session.execute(select(Task))).scalars().all()

    assert artifacts == []
    assert artifact_versions == []
    assert tasks == []


@pytest.mark.asyncio
async def test_tool_package_v2_prepare_preview_rejects_invalid_standard_upload_content(
    db_session: AsyncSession,
    tmp_path: Path,
):
    owner = UserModel(
        email="preview-standard-upload@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(owner)
    await db_session.flush()

    tool = ToolModel(
        owner_id=owner.id,
        name="Preview Tool",
        slug="preview-tool",
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
            "tool_package_manifest": _minimal_tool_package_v2_manifest(
                output_type="molecule_table@1"
            ),
        },
        is_active=True,
        deprecated=False,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    tool.current_version = version
    molecule_file = await _create_uploaded_file(
        db_session,
        owner,
        tmp_path,
        filename="molecules.csv",
        content_type="text/csv",
        content=b"\n",
    )

    with pytest.raises(ValidationException, match="标准 Artifact 上传内容无效"):
        await prepare_tool_task_preview(
            db=db_session,
            current_user=owner,
            task_data=TaskCreate(
                tool_id=tool.id,
                standard_input_uploads={"molecules": molecule_file.id},
            ),
        )

    artifacts = (await db_session.execute(select(ArtifactModel))).scalars().all()
    tasks = (await db_session.execute(select(Task))).scalars().all()

    assert artifacts == []
    assert tasks == []
