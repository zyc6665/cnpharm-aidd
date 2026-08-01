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
from app.models import agent as _agent_models  # noqa: F401,E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import system_settings as _system_settings  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.files import File as FileModel, FileSourceType  # noqa: E402
from app.models.tasks import Task, TaskInput, TaskOutput, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.models.workflows import WorkflowRun  # noqa: E402


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
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": slug,
            "name": slug.replace("-", " ").title(),
            "version": "1.0.0",
        },
        "artifacts": {"inputs": inputs, "outputs": outputs},
        "parameters_schema": {"type": "object"},
        "exposure": {"agent": True, "workflow": True, "direct_run": True},
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


@pytest.mark.asyncio
async def test_workflow_template_crud_and_duplicate(
    api_client: httpx.AsyncClient,
    pocket_tool: Tool,
) -> None:
    response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "name": "Protein to Pocket",
            "description": "Predict pockets from a protein PDB.",
            "definition": template_definition(pocket_tool),
        },
    )

    assert response.status_code == 200
    created = response.json()["data"]
    assert created["name"] == "Protein to Pocket"
    assert created["definition"]["nodes"][1]["tool_version"]["version"] == "1.0.0"

    list_response = await api_client.get(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["data"]["total"] == 1

    duplicate_response = await api_client.post(
        f"/api/v1/workflows/templates/{created['id']}/duplicate",
        headers={"Authorization": "Bearer owner-token"},
        json={"name": "Protein to Pocket Copy"},
    )
    assert duplicate_response.status_code == 200
    duplicated = duplicate_response.json()["data"]
    assert duplicated["id"] != created["id"]
    assert duplicated["definition"] == created["definition"]

    delete_response = await api_client.delete(
        f"/api/v1/workflows/templates/{created['id']}",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["id"] == created["id"]


@pytest.mark.asyncio
async def test_workflow_template_access_is_owner_scoped(
    api_client: httpx.AsyncClient,
    pocket_tool: Tool,
) -> None:
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={"name": "Private Flow", "definition": template_definition(pocket_tool)},
    )
    template_id = create_response.json()["data"]["id"]

    forbidden_response = await api_client.get(
        f"/api/v1/workflows/templates/{template_id}",
        headers={"Authorization": "Bearer other-token"},
    )

    assert forbidden_response.status_code == 403


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
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={"name": "Protein to Pocket", "definition": template_definition(pocket_tool)},
    )
    template_id = create_response.json()["data"]["id"]

    missing_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {}},
    )
    assert missing_response.status_code == 422
    assert "protein_pdb" in missing_response.json()["message"]

    run_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    assert run_response.status_code == 200
    run = run_response.json()["data"]
    assert run["template_id"] == template_id
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
    assert params["workflow_template_id"] == template_id
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
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={"name": "Protein to Pocket", "definition": template_definition(pocket_tool)},
    )
    template_id = create_response.json()["data"]["id"]
    run_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
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
async def test_list_workflow_runs_is_owner_scoped_and_filterable_by_template(
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
    first_template_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={"name": "Protein to Pocket A", "definition": template_definition(pocket_tool)},
    )
    second_template_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={"name": "Protein to Pocket B", "definition": template_definition(pocket_tool)},
    )
    first_template_id = first_template_response.json()["data"]["id"]
    second_template_id = second_template_response.json()["data"]["id"]

    first_run_response = await api_client.post(
        f"/api/v1/workflows/templates/{first_template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    second_run_response = await api_client.post(
        f"/api/v1/workflows/templates/{second_template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )
    other_run = WorkflowRun(
        owner_id=other_user.id,
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
        f"/api/v1/workflows/runs?template_id={first_template_id}",
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
    assert filtered["items"][0]["template_id"] == first_template_id


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
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "name": "Protein to Generation",
            "definition": linear_generation_definition(pocket_tool, generation_tool),
        },
    )
    template_id = create_response.json()["data"]["id"]
    run_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
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
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "name": "Standard Artifact Flow",
            "definition": standard_artifact_generation_definition(pocket_tool, generation_tool),
        },
    )
    template_id = create_response.json()["data"]["id"]
    run_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_structure@1": protein_file.id}},
    )
    run = run_response.json()["data"]
    first_state = run["node_states"]["pocket_prediction"]
    assert first_state["input_file_ids"] == [protein_file.id]

    output_files = []
    for filename, content in [
        ("residue_pocket.pdb", b"residue"),
        ("atom_pocket.pdb", b"atom"),
        ("pocket_metadata.json", b"{}"),
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

    task = await db_session.get(Task, first_state["task_id"])
    task.status = TaskStatus.SUCCESS.value
    standard_artifacts = {
        "artifact_version_ids_by_ref": {"pocket": "artifact-version-pocket"},
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
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "name": "Protein to Generation",
            "definition": linear_generation_definition(pocket_tool, generation_tool),
        },
    )
    template_id = create_response.json()["data"]["id"]
    run_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
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
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "name": "Protein to Generation",
            "definition": linear_generation_definition(pocket_tool, generation_tool),
        },
    )
    template_id = create_response.json()["data"]["id"]
    run_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
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
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "name": "Failure Stops Downstream",
            "definition": linear_generation_definition(pocket_tool, generation_tool),
        },
    )
    template_id = create_response.json()["data"]["id"]
    run_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
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
async def test_workflow_template_rejects_cycles(
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

    response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={"name": "Cyclic Flow", "definition": definition},
    )

    assert response.status_code == 422
    assert "cycle" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_workflow_template_accepts_tool_slug_only_nodes(
    api_client: httpx.AsyncClient,
    pocket_tool: Tool,
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        create_fake_scheduled_task,
    )
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={"name": "Slug Only Flow", "definition": slug_only_tool_definition(pocket_tool)},
    )

    assert create_response.status_code == 200
    template_id = create_response.json()["data"]["id"]

    run_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
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
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "name": "Semantic Dependency Flow",
            "definition": semantic_only_generation_definition(pocket_tool, generation_tool),
        },
    )
    assert create_response.status_code == 200
    template_id = create_response.json()["data"]["id"]

    run_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
    )

    assert run_response.status_code == 200
    run = run_response.json()["data"]
    assert run["execution_order"] == ["pocket_prediction", "molecule_generation"]
    assert run["node_states"]["pocket_prediction"]["status"] == "waiting_task"
    assert run["node_states"]["molecule_generation"]["status"] == "pending"


@pytest.mark.asyncio
async def test_workflow_template_rejects_semantic_input_cycles(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "name": "Semantic Cycle Flow",
            "definition": {
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
        },
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
    create_response = await api_client.post(
        "/api/v1/workflows/templates",
        headers={"Authorization": "Bearer owner-token"},
        json={"name": "Protein to Pocket", "definition": template_definition(pocket_tool)},
    )
    template_id = create_response.json()["data"]["id"]
    run_response = await api_client.post(
        f"/api/v1/workflows/templates/{template_id}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": {"protein_pdb": protein_file.id}},
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
