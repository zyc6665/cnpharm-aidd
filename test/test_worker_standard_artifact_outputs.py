"""Worker standard result.v2 Artifact persistence tests."""

from __future__ import annotations

import hashlib
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
from app.models import (  # noqa: F401
    AgentEvent,
    AgentRun,
    Artifact,
    ArtifactLineage,
    ArtifactVersion,
    ArtifactVersionFile,
    File,
    Organization,
    Project,
    Task,
    TaskInput,
    TaskOutput,
    Tool,
    ToolVersion,
    User,
)
from app.models.artifacts import ArtifactVersion as ArtifactVersionModel
from app.models.artifacts import ArtifactVersionFile as ArtifactVersionFileModel
from app.models.agent import AgentRun as AgentRunModel
from app.models.conversations import AgentEvent as AgentEventModel
from app.models.files import File as FileModel
from app.models.files import FileSourceType
from app.models.projects import Organization as OrganizationModel
from app.models.projects import Project as ProjectModel
from app.models.tasks import Task as TaskModel
from app.models.tasks import TaskInput as TaskInputModel
from app.models.tasks import TaskOutput as TaskOutputModel
from app.models.tasks import TaskStatus
from app.models.tools import Tool as ToolModel
from app.models.tools import ToolStatus
from app.models.tools import ToolVersion as ToolVersionModel
from app.models.users import User as UserModel
from app.models.users import UserRole, UserStatus
from app.worker import tasks as worker_tasks


@pytest_asyncio.fixture
async def worker_standard_db_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


def _v2_manifest() -> dict:
    slug = "worker-standard-tool"
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": slug,
            "name": "Worker Standard Tool",
            "version": "1.0.0",
        },
        "artifacts": {
            "inputs": [{"name": "protein", "type": "protein_structure@1"}],
            "outputs": [
                {"name": "pocket", "type": "binding_pocket@1"},
                {"name": "report", "type": "run_report@1", "required": False},
            ],
        },
        "parameters_schema": {"type": "object"},
        "runtime": {
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
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["cli"],
                "entrypoint": ["/app/runner/entrypoint.sh"],
            }
        ],
    }


async def _seed_task(
    db: AsyncSession,
    *,
    tool_config: dict,
    project_required: bool = True,
) -> tuple[TaskModel, ToolVersionModel]:
    user = UserModel(
        email=f"worker-standard-{hash(str(tool_config))}@example.com",
        password_hash="hashed",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    organization = OrganizationModel(name="Worker Standard Lab", slug=f"lab-{abs(hash(str(tool_config)))}")
    db.add_all([user, organization])
    await db.flush()
    project = ProjectModel(
        organization_id=organization.id,
        created_by=user.id,
        name="Worker standard artifacts",
        status="active",
    )
    db.add(project)
    await db.flush()
    tool = ToolModel(
        owner_id=user.id,
        name="Worker Standard Tool",
        slug=f"worker-standard-tool-{abs(hash(str(tool_config)))}",
        status=ToolStatus.PUBLISHED.value,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersionModel(tool_id=tool.id, version="1.0.0", config=tool_config)
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    task = TaskModel(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        status=TaskStatus.PENDING.value,
        extra_data={"project_id": project.id} if project_required else {},
    )
    db.add(task)
    await db.flush()
    db.add(TaskInputModel(task_id=task.id, params={}, file_ids=[]))
    await db.commit()
    return task, version


async def _seed_output_file(
    db: AsyncSession,
    *,
    task: TaskModel,
    tmp_path: Path,
    relative_path: str,
    content: bytes,
    content_type: str | None = None,
) -> FileModel:
    storage_path = tmp_path / "collected" / relative_path
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    file_record = FileModel(
        project_id=task.extra_data["project_id"],
        owner_id=task.user_id,
        filename=relative_path.replace("/", "__"),
        content_type=content_type
        or ("application/json" if relative_path.endswith(".json") else "chemical/x-pdb"),
        size_bytes=len(content),
        sha256=digest,
        storage_path=str(storage_path),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        file_meta={"relative_path": relative_path},
    )
    db.add(file_record)
    await db.flush()
    return file_record


def _molecule_table_manifest(
    *,
    slug: str,
    output_name: str,
) -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {"slug": slug, "name": slug, "version": "1.0.0"},
        "artifacts": {
            "inputs": [{"name": "molecules", "type": "molecule_table@1"}],
            "outputs": [
                {"name": output_name, "type": "molecule_table@1", "cardinality": "one"},
                {"name": "report", "type": "run_report@1", "required": False},
            ],
        },
        "parameters_schema": {"type": "object"},
        "runtime": {
            "python": "3.10",
            "executor_support": ["ssh_docker_exec"],
            "selection_policy": "test runtime fixture",
            "artifacts": {
                "primary": {"kind": "container", "image": "example/image", "image_digest": "sha256:test"},
                "fallback": {"kind": "conda_pack", "uri": "artifacts://env", "sha256": "test"},
            },
            "weights": {"manifest_uri": "artifacts://weights", "manifest_sha256": "test"},
            "cache_policy": {"key_fields": ["metadata.slug"], "mutable_host_paths_forbidden": True},
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["cli"],
                "entrypoint": ["/app/run.sh"],
            }
        ],
    }


