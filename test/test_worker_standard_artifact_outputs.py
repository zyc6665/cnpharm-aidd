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
) -> FileModel:
    storage_path = tmp_path / "collected" / relative_path
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    file_record = FileModel(
        project_id=task.extra_data["project_id"],
        owner_id=task.user_id,
        filename=relative_path.replace("/", "__"),
        content_type="application/json" if relative_path.endswith(".json") else "chemical/x-pdb",
        size_bytes=len(content),
        sha256=digest,
        storage_path=str(storage_path),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        file_meta={"relative_path": relative_path},
    )
    db.add(file_record)
    await db.flush()
    return file_record


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
    assert task_output.file_ids == file_ids
    assert artifact_count == 1
    assert version_record.manifest_json["type"] == "binding_pocket@1"
    assert {file.role for file in version_record.files} == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }


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
