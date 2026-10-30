"""Workflow persistence API tests."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import get_current_user  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile  # noqa: E402
from app.models.files import File as FileModel, FileSourceType  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.tasks import Task, TaskInput, TaskOutput, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.models.workflows import WorkflowDefinition, WorkflowRun  # noqa: E402


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
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


async def create_user(db_session: AsyncSession, *, email: str) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        display_name=email.split("@")[0],
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    return await create_user(db_session, email="owner@example.com")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await create_user(db_session, email="other@example.com")


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    owner: User,
    other_user: User,
):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == "Bearer owner-token":
            return owner
        if authorization == "Bearer other-token":
            return other_user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def pocket_tool(db_session: AsyncSession, owner: User) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name="LVpocket",
        slug="lvpocket-pocket-prediction",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "ssh_job"},
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest_asyncio.fixture
async def generation_tool(db_session: AsyncSession, owner: User) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name="STD-Diff",
        slug="gcdm-pocket-generation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "ssh_job"},
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


def standard_tool_manifest(
    *,
    slug: str,
    inputs: list[dict],
    outputs: list[dict],
) -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package",
        "kind": "ToolPackage",
        "metadata": {
            "slug": slug,
            "name": slug.replace("-", " ").title(),
            "version": "1.0.0",
        },
        "artifacts": {"inputs": inputs, "outputs": outputs},
        "parameters_schema": {"type": "object"},
        "exposure": {"agent": True, "workflow": True, "direct_run": True},
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


async def create_standard_tool(
    db_session: AsyncSession,
    owner: User,
    *,
    slug: str,
    inputs: list[dict],
    outputs: list[dict],
) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name=slug.replace("-", " ").title(),
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "ssh_job",
            "tool_package_manifest": standard_tool_manifest(
                slug=slug,
                inputs=inputs,
                outputs=outputs,
            ),
        },
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest_asyncio.fixture
async def protein_file(db_session: AsyncSession, owner: User) -> FileModel:
    file_record = FileModel(
        owner_id=owner.id,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"protein").hexdigest(),
        source_type=FileSourceType.UPLOAD.value,
        storage_path="/tmp/protein.pdb",
        is_public=False,
    )
    db_session.add(file_record)
    await db_session.commit()
    await db_session.refresh(file_record)
    return file_record


async def create_protein_file_for_user(
    db_session: AsyncSession,
    user: User,
    *,
    filename: str = "protein.pdb",
) -> FileModel:
    file_record = FileModel(
        owner_id=user.id,
        filename=filename,
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(f"{user.id}:{filename}".encode()).hexdigest(),
        source_type=FileSourceType.UPLOAD.value,
        storage_path=f"/tmp/{filename}",
        is_public=False,
    )
    db_session.add(file_record)
    await db_session.commit()
    await db_session.refresh(file_record)
    return file_record


async def create_binding_pocket_version(
    db_session: AsyncSession,
    owner: User,
    *,
    project_id: str,
    files: list[FileModel],
) -> ArtifactVersion:
    artifact = Artifact(
        project_id=project_id,
        created_by=owner.id,
        artifact_type="binding_pocket",
        semantic_type="binding_pocket",
        standard_type="binding_pocket",
        standard_version=1,
        name="binding_pocket@1",
    )
    db_session.add(artifact)
    await db_session.flush()

    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename="binding_pocket.manifest.json",
        content_type="application/json",
        size_bytes=2,
        sha256="0" * 64,
        storage_key="test/binding_pocket.manifest.json",
        status="available",
        validation_status="passed",
        validation_errors=[],
        manifest_json={"type": "binding_pocket@1"},
        summary_json={},
        metrics_json={},
    )
    db_session.add(version)
    await db_session.flush()

    for index, (role, file_record) in enumerate(
        zip(
            ("residue_pocket_pdb", "atom_pocket_pdb", "pocket_metadata_json"),
            files,
            strict=False,
        )
    ):
        db_session.add(
            ArtifactVersionFile(
                artifact_version_id=version.id,
                role=role,
                file_id=file_record.id,
                is_primary=index == 0,
                sort_order=index,
            )
        )
    artifact.latest_version_id = version.id
    await db_session.flush()
    return version


def template_definition(tool: Tool) -> dict:
    return {
        "nodes": [
            {
                "id": "protein_input",
                "kind": "input",
                "semantic_type": "protein_pdb",
            },
            {
                "id": "pocket_prediction",
                "kind": "tool",
                "tool_id": tool.id,
                "tool_slug": tool.slug,
                "tool_version": {
                    "id": tool.current_version_id,
                    "version": "1.0.0",
                },
                "semantic_inputs": {"protein_pdb": "workflow_input:protein_pdb"},
                "params": {"device": "cpu"},
            },
        ],
        "edges": [
            {
                "source": "protein_input",
                "target": "pocket_prediction",
                "source_output": "protein_pdb",
                "target_input": "protein_pdb",
            }
        ],
    }


def linear_generation_definition(pocket_tool: Tool, generation_tool: Tool) -> dict:
    definition = template_definition(pocket_tool)
    definition["nodes"].append(
        {
            "id": "molecule_generation",
            "kind": "tool",
            "tool_id": generation_tool.id,
            "tool_slug": generation_tool.slug,
            "tool_version": {
                "id": generation_tool.current_version_id,
                "version": "1.0.0",
            },
            "semantic_inputs": {"pocket_pdb": "node:pocket_prediction:pocket_pdb"},
            "params": {"params.n_samples": 8},
        }
    )
    definition["edges"].append(
        {
            "source": "pocket_prediction",
            "target": "molecule_generation",
            "source_output": "pocket_pdb",
            "target_input": "pocket_pdb",
        }
    )
    return definition


def semantic_only_generation_definition(pocket_tool: Tool, generation_tool: Tool) -> dict:
    return {
        "nodes": [
            {
                "id": "protein_input",
                "kind": "input",
                "semantic_type": "protein_pdb",
            },
            {
                "id": "molecule_generation",
                "kind": "tool",
                "tool_id": generation_tool.id,
                "tool_slug": generation_tool.slug,
                "semantic_inputs": {"pocket_pdb": "node:pocket_prediction:pocket_pdb"},
            },
            {
                "id": "pocket_prediction",
                "kind": "tool",
                "tool_id": pocket_tool.id,
                "tool_slug": pocket_tool.slug,
                "semantic_inputs": {"protein_pdb": "workflow_input:protein_pdb"},
            },
        ],
        "edges": [],
    }


def standard_artifact_generation_definition(pocket_tool: Tool, generation_tool: Tool) -> dict:
    return {
        "nodes": [
            {
                "id": "protein_input",
                "kind": "input",
                "standard_type": "protein_structure@1",
            },
            {
                "id": "pocket_prediction",
                "kind": "tool",
                "tool_id": pocket_tool.id,
                "tool_slug": pocket_tool.slug,
                "tool_version": {
                    "id": pocket_tool.current_version_id,
                    "version": "1.0.0",
                },
                "artifact_input_slots": [
                    {"name": "protein", "type": "protein_structure@1", "required": True}
                ],
                "artifact_inputs": {"protein": "workflow_input:protein_structure@1"},
                "artifact_outputs": [
                    {"name": "pocket", "type": "binding_pocket@1", "required": True}
                ],
            },
            {
                "id": "molecule_generation",
                "kind": "tool",
                "tool_id": generation_tool.id,
                "tool_slug": generation_tool.slug,
                "tool_version": {
                    "id": generation_tool.current_version_id,
                    "version": "1.0.0",
                },
                "artifact_input_slots": [
                    {"name": "pocket", "type": "binding_pocket@1", "required": True}
                ],
                "artifact_inputs": {"pocket": "node:pocket_prediction:pocket"},
                "artifact_outputs": [
                    {
                        "name": "ligands",
                        "type": "ligand_structure@1",
                        "cardinality": "many",
                        "required": True,
                    }
                ],
            },
        ],
        "edges": [
            {
                "source": "protein_input",
                "target": "pocket_prediction",
                "source_output": "protein_structure@1",
                "target_input": "protein",
            },
            {
                "source": "pocket_prediction",
                "target": "molecule_generation",
                "source_output": "pocket",
                "target_input": "pocket",
            },
        ],
    }


def slug_only_tool_definition(pocket_tool: Tool) -> dict:
    return {
        "nodes": [
            {
                "id": "protein_input",
                "kind": "input",
                "semantic_type": "protein_pdb",
            },
            {
                "id": "pocket_prediction",
                "tool_id": pocket_tool.id,
                "tool_slug": pocket_tool.slug,
                "tool_version": {
                    "id": pocket_tool.current_version_id,
                    "version": "1.0.0",
                },
                "semantic_inputs": {"protein_pdb": "workflow_input:protein_pdb"},
                "params": {"device": "cpu"},
            },
        ],
        "edges": [
            {
                "source": "protein_input",
                "target": "pocket_prediction",
                "source_output": "protein_pdb",
                "target_input": "protein_pdb",
            }
        ],
    }


async def create_fake_scheduled_task(*, db, current_user, task_data, direct_runner=None):
    tool = await db.get(Tool, task_data.tool_id)
    task = Task(
        user_id=current_user.id,
        tool_id=task_data.tool_id,
        tool_version_id=task_data.tool_version_id or tool.current_version_id,
        name=task_data.name,
        status=TaskStatus.PENDING.value,
        progress=0.0,
        priority=task_data.priority,
        extra_data={"project_id": task_data.project_id} if task_data.project_id else {},
    )
    db.add(task)
    await db.flush()
    db.add(
        TaskInput(
            task_id=task.id,
            params=task_data.params,
            file_ids=task_data.file_ids or [],
        )
    )
    return task


async def create_project_for_user(db_session: AsyncSession, owner: User) -> Project:
    organization = Organization(name="Workflow org", slug="workflow-org")
    project = Project(
        organization=organization,
        created_by=owner.id,
        name="Project workflow",
        goal="Run project scoped workflows",
        status="active",
    )
    db_session.add_all([organization, project])
    await db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def create_workflow_definition_for_run(
    api_client: httpx.AsyncClient,
    *,
    name: str,
    definition: dict,
    project_id: str | None = None,
) -> dict:
    payload = {
        "name": name,
        "project_id": project_id,
        "canvas_preset_id": "free-canvas",
        "nodes": definition.get("nodes", []),
        "edges": definition.get("edges", []),
        "selected_tool_by_node": {},
        "artifact_bindings_by_node": {},
    }
    response = await api_client.post(
        "/api/v1/workflows",
        headers={"Authorization": "Bearer owner-token"},
        json=payload,
    )
    assert response.status_code == 200
    return response.json()["data"]


async def create_workflow_run_for_definition(
    api_client: httpx.AsyncClient,
    *,
    name: str,
    definition: dict,
    input_files: dict[str, str],
) -> tuple[dict, httpx.Response]:
    workflow = await create_workflow_definition_for_run(
        api_client,
        name=name,
        definition=definition,
    )
    run_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": input_files},
    )
    return workflow, run_response


@pytest.mark.asyncio
async def test_create_workflow_definition_run_inherits_project_and_schedules_nodes(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    project = await create_project_for_user(db_session, owner)
    workflow = await create_workflow_definition_for_run(
        api_client,
        name="Project Protein to Pocket",
        project_id=project.id,
        definition=template_definition(pocket_tool),
    )

    run_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )

    assert run_response.status_code == 200
    run = run_response.json()["data"]
    assert run["workflow_definition_id"] == workflow["id"]
    assert run["project_id"] == project.id
    assert "canvas_preset_id" not in run
    node_state = run["node_states"]["pocket_prediction"]
    assert node_state["status"] == "waiting_task"
    assert node_state["task_id"]
    params = node_state["params"]
    assert params["workflow_definition_id"] == workflow["id"]
    assert "workflow_template_id" not in params
    task = await db_session.get(Task, node_state["task_id"])
    assert task.extra_data["project_id"] == project.id


@pytest.mark.asyncio
async def test_project_workflow_run_requires_membership(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    project = await create_project_for_user(db_session, owner)
    workflow = await create_workflow_definition_for_run(
        api_client,
        name="Private project flow",
        project_id=project.id,
        definition=template_definition(pocket_tool),
    )

    create_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer other-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    list_response = await api_client.get(
        f"/api/v1/workflows/runs?project_id={project.id}",
        headers={"Authorization": "Bearer other-token"},
    )

    assert create_response.status_code == 404
    assert list_response.status_code == 404


@pytest.mark.asyncio
async def test_project_member_can_run_shared_project_workflow_definition(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    other_user: User,
    pocket_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    project = await create_project_for_user(db_session, owner)
    db_session.add(ProjectMember(project_id=project.id, user_id=other_user.id, role="editor"))
    await db_session.commit()
    member_file = await create_protein_file_for_user(
        db_session,
        other_user,
        filename="member-protein.pdb",
    )
    workflow = await create_workflow_definition_for_run(
        api_client,
        name="Shared project flow",
        project_id=project.id,
        definition=template_definition(pocket_tool),
    )

    run_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer other-token"},
        json={"input_files": {"protein_pdb": member_file.id}},
    )
    list_response = await api_client.get(
        f"/api/v1/workflows/runs?project_id={project.id}",
        headers={"Authorization": "Bearer other-token"},
    )

    assert run_response.status_code == 200
    run = run_response.json()["data"]
    assert run["owner_id"] == other_user.id
    assert run["project_id"] == project.id
    assert run["workflow_definition_id"] == workflow["id"]
    assert list_response.status_code == 200
    listed = list_response.json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == run["id"]


@pytest.mark.asyncio
async def test_project_member_can_restore_project_workflow_run_created_by_owner(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    other_user: User,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    project = await create_project_for_user(db_session, owner)
    db_session.add(ProjectMember(project_id=project.id, user_id=other_user.id, role="viewer"))
    await db_session.commit()
    workflow = await create_workflow_definition_for_run(
        api_client,
        name="Owner project flow",
        project_id=project.id,
        definition=template_definition(pocket_tool),
    )
    run_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    run = run_response.json()["data"]

    restore_response = await api_client.get(
        f"/api/v1/workflows/runs/{run['id']}",
        headers={"Authorization": "Bearer other-token"},
    )
    list_response = await api_client.get(
        f"/api/v1/workflows/runs?project_id={project.id}",
        headers={"Authorization": "Bearer other-token"},
    )

    assert restore_response.status_code == 200
    assert restore_response.json()["data"]["id"] == run["id"]
    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["id"] == run["id"]


@pytest.mark.asyncio
async def test_project_workflow_run_operations_require_runner_or_write_role(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    other_user: User,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    project = await create_project_for_user(db_session, owner)
    membership = ProjectMember(project_id=project.id, user_id=other_user.id, role="viewer")
    db_session.add(membership)
    await db_session.commit()
    workflow = await create_workflow_definition_for_run(
        api_client,
        name="Project operation flow",
        project_id=project.id,
        definition=template_definition(pocket_tool),
    )

    cancel_run_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    cancel_run = cancel_run_response.json()["data"]
    cancel_task_id = cancel_run["node_states"]["pocket_prediction"]["task_id"]

    viewer_cancel_response = await api_client.post(
        f"/api/v1/workflows/runs/{cancel_run['id']}/cancel",
        headers={"Authorization": "Bearer other-token"},
    )
    membership.role = "runner"
    await db_session.commit()
    runner_cancel_response = await api_client.post(
        f"/api/v1/workflows/runs/{cancel_run['id']}/cancel",
        headers={"Authorization": "Bearer other-token"},
    )

    canceled_task = await db_session.get(Task, cancel_task_id)
    assert viewer_cancel_response.status_code == 403
    assert runner_cancel_response.status_code == 200
    assert runner_cancel_response.json()["data"]["status"] == "canceled"
    assert canceled_task is not None
    assert canceled_task.status == TaskStatus.CANCELED.value

    retry_run_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    retry_run = retry_run_response.json()["data"]
    failed_task_id = retry_run["node_states"]["pocket_prediction"]["task_id"]
    failed_task = await db_session.get(Task, failed_task_id)
    assert failed_task is not None
    failed_task.status = TaskStatus.FAILURE.value
    failed_task.error_message = "temporary failure"
    await db_session.commit()
    sync_response = await api_client.post(
        f"/api/v1/workflows/runs/{retry_run['id']}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert sync_response.status_code == 200
    membership.role = "viewer"
    await db_session.commit()
    viewer_retry_response = await api_client.post(
        f"/api/v1/workflows/runs/{retry_run['id']}/nodes/pocket_prediction/retry",
        headers={"Authorization": "Bearer other-token"},
    )
    membership.role = "runner"
    await db_session.commit()
    runner_retry_response = await api_client.post(
        f"/api/v1/workflows/runs/{retry_run['id']}/nodes/pocket_prediction/retry",
        headers={"Authorization": "Bearer other-token"},
    )

    assert viewer_retry_response.status_code == 403
    assert runner_retry_response.status_code == 200
    retry_state = runner_retry_response.json()["data"]["node_states"]["pocket_prediction"]
    assert retry_state["status"] == "waiting_task"
    assert retry_state["task_id"] != failed_task_id


@pytest.mark.asyncio
async def test_workflow_template_routes_are_removed(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_workflow_run_preflights_required_inputs(
    api_client: httpx.AsyncClient,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    workflow = await create_workflow_definition_for_run(
        api_client,
        name="Protein to Pocket",
        definition=template_definition(pocket_tool),
    )

    missing_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {}},
    )
    assert missing_response.status_code == 422
    assert "protein_pdb" in missing_response.json()["message"]

    run_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    assert run_response.status_code == 200
    run = run_response.json()["data"]
    assert run["workflow_definition_id"] == workflow["id"]
    assert run["status"] == "waiting_task"
    assert run["input_files"] == {"protein_pdb": protein_file.id}
    assert run["execution_order"] == ["pocket_prediction"]
    assert run["node_states"]["pocket_prediction"]["status"] == "waiting_task"
    assert run["node_states"]["pocket_prediction"]["tool_version_id"] == pocket_tool.current_version_id
    params = run["node_states"]["pocket_prediction"]["params"]
    assert params["device"] == "cpu"
    assert params["workflow_node_id"] == "pocket_prediction"
    assert params["workflow_node_type"] == "tool"
    assert params["workflow_run_id"] == run["id"]
    assert params["workflow_definition_id"] == workflow["id"]
    assert run["node_states"]["pocket_prediction"]["task_id"]
    assert run["node_states"]["pocket_prediction"]["input_file_ids"] == [protein_file.id]
    assert run["definition"]["nodes"][1]["tool_version"]["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_get_workflow_run_restores_owner_run_state(
    api_client: httpx.AsyncClient,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    workflow = await create_workflow_definition_for_run(
        api_client,
        name="Protein to Pocket",
        definition=template_definition(pocket_tool),
    )
    run_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    created_run = run_response.json()["data"]

    restore_response = await api_client.get(
        f"/api/v1/workflows/runs/{created_run['id']}",
        headers={"Authorization": "Bearer owner-token"},
    )
    forbidden_response = await api_client.get(
        f"/api/v1/workflows/runs/{created_run['id']}",
        headers={"Authorization": "Bearer other-token"},
    )

    assert restore_response.status_code == 200
    restored = restore_response.json()["data"]
    assert restored["id"] == created_run["id"]
    assert restored["status"] == "waiting_task"
    assert restored["node_states"]["pocket_prediction"]["task_id"]
    assert forbidden_response.status_code == 403


@pytest.mark.asyncio
async def test_list_workflow_runs_is_owner_scoped_and_filterable_by_workflow_definition(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    other_user: User,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    first_workflow = await create_workflow_definition_for_run(
        api_client,
        name="Protein to Pocket A",
        definition=template_definition(pocket_tool),
    )
    second_workflow = await create_workflow_definition_for_run(
        api_client,
        name="Protein to Pocket B",
        definition=template_definition(pocket_tool),
    )

    first_run_response = await api_client.post(
        f"/api/v1/workflows/{first_workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    second_run_response = await api_client.post(
        f"/api/v1/workflows/{second_workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    other_workflow = WorkflowDefinition(
        user_id=other_user.id,
        name="Other user's workflow",
        canvas_preset_id="free-canvas",
        nodes=template_definition(pocket_tool)["nodes"],
        edges=template_definition(pocket_tool)["edges"],
        selected_tool_by_node={},
        artifact_bindings_by_node={},
    )
    db_session.add(other_workflow)
    await db_session.flush()
    other_run = WorkflowRun(
        owner_id=other_user.id,
        workflow_definition_id=other_workflow.id,
        name="Other user's run",
        status="pending",
        definition=template_definition(pocket_tool),
        input_files={},
        execution_order=[],
        node_states={},
        artifact_lineage={},
    )
    db_session.add(other_run)
    await db_session.commit()

    list_response = await api_client.get(
        "/api/v1/workflows/runs",
        headers={"Authorization": "Bearer owner-token"},
    )
    filter_response = await api_client.get(
        f"/api/v1/workflows/runs?workflow_definition_id={first_workflow['id']}",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert list_response.status_code == 200
    listed = list_response.json()["data"]
    listed_ids = {item["id"] for item in listed["items"]}
    assert listed["total"] == 2
    assert listed_ids == {
        first_run_response.json()["data"]["id"],
        second_run_response.json()["data"]["id"],
    }
    assert other_run.id not in listed_ids
    assert filter_response.status_code == 200
    filtered = filter_response.json()["data"]
    assert filtered["total"] == 1
    assert filtered["items"][0]["workflow_definition_id"] == first_workflow["id"]


@pytest.mark.asyncio
async def test_sync_workflow_run_extracts_outputs_and_schedules_downstream(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    pocket_tool: Tool,
    generation_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Protein to Generation",
        definition=linear_generation_definition(pocket_tool, generation_tool),
        input_files={"protein_pdb": protein_file.id},
    )
    run = run_response.json()["data"]
    first_task_id = run["node_states"]["pocket_prediction"]["task_id"]

    pocket_output = FileModel(
        owner_id=owner.id,
        filename="best_pocket.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"pocket").hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path="/tmp/best_pocket.pdb",
        is_public=False,
    )
    db_session.add(pocket_output)
    await db_session.flush()
    task = await db_session.get(Task, first_task_id)
    task.status = TaskStatus.SUCCESS.value
    db_session.add(TaskOutput(task_id=task.id, result={"ok": True}, file_ids=[pocket_output.id]))
    await db_session.commit()

    sync_response = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert sync_response.status_code == 200
    synced = sync_response.json()["data"]
    first_state = synced["node_states"]["pocket_prediction"]
    second_state = synced["node_states"]["molecule_generation"]
    assert synced["status"] == "waiting_task"
    assert first_state["status"] == "success"
    assert first_state["semantic_outputs"]["pocket_pdb"]["file_id"] == pocket_output.id
    assert synced["artifact_lineage"]["pocket_prediction"]["pocket_pdb"]["file_id"] == pocket_output.id
    assert second_state["status"] == "waiting_task"
    assert second_state["task_id"]
    assert second_state["input_file_ids"] == [pocket_output.id]


@pytest.mark.asyncio
async def test_sync_workflow_run_schedules_downstream_standard_artifact_slots(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    pocket_tool = await create_standard_tool(
        db_session,
        owner,
        slug="standard-pocket-tool",
        inputs=[{"name": "protein", "type": "protein_structure@1", "required": True}],
        outputs=[{"name": "pocket", "type": "binding_pocket@1", "required": True}],
    )
    generation_tool = await create_standard_tool(
        db_session,
        owner,
        slug="standard-generation-tool",
        inputs=[{"name": "pocket", "type": "binding_pocket@1", "required": True}],
        outputs=[
            {
                "name": "ligands",
                "type": "ligand_structure@1",
                "cardinality": "many",
                "required": True,
            }
        ],
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Standard Artifact Flow",
        definition=standard_artifact_generation_definition(pocket_tool, generation_tool),
        input_files={"protein_structure@1": protein_file.id},
    )
    run = run_response.json()["data"]
    assert run["project_id"]
    first_state = run["node_states"]["pocket_prediction"]
    assert first_state["input_file_ids"] == [protein_file.id]

    output_files = []
    for filename, content in [
        ("residue_pocket.pdb", b"residue"),
        ("atom_pocket.pdb", b"atom"),
        ("pocket_metadata.json", b"{}"),
    ]:
        file_record = FileModel(
            project_id=run["project_id"],
            owner_id=owner.id,
            filename=filename,
            content_type="application/json" if filename.endswith(".json") else "chemical/x-pdb",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            source_type=FileSourceType.TOOL_OUTPUT.value,
            storage_path=f"/tmp/{filename}",
            is_public=False,
        )
        db_session.add(file_record)
        await db_session.flush()
        output_files.append(file_record)

    pocket_version = await create_binding_pocket_version(
        db_session,
        owner,
        project_id=run["project_id"],
        files=output_files,
    )

    task = await db_session.get(Task, first_state["task_id"])
    task.status = TaskStatus.SUCCESS.value
    standard_artifacts = {
        "artifact_version_ids_by_ref": {"pocket": pocket_version.id},
        "file_ids_by_artifact_ref": {
            "pocket": [file_record.id for file_record in output_files]
        },
    }
    db_session.add(
        TaskOutput(
            task_id=task.id,
            result={"standard_artifacts": standard_artifacts},
            file_ids=[file_record.id for file_record in output_files],
        )
    )
    await db_session.commit()

    sync_response = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert sync_response.status_code == 200
    synced = sync_response.json()["data"]
    source_state = synced["node_states"]["pocket_prediction"]
    downstream_state = synced["node_states"]["molecule_generation"]
    assert synced["status"] == "waiting_task"
    assert source_state["status"] == "success"
    assert source_state["standard_artifacts"] == standard_artifacts
    assert downstream_state["status"] == "waiting_task"
    assert downstream_state["input_file_ids"] == [
        file_record.id for file_record in output_files
    ]


@pytest.mark.asyncio
async def test_sync_workflow_run_standard_artifact_satisfies_legacy_semantic_gate(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    pocket_tool: Tool,
    generation_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Legacy LVpocket With Standard Artifacts",
        definition=standard_artifact_generation_definition(pocket_tool, generation_tool),
        input_files={"protein_structure@1": protein_file.id},
    )
    run = run_response.json()["data"]
    first_state = run["node_states"]["pocket_prediction"]

    output_files = []
    for filename, content in [
        ("residue_region.pdb", b"residue"),
        ("atom_region.pdb", b"atom"),
        ("metadata.json", b"{}"),
    ]:
        file_record = FileModel(
            owner_id=owner.id,
            filename=filename,
            content_type="application/json" if filename.endswith(".json") else "chemical/x-pdb",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            source_type=FileSourceType.TOOL_OUTPUT.value,
            storage_path=f"/tmp/{filename}",
            is_public=False,
        )
        db_session.add(file_record)
        await db_session.flush()
        output_files.append(file_record)

    standard_artifacts = {
        "artifact_version_ids_by_ref": {"pocket": "artifact-version-pocket"},
        "file_ids_by_artifact_ref": {
            "pocket": [file_record.id for file_record in output_files]
        },
    }
    task = await db_session.get(Task, first_state["task_id"])
    task.status = TaskStatus.SUCCESS.value
    db_session.add(
        TaskOutput(
            task_id=task.id,
            result={"standard_artifacts": standard_artifacts},
            file_ids=[file_record.id for file_record in output_files],
        )
    )
    await db_session.commit()

    sync_response = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert sync_response.status_code == 200
    synced = sync_response.json()["data"]
    source_state = synced["node_states"]["pocket_prediction"]
    downstream_state = synced["node_states"]["molecule_generation"]
    assert synced["status"] == "waiting_task"
    assert source_state["status"] == "success"
    assert source_state["semantic_outputs"] == {}
    assert source_state["standard_artifacts"] == standard_artifacts
    assert downstream_state["status"] == "waiting_task"
    assert downstream_state["input_file_ids"] == [
        file_record.id for file_record in output_files
    ]


@pytest.mark.asyncio
async def test_workflow_reconciliation_service_advances_waiting_runs(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    pocket_tool: Tool,
    generation_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Protein to Generation",
        definition=linear_generation_definition(pocket_tool, generation_tool),
        input_files={"protein_pdb": protein_file.id},
    )
    run = run_response.json()["data"]
    first_task_id = run["node_states"]["pocket_prediction"]["task_id"]

    pocket_output = FileModel(
        owner_id=owner.id,
        filename="best_pocket.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"pocket-reconcile").hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path="/tmp/best_pocket_reconcile.pdb",
        is_public=False,
    )
    db_session.add(pocket_output)
    await db_session.flush()
    task = await db_session.get(Task, first_task_id)
    task.status = TaskStatus.SUCCESS.value
    db_session.add(TaskOutput(task_id=task.id, result={"ok": True}, file_ids=[pocket_output.id]))
    await db_session.commit()

    module_spec = importlib.util.find_spec("app.services.workflow_reconciliation")
    assert module_spec is not None
    workflow_reconciliation = importlib.import_module("app.services.workflow_reconciliation")

    processed = await workflow_reconciliation.reconcile_waiting_workflow_runs(
        db_session,
        batch_size=10,
        schedule_task_fn=create_fake_scheduled_task,
    )

    assert processed == 1
    run_record = await db_session.get(WorkflowRun, run["id"])
    assert run_record is not None
    downstream_state = (run_record.node_states or {})["molecule_generation"]
    assert downstream_state["status"] == "waiting_task"
    assert downstream_state["task_id"]


@pytest.mark.asyncio
async def test_sync_workflow_run_does_not_duplicate_pending_node_task_when_task_id_exists(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    pocket_tool: Tool,
    generation_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Protein to Generation",
        definition=linear_generation_definition(pocket_tool, generation_tool),
        input_files={"protein_pdb": protein_file.id},
    )
    run = run_response.json()["data"]
    first_task_id = run["node_states"]["pocket_prediction"]["task_id"]

    pocket_output = FileModel(
        owner_id=owner.id,
        filename="best_pocket_duplicate_guard.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"pocket-duplicate-guard").hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path="/tmp/best_pocket_duplicate_guard.pdb",
        is_public=False,
    )
    db_session.add(pocket_output)
    await db_session.flush()
    task = await db_session.get(Task, first_task_id)
    task.status = TaskStatus.SUCCESS.value
    db_session.add(TaskOutput(task_id=task.id, result={"ok": True}, file_ids=[pocket_output.id]))
    await db_session.commit()

    first_sync = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert first_sync.status_code == 200
    first_synced_run = first_sync.json()["data"]
    downstream_state = first_synced_run["node_states"]["molecule_generation"]
    original_downstream_task_id = downstream_state["task_id"]

    run_record = await db_session.get(WorkflowRun, run["id"])
    node_states = dict(run_record.node_states or {})
    mutated_downstream_state = dict(node_states["molecule_generation"])
    mutated_downstream_state["status"] = "pending"
    node_states["molecule_generation"] = mutated_downstream_state
    run_record.node_states = node_states
    await db_session.commit()
    await db_session.refresh(run_record)

    second_sync = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert second_sync.status_code == 200
    second_synced_run = second_sync.json()["data"]
    second_downstream_state = second_synced_run["node_states"]["molecule_generation"]
    assert second_downstream_state["task_id"] == original_downstream_task_id

    task_count_result = await db_session.execute(select(func.count()).select_from(Task))
    assert task_count_result.scalar_one() == 2


@pytest.mark.asyncio
async def test_sync_workflow_run_failure_stops_downstream_scheduling(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    pocket_tool: Tool,
    generation_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Failure Stops Downstream",
        definition=linear_generation_definition(pocket_tool, generation_tool),
        input_files={"protein_pdb": protein_file.id},
    )
    run = run_response.json()["data"]
    first_task_id = run["node_states"]["pocket_prediction"]["task_id"]

    first_task = await db_session.get(Task, first_task_id)
    assert first_task is not None
    first_task.status = TaskStatus.FAILURE.value
    first_task.error_message = "upstream failure"
    await db_session.commit()

    sync_response = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert sync_response.status_code == 200
    synced = sync_response.json()["data"]
    assert synced["status"] == "failure"
    assert synced["node_states"]["pocket_prediction"]["status"] == "failure"
    assert synced["node_states"]["molecule_generation"]["status"] == "pending"
    assert synced["node_states"]["molecule_generation"].get("task_id") is None

    task_count_result = await db_session.execute(select(func.count()).select_from(Task))
    assert task_count_result.scalar_one() == 1


@pytest.mark.asyncio
async def test_cancel_workflow_run_cancels_active_node_tasks(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Cancelable workflow",
        definition=template_definition(pocket_tool),
        input_files={"protein_pdb": protein_file.id},
    )
    run = run_response.json()["data"]
    task_id = run["node_states"]["pocket_prediction"]["task_id"]

    cancel_response = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/cancel",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert cancel_response.status_code == 200
    canceled = cancel_response.json()["data"]
    assert canceled["status"] == "canceled"
    assert canceled["node_states"]["pocket_prediction"]["status"] == "canceled"
    assert canceled["node_states"]["pocket_prediction"]["task_id"] == task_id
    task = await db_session.get(Task, task_id)
    assert task is not None
    assert task.status == TaskStatus.CANCELED.value


@pytest.mark.asyncio
async def test_retry_failed_workflow_node_reschedules_only_that_node(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    pocket_tool: Tool,
    generation_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Retry Failed Node",
        definition=linear_generation_definition(pocket_tool, generation_tool),
        input_files={"protein_pdb": protein_file.id},
    )
    run = run_response.json()["data"]
    first_task_id = run["node_states"]["pocket_prediction"]["task_id"]
    first_task = await db_session.get(Task, first_task_id)
    assert first_task is not None
    first_task.status = TaskStatus.FAILURE.value
    first_task.error_message = "temporary failure"
    await db_session.commit()

    sync_response = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert sync_response.status_code == 200
    failed_run = sync_response.json()["data"]
    assert failed_run["status"] == "failure"

    retry_response = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/nodes/pocket_prediction/retry",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert retry_response.status_code == 200
    retried = retry_response.json()["data"]
    retried_state = retried["node_states"]["pocket_prediction"]
    downstream_state = retried["node_states"]["molecule_generation"]
    assert retried["status"] == "waiting_task"
    assert retried["error_message"] is None
    assert retried_state["status"] == "waiting_task"
    assert retried_state["task_id"] != first_task_id
    assert "error_message" not in retried_state
    assert downstream_state["status"] == "pending"
    assert downstream_state.get("task_id") is None
    task_count_result = await db_session.execute(select(func.count()).select_from(Task))
    assert task_count_result.scalar_one() == 2


@pytest.mark.asyncio
async def test_workflow_definition_run_rejects_cycles(
    api_client: httpx.AsyncClient,
    pocket_tool: Tool,
) -> None:
    definition = template_definition(pocket_tool)
    definition["nodes"].append(
        {
            "id": "property_prediction",
            "kind": "tool",
            "tool_slug": "molp-pc-property-prediction",
            "semantic_inputs": {"smiles_csv": "node:pocket_prediction:smiles_csv"},
        }
    )
    definition["edges"].extend(
        [
            {"source": "pocket_prediction", "target": "property_prediction"},
            {"source": "property_prediction", "target": "pocket_prediction"},
        ]
    )

    workflow = await create_workflow_definition_for_run(
        api_client,
        name="Cyclic Flow",
        definition=definition,
    )
    response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {}},
    )

    assert response.status_code == 422
    assert "cycle" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_workflow_definition_run_accepts_tool_slug_only_nodes(
    api_client: httpx.AsyncClient,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Slug Only Flow",
        definition=slug_only_tool_definition(pocket_tool),
        input_files={"protein_pdb": protein_file.id},
    )

    assert run_response.status_code == 200
    run = run_response.json()["data"]
    assert run["execution_order"] == ["pocket_prediction"]
    assert run["node_states"]["pocket_prediction"]["tool_slug"] == pocket_tool.slug
    tool_node = next(node for node in run["definition"]["nodes"] if node["id"] == "pocket_prediction")
    assert tool_node["tool_version"]["id"] == pocket_tool.current_version_id
    assert run["node_states"]["pocket_prediction"]["status"] == "waiting_task"


@pytest.mark.asyncio
async def test_workflow_execution_order_uses_semantic_input_dependencies(
    api_client: httpx.AsyncClient,
    pocket_tool: Tool,
    generation_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Semantic Dependency Flow",
        definition=semantic_only_generation_definition(pocket_tool, generation_tool),
        input_files={"protein_pdb": protein_file.id},
    )

    assert run_response.status_code == 200
    run = run_response.json()["data"]
    assert run["execution_order"] == ["pocket_prediction", "molecule_generation"]
    assert run["node_states"]["pocket_prediction"]["status"] == "waiting_task"
    assert run["node_states"]["molecule_generation"]["status"] == "pending"


@pytest.mark.asyncio
async def test_workflow_definition_run_rejects_semantic_input_cycles(
    api_client: httpx.AsyncClient,
) -> None:
    workflow = await create_workflow_definition_for_run(
        api_client,
        name="Semantic Cycle Flow",
        definition={
            "nodes": [
                {
                    "id": "a",
                    "kind": "tool",
                    "tool_slug": "tool-a",
                    "semantic_inputs": {"result": "node:b:result"},
                },
                {
                    "id": "b",
                    "kind": "tool",
                    "tool_slug": "tool-b",
                    "semantic_inputs": {"result": "node:a:result"},
                },
            ],
            "edges": [],
        },
    )
    response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {}},
    )

    assert response.status_code == 422
    assert "cycle" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_sync_workflow_run_records_missing_required_output_details(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    _, run_response = await create_workflow_run_for_definition(
        api_client,
        name="Protein to Pocket",
        definition=template_definition(pocket_tool),
        input_files={"protein_pdb": protein_file.id},
    )
    run = run_response.json()["data"]
    task_id = run["node_states"]["pocket_prediction"]["task_id"]

    task = await db_session.get(Task, task_id)
    task.status = TaskStatus.SUCCESS.value
    db_session.add(TaskOutput(task_id=task.id, result={"ok": True}, file_ids=[]))
    await db_session.commit()

    sync_response = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert sync_response.status_code == 200
    synced = sync_response.json()["data"]
    node_state = synced["node_states"]["pocket_prediction"]
    assert synced["status"] == "failure"
    assert "pocket_pdb" in node_state["error_message"]
    assert node_state["missing_outputs"][0]["semantic_type"] == "pocket_pdb"
    assert node_state["missing_outputs"][0]["match"]["extension"] == ".pdb"


@pytest.mark.asyncio
async def test_list_workflow_runs_cursor_contract(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
) -> None:
    """运行列表 API：不传 cursor 有 total；传 cursor total=None + nextCursor/hasMore。"""
    from datetime import datetime

    workflow = WorkflowDefinition(
        user_id=owner.id,
        name="Cursor workflow",
        canvas_preset_id="free-canvas",
        nodes=[],
        edges=[],
        selected_tool_by_node={},
        artifact_bindings_by_node={},
    )
    db_session.add(workflow)
    await db_session.flush()

    fixed = datetime(2026, 1, 1, 12, 0, 0)
    runs = []
    for index in range(5):
        run = WorkflowRun(
            owner_id=owner.id,
            workflow_definition_id=workflow.id,
            name=f"cursor-run-{index}",
            status="pending",
            definition={"nodes": [], "edges": []},
            input_files={},
            execution_order=[],
            node_states={},
            artifact_lineage={},
        )
        db_session.add(run)
        runs.append(run)
    await db_session.flush()
    for run in runs:
        run.created_at = fixed
    await db_session.commit()
    expected = sorted((run.id for run in runs), reverse=True)

    offset_resp = await api_client.get(
        "/api/v1/workflows/runs?page=1&page_size=2",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert offset_resp.status_code == 200, offset_resp.text
    offset_data = offset_resp.json()["data"]
    assert offset_data["total"] == 5
    assert offset_data["totalKnown"] is True
    assert offset_data["hasMore"] is True
    assert offset_data["nextCursor"]
    assert [item["id"] for item in offset_data["items"]] == expected[:2]

    collected = [item["id"] for item in offset_data["items"]]
    cursor = offset_data["nextCursor"]
    pages = 0
    while cursor:
        resp = await api_client.get(
            f"/api/v1/workflows/runs?page_size=2&cursor={cursor}",
            headers={"Authorization": "Bearer owner-token"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total"] is None
        assert data["total_pages"] is None
        assert data["totalKnown"] is False
        collected.extend(item["id"] for item in data["items"])
        pages += 1
        assert pages < 10, "游标翻页没有收敛"
        cursor = data["nextCursor"] if data["hasMore"] else None

    assert collected == expected
    assert len(collected) == len(set(collected)) == 5