async def _disable_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    async def noop(*args, **kwargs):
        return None

    async def passthrough(_db, _task, _tool_version, output_result):
        return output_result

    monkeypatch.setattr(worker_tasks, "notify_task_status", noop)
    monkeypatch.setattr(worker_tasks, "notify_task_log", noop)
    monkeypatch.setattr(worker_tasks, "notify_task_progress", noop)
    monkeypatch.setattr(worker_tasks, "notify_task_complete", noop)
    monkeypatch.setattr(worker_tasks, "notify_task_error", noop)
    monkeypatch.setattr(
        "app.tasks.molecule_scoring.append_molecule_scoring_artifacts",
        passthrough,
    )


@pytest.mark.asyncio
async def test_worker_persists_standard_result_v2_as_artifact_versions(
    worker_standard_db_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    await _disable_notifications(monkeypatch)
    monkeypatch.setattr("app.database.session.async_session_factory", worker_standard_db_factory)

    async with worker_standard_db_factory() as db:
        task, version = await _seed_task(
            db,
            tool_config={"type": "python_script", "tool_package_manifest": _v2_manifest()},
        )
        residue = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/pocket/residue.pdb",
            content=b"residue",
        )
        atom = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/pocket/atom.pdb",
            content=b"atom",
        )
        metadata = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/pocket/metadata.json",
            content=b"{}",
        )
        file_ids = [residue.id, atom.id, metadata.id]
        await db.commit()
        result_payload = {
            "result_version": "aidd.sciminer/result.v2",
            "artifacts": {
                "pocket": {
                    "name": "Top pocket",
                    "type": "binding_pocket@1",
                    "files": {
                        "residue_pocket_pdb": {
                            "path": "artifacts/pocket/residue.pdb",
                            "sha256": residue.sha256,
                        },
                        "atom_pocket_pdb": {
                            "path": "artifacts/pocket/atom.pdb",
                            "sha256": atom.sha256,
                        },
                        "pocket_metadata_json": {
                            "path": "artifacts/pocket/metadata.json",
                            "sha256": metadata.sha256,
                        },
                    },
                }
            },
        }
        task_id = task.id
        version_id = version.id

    async def fake_execute(self):
        return {"success": True, "result": result_payload, "output_file_ids": file_ids}

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    result = await worker_tasks._execute_tool_task_impl(str(task_id), str(version_id))

    async with worker_standard_db_factory() as db:
        task_record = (
            await db.execute(select(TaskModel).where(TaskModel.id == task_id))
        ).scalar_one()
        task_output = (
            await db.execute(select(TaskOutputModel).where(TaskOutputModel.task_id == task_id))
        ).scalar_one()
        artifact_count = await db.scalar(select(func.count(ArtifactVersionModel.id)))
        artifact_version_id = task_output.result["standard_artifacts"][
            "artifact_version_ids_by_ref"
        ]["pocket"]
        version_record = (
            await db.execute(
                select(ArtifactVersionModel)
                .options(selectinload(ArtifactVersionModel.files))
                .where(ArtifactVersionModel.id == artifact_version_id)
            )
        ).scalar_one()

    assert result["result"]["result_version"] == "aidd.sciminer/result.v2"
    assert task_record.progress == 100.0
    assert task_record.progress_message == "任务执行成功"
    assert task_output.file_ids == file_ids
    assert artifact_count == 1
    assert version_record.manifest_json["type"] == "binding_pocket@1"
    assert {file.role for file in version_record.files} == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }


@pytest.mark.asyncio
async def test_worker_persists_remote_tool_v1_standard_outputs(
    worker_standard_db_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    await _disable_notifications(monkeypatch)
    monkeypatch.setattr("app.database.session.async_session_factory", worker_standard_db_factory)

    async with worker_standard_db_factory() as db:
        task, version = await _seed_task(
            db,
            tool_config={
                "type": "remote_api",
                "mode": "remote_tool_v1",
                "artifacts": {
                    "outputs": [
                        {"name": "pocket", "type": "binding_pocket@1", "cardinality": "one"},
                    ]
                },
            },
        )
        residue = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/pocket/residue.pdb",
            content=b"residue",
        )
        atom = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/pocket/atom.pdb",
            content=b"atom",
        )
        metadata = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/pocket/metadata.json",
            content=b"{}",
        )
        file_ids = [residue.id, atom.id, metadata.id]
        result_payload = {
            "result_version": "aidd.sciminer/result.v2",
            "artifacts": {
                "pocket": {
                    "name": "Top pocket",
                    "type": "binding_pocket@1",
                    "files": {
                        "residue_pocket_pdb": {
                            "path": "artifacts/pocket/residue.pdb",
                            "sha256": residue.sha256,
                        },
                        "atom_pocket_pdb": {
                            "path": "artifacts/pocket/atom.pdb",
                            "sha256": atom.sha256,
                        },
                        "pocket_metadata_json": {
                            "path": "artifacts/pocket/metadata.json",
                            "sha256": metadata.sha256,
                        },
                    },
                }
            },
        }
        task_id = task.id
        version_id = version.id
        await db.commit()

    async def fake_execute(self):
        return {"success": True, "result": result_payload, "output_file_ids": file_ids}

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    await worker_tasks._execute_tool_task_impl(str(task_id), str(version_id))

    async with worker_standard_db_factory() as db:
        task_output = (
            await db.execute(select(TaskOutputModel).where(TaskOutputModel.task_id == task_id))
        ).scalar_one()
        artifact_count = await db.scalar(select(func.count(ArtifactVersionModel.id)))

    assert artifact_count == 1
    assert task_output.result["standard_artifacts"]["artifact_version_ids_by_ref"]["pocket"]


@pytest.mark.asyncio
async def test_worker_standardizes_legacy_lvpocket_outputs(
    worker_standard_db_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    await _disable_notifications(monkeypatch)
    monkeypatch.setattr("app.database.session.async_session_factory", worker_standard_db_factory)

    async with worker_standard_db_factory() as db:
        task, version = await _seed_task(
            db,
            tool_config={
                "type": "ssh_job",
                "artifacts": {
                    "outputs": [
                        {"name": "pocket", "type": "binding_pocket@1", "cardinality": "one"},
                    ]
                },
            },
        )
        residue = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/lv_results/input/protein_pocket_residues.pdb",
            content=b"residue",
        )
        atom = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/lv_results/input/pocket0.pdb",
            content=b"atom",
        )
        metadata = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/prediction.json",
            content=b"{}",
        )
        file_ids = [residue.id, atom.id, metadata.id]
        task_id = task.id
        version_id = version.id
        await db.commit()

    async def fake_execute(self):
        return {
            "success": True,
            "result": {
                "success": True,
                "message": "LVpocket pocket prediction completed",
                "outputs": {
                    "pocket_count": 1,
                    "pockets": [
                        {"id": "pocket0", "pdb": "artifacts/lv_results/input/pocket0.pdb"}
                    ],
                    "protein_pocket_residues": {
                        "path": "artifacts/lv_results/input/protein_pocket_residues.pdb",
                        "residue_count": 32,
                        "atom_count": 259,
                    },
                },
                "artifacts": [
                    {"name": "prediction.json", "path": "artifacts/prediction.json"},
                ],
            },
            "output_file_ids": file_ids,
        }

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    await worker_tasks._execute_tool_task_impl(str(task_id), str(version_id))

    async with worker_standard_db_factory() as db:
        task_output = (
            await db.execute(select(TaskOutputModel).where(TaskOutputModel.task_id == task_id))
        ).scalar_one()
        artifact_count = await db.scalar(select(func.count(ArtifactVersionModel.id)))
        artifact_version_id = task_output.result["standard_artifacts"][
            "artifact_version_ids_by_ref"
        ]["pocket"]
        version_record = (
            await db.execute(
                select(ArtifactVersionModel)
                .options(selectinload(ArtifactVersionModel.files))
                .where(ArtifactVersionModel.id == artifact_version_id)
            )
        ).scalar_one()

    assert artifact_count == 1
    assert version_record.manifest_json["type"] == "binding_pocket@1"
    assert {file.role for file in version_record.files} == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }


@pytest.mark.asyncio
async def test_worker_standardizes_legacy_molp_pc_outputs(
    worker_standard_db_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    await _disable_notifications(monkeypatch)
    monkeypatch.setattr("app.database.session.async_session_factory", worker_standard_db_factory)

    async with worker_standard_db_factory() as db:
        task, version = await _seed_task(
            db,
            tool_config={
                "type": "ssh_job",
                "tool_package_manifest": _molecule_table_manifest(
                    slug="molp-pc-property-prediction",
                    output_name="properties",
                ),
            },
        )
        prediction = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/cb_data_result.csv",
            content=b"SMILES,F20\nCCO,0.9\n",
            content_type="text/csv",
        )
        file_ids = [prediction.id]
        task_id = task.id
        version_id = version.id
        await db.commit()

    async def fake_execute(self):
        return {
            "success": True,
            "result": {
                "success": True,
                "message": "MolP-PC property prediction completed",
                "outputs": {
                    "task_id": str(task_id),
                    "input_rows": 1,
                    "predicted_rows": 1,
                    "prediction_file": "artifacts/cb_data_result.csv",
                    "device": "cpu",
                },
                "artifacts": [
                    {"name": "cb_data_result.csv", "path": "artifacts/cb_data_result.csv"},
                ],
            },
            "output_file_ids": file_ids,
        }

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    await worker_tasks._execute_tool_task_impl(str(task_id), str(version_id))

    async with worker_standard_db_factory() as db:
        task_output = (
            await db.execute(select(TaskOutputModel).where(TaskOutputModel.task_id == task_id))
        ).scalar_one()
        artifact_version_id = task_output.result["standard_artifacts"][
            "artifact_version_ids_by_ref"
        ]["properties"]
        version_record = (
            await db.execute(
                select(ArtifactVersionModel)
                .options(selectinload(ArtifactVersionModel.files))
                .where(ArtifactVersionModel.id == artifact_version_id)
            )
        ).scalar_one()

    assert version_record.manifest_json["type"] == "molecule_table@1"
    assert {file.role for file in version_record.files} == {"table_file", "metadata_json"}
    assert len(task_output.file_ids) == 2


@pytest.mark.asyncio
async def test_worker_standardizes_legacy_msign_outputs(
    worker_standard_db_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    await _disable_notifications(monkeypatch)
    monkeypatch.setattr("app.database.session.async_session_factory", worker_standard_db_factory)

    async with worker_standard_db_factory() as db:
        task, version = await _seed_task(
            db,
            tool_config={
                "type": "ssh_job",
                "tool_package_manifest": _molecule_table_manifest(
                    slug="msign-affinity-prediction",
                    output_name="affinity",
                ),
            },
        )
        prediction_file = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/prediction.json",
            content=b"{}",
            content_type="application/json",
        )
        file_ids = [prediction_file.id]
        task_id = task.id
        version_id = version.id
        await db.commit()

    async def fake_execute(self):
        return {
            "success": True,
            "result": {
                "success": True,
                "message": "MSIGN affinity prediction completed",
                "outputs": {
                    "complex_id": "1A2B_generated_001",
                    "prediction": {
                        "predicted_affinity": 8.19,
                        "predicted_ligand_to_pocket": 11.15,
                        "predicted_pocket_to_ligand": 5.22,
                        "scale": "pKa/pKi-like binding affinity score",
                    },
                    "model_name": "full_finetune_model.pt",
                    "distance_angstrom": 5.0,
                    "device": "cpu",
                },
                "artifacts": [
                    {"name": "prediction.json", "path": "artifacts/prediction.json"},
                ],
            },
            "output_file_ids": file_ids,
        }

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    await worker_tasks._execute_tool_task_impl(str(task_id), str(version_id))

    async with worker_standard_db_factory() as db:
        task_output = (
            await db.execute(select(TaskOutputModel).where(TaskOutputModel.task_id == task_id))
        ).scalar_one()
        artifact_version_id = task_output.result["standard_artifacts"][
            "artifact_version_ids_by_ref"
        ]["affinity"]
        version_record = (
            await db.execute(
                select(ArtifactVersionModel)
                .options(selectinload(ArtifactVersionModel.files))
                .where(ArtifactVersionModel.id == artifact_version_id)
            )
        ).scalar_one()

    assert version_record.manifest_json["type"] == "molecule_table@1"
    assert {file.role for file in version_record.files} == {"table_file", "metadata_json"}
    assert len(task_output.file_ids) == 3


@pytest.mark.asyncio
async def test_worker_persists_builtin_standard_outputs(
    worker_standard_db_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    await _disable_notifications(monkeypatch)
    monkeypatch.setattr("app.database.session.async_session_factory", worker_standard_db_factory)

    async with worker_standard_db_factory() as db:
        task, version = await _seed_task(
            db,
            tool_config={
                "type": "builtin",
                "builtin_slug": "builtin-protein-preparation",
                "artifacts": {
                    "outputs": [
                        {"name": "pocket", "type": "binding_pocket@1", "cardinality": "one"},
                    ]
                },
            },
        )
        residue = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/pocket/residue.pdb",
            content=b"residue",
        )
        atom = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/pocket/atom.pdb",
            content=b"atom",
        )
        metadata = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="artifacts/pocket/metadata.json",
            content=b"{}",
        )
        file_ids = [residue.id, atom.id, metadata.id]
        result_payload = {
            "result_version": "aidd.sciminer/result.v2",
            "artifacts": {
                "pocket": {
                    "name": "Top pocket",
                    "type": "binding_pocket@1",
                    "files": {
                        "residue_pocket_pdb": {
                            "path": "artifacts/pocket/residue.pdb",
                            "sha256": residue.sha256,
                        },
                        "atom_pocket_pdb": {
                            "path": "artifacts/pocket/atom.pdb",
                            "sha256": atom.sha256,
                        },
                        "pocket_metadata_json": {
                            "path": "artifacts/pocket/metadata.json",
                            "sha256": metadata.sha256,
                        },
                    },
                }
            },
        }
        task_id = task.id
        version_id = version.id
        await db.commit()

    async def fake_execute(self):
        return {"success": True, "result": result_payload, "output_file_ids": file_ids}

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    await worker_tasks._execute_tool_task_impl(str(task_id), str(version_id))

    async with worker_standard_db_factory() as db:
        task_output = (
            await db.execute(select(TaskOutputModel).where(TaskOutputModel.task_id == task_id))
        ).scalar_one()
        artifact_count = await db.scalar(select(func.count(ArtifactVersionModel.id)))

    assert artifact_count == 1
    assert task_output.result["standard_artifacts"]["artifact_version_ids_by_ref"]["pocket"]


@pytest.mark.asyncio
async def test_worker_keeps_legacy_outputs_when_no_v2_manifest(
    worker_standard_db_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    await _disable_notifications(monkeypatch)
    monkeypatch.setattr("app.database.session.async_session_factory", worker_standard_db_factory)

    async with worker_standard_db_factory() as db:
        task, version = await _seed_task(db, tool_config={"type": "python_script"})
        output_file = await _seed_output_file(
            db,
            task=task,
            tmp_path=tmp_path,
            relative_path="legacy/output.txt",
            content=b"legacy",
        )
        task_id = task.id
        version_id = version.id
        file_id = output_file.id
        await db.commit()

    async def fake_execute(self):
        return {"success": True, "result": {"ok": True}, "output_file_ids": [file_id]}

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    await worker_tasks._execute_tool_task_impl(str(task_id), str(version_id))

    async with worker_standard_db_factory() as db:
        task_output = (
            await db.execute(select(TaskOutputModel).where(TaskOutputModel.task_id == task_id))
        ).scalar_one()
        artifact_count = await db.scalar(select(func.count(ArtifactVersionFileModel.id)))

    assert task_output.file_ids == [file_id]
    assert "standard_artifacts" not in task_output.result
    assert artifact_count == 0


@pytest.mark.asyncio
async def test_worker_records_remote_tool_smoke_success_and_auto_publishes(
    worker_standard_db_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    await _disable_notifications(monkeypatch)
    monkeypatch.setattr("app.database.session.async_session_factory", worker_standard_db_factory)
    manifest_hash = "b" * 64

    async with worker_standard_db_factory() as db:
        task, version = await _seed_task(
            db,
            tool_config={
                "type": "remote_api",
                "mode": "remote_tool_v1",
                "manifest_sha256": manifest_hash,
                "pending_publish_on_smoke_success": True,
            },
        )
        task.extra_data = {
            **(task.extra_data or {}),
            "smoke_test": True,
            "smoke_test_type": "remote_tool_v1",
            "publish_on_success": True,
            "manifest_sha256": manifest_hash,
            "tool_version_id": str(version.id),
            "example_name": "smoke-default",
        }
        db.add(task)
        await db.commit()
        task_id = task.id
        version_id = version.id
        tool_id = task.tool_id

    async def fake_execute(self):
        return {"success": True, "remote_run_id": "run-1", "result": {"ok": True}}

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    await worker_tasks._execute_tool_task_impl(str(task_id), str(version_id))

    async with worker_standard_db_factory() as db:
        refreshed_version = (
            await db.execute(select(ToolVersionModel).where(ToolVersionModel.id == version_id))
        ).scalar_one()
        refreshed_tool = (
            await db.execute(select(ToolModel).where(ToolModel.id == tool_id))
        ).scalar_one()

    assert refreshed_version.config["last_smoke_test"]["status"] == "success"
    assert refreshed_version.config["last_smoke_test"]["manifest_sha256"] == manifest_hash
    assert refreshed_version.config["last_smoke_test"]["task_id"] == task_id
    assert "pending_publish_on_smoke_success" not in refreshed_version.config
    assert refreshed_tool.status == ToolStatus.PUBLISHED.value


@pytest.mark.asyncio
async def test_worker_records_remote_tool_smoke_failure(
    worker_standard_db_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    await _disable_notifications(monkeypatch)
    monkeypatch.setattr("app.database.session.async_session_factory", worker_standard_db_factory)
    manifest_hash = "c" * 64

    async with worker_standard_db_factory() as db:
        task, version = await _seed_task(
            db,
            tool_config={
                "type": "remote_api",
                "mode": "remote_tool_v1",
                "manifest_sha256": manifest_hash,
                "pending_publish_on_smoke_success": True,
            },
        )
        task.extra_data = {
            **(task.extra_data or {}),
            "smoke_test": True,
            "smoke_test_type": "remote_tool_v1",
            "publish_on_success": True,
            "manifest_sha256": manifest_hash,
            "tool_version_id": str(version.id),
            "example_name": "smoke-default",
        }
        db.add(task)
        await db.commit()
        task_id = task.id
        version_id = version.id
        tool_id = task.tool_id

    async def fake_execute(self):
        raise RuntimeError("remote run failed")

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    with pytest.raises(RuntimeError, match="remote run failed"):
        await worker_tasks._execute_tool_task_impl(str(task_id), str(version_id))

    async with worker_standard_db_factory() as db:
        refreshed_version = (
            await db.execute(select(ToolVersionModel).where(ToolVersionModel.id == version_id))
        ).scalar_one()
        refreshed_tool = (
            await db.execute(select(ToolModel).where(ToolModel.id == tool_id))
        ).scalar_one()

    assert refreshed_version.config["last_smoke_test"]["status"] == "failure"
    assert refreshed_version.config["last_smoke_test"]["manifest_sha256"] == manifest_hash
    assert refreshed_version.config["last_smoke_test"]["task_id"] == task_id
    assert refreshed_version.config["last_smoke_test"]["error"] == "remote run failed"
    assert refreshed_tool.status == ToolStatus.PUBLISHED.value


@pytest.mark.asyncio
async def test_worker_publishes_agent_events_for_agent_task_progress(
    worker_standard_db_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    await _disable_notifications(monkeypatch)
    monkeypatch.setattr("app.database.session.async_session_factory", worker_standard_db_factory)

    async with worker_standard_db_factory() as db:
        task, version = await _seed_task(db, tool_config={"type": "python_script"})
        run = AgentRunModel(
            project_id=task.extra_data["project_id"],
            user_id=task.user_id,
            message="Find pockets",
            intent="pocket_detection",
            status="queued",
            input_type="protein_structure",
        )
        db.add(run)
        await db.flush()
        task.extra_data = {
            **(task.extra_data or {}),
            "agent_run_id": run.id,
            "plan_version_id": "plan-1",
        }
        task_id = task.id
        version_id = version.id
        run_id = run.id
        await db.commit()

    async def fake_execute(self):
        await self.progress_callback(15.0, "远端模型进程已启动")
        await self.progress_callback(55.0, "远端运行中：sampling")
        return {"success": True, "result": {"ok": True}, "output_file_ids": []}

    monkeypatch.setattr("app.tasks.executor.TaskExecutor.execute", fake_execute)

    await worker_tasks._execute_tool_task_impl(str(task_id), str(version_id))

    async with worker_standard_db_factory() as db:
        run_record = await db.get(AgentRunModel, run_id)
        events = (
            (
                await db.execute(
                    select(AgentEventModel)
                    .where(AgentEventModel.agent_run_id == run_id)
                    .order_by(AgentEventModel.sequence)
                )
            )
            .scalars()
            .all()
        )

    assert run_record.status == "success"
    assert [event.event_type for event in events] == [
        "execution_started",
        "execution_progress",
        "execution_progress",
        "execution_completed",
    ]
    assert [event.payload["task_id"] for event in events] == [task_id] * 4
    assert events[1].payload["progress"] == 15.0
    assert events[1].payload["message"] == "远端模型进程已启动"
    assert events[-1].payload["status"] == "success"
