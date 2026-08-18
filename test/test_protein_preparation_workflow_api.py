"""Protein preparation board-to-workflow integration tests."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1.research_boards import create_research_board, create_workflow_draft  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import agent as _agent_models  # noqa: F401,E402
from app.models import artifacts as _artifact_models  # noqa: F401,E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import projects as _project_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import system_settings as _system_settings  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tool_models  # noqa: F401,E402
from app.models import users as _user_models  # noqa: F401,E402
from app.models import workflows as _workflow_models  # noqa: F401,E402
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile  # noqa: E402
from app.models.files import File as FileModel  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.tasks import Task, TaskInput, TaskOutput, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.schemas.research_boards import ResearchBoardCreate  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = User(
        email="protein-workflow-owner@example.com",
        password_hash="hashed-password",
        display_name="protein-workflow-owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, owner: User):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(authorization: str | None = Header(default=None)) -> User:
        if authorization == "Bearer owner-token":
            return owner
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


async def _fake_schedule_task(*, db, current_user, task_data, direct_runner=None):
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


async def _create_builtin_tool(
    db: AsyncSession,
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
    db.add(tool)
    await db.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "builtin",
            "builtin_slug": slug,
            "artifacts": {"inputs": inputs, "outputs": outputs},
        },
        is_active=True,
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    await db.commit()
    await db.refresh(tool)
    return tool


async def _create_raw_protein_artifact(db: AsyncSession, owner: User) -> tuple[Artifact, FileModel]:
    artifact = Artifact(
        project_id="project-1",
        created_by=owner.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure@1",
        standard_type="protein_structure",
        standard_version=1,
        name="Raw 1ABC",
    )
    db.add(artifact)
    await db.flush()
    content = b"ATOM      1  N   ALA A   1\nEND\n"
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename="1ABC.pdb",
        content_type="chemical/x-pdb",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_key="standard/1ABC.pdb",
        status="available",
    )
    file_record = FileModel(
        project_id="project-1",
        owner_id=owner.id,
        filename="1ABC.pdb",
        content_type="chemical/x-pdb",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_path="/tmp/1ABC.pdb",
        source_type=FileSourceType.UPLOAD.value,
    )
    db.add_all([version, file_record])
    await db.flush()
    db.add(
        ArtifactVersionFile(
            artifact_version_id=version.id,
            role="structure_file",
            file_id=file_record.id,
            is_primary=True,
            sort_order=0,
        )
    )
    artifact.latest_version_id = version.id
    await db.commit()
    await db.refresh(artifact)
    await db.refresh(file_record)
    return artifact, file_record


async def _create_output_file(
    db: AsyncSession,
    owner: User,
    *,
    filename: str,
    content: bytes,
    content_type: str,
) -> FileModel:
    file_record = FileModel(
        project_id="project-1",
        owner_id=owner.id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_path=f"/tmp/{filename}",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    db.add(file_record)
    await db.flush()
    return file_record


@pytest.mark.asyncio
async def test_board_protein_preparation_workflow_schedules_downstream_with_prepared_artifact(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    owner: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        _fake_schedule_task,
    )
    raw_artifact, raw_file = await _create_raw_protein_artifact(db_session, owner)
    prep_tool = await _create_builtin_tool(
        db_session,
        owner,
        slug="builtin-protein-preparation",
        inputs=[{"name": "protein", "type": "protein_structure@1", "required": True}],
        outputs=[
            {"name": "prepared_protein", "type": "protein_structure@1", "required": True}
        ],
    )
    docking_tool = await _create_builtin_tool(
        db_session,
        owner,
        slug="builtin-vina-docking",
        inputs=[{"name": "protein", "type": "protein_structure@1", "required": True}],
        outputs=[{"name": "docking_report", "type": "run_report@1", "required": False}],
    )
    board_response = await create_research_board(
        ResearchBoardCreate(
            name="Protein preparation flow",
            content={
                "nodes": [
                    {
                        "id": "artifact-raw",
                        "type": "artifact",
                        "position": {"x": 0, "y": 0},
                        "artifact_id": raw_artifact.id,
                    },
                    {
                        "id": "tool-prep",
                        "type": "tool",
                        "position": {"x": 320, "y": 0},
                        "tool_id": prep_tool.id,
                    },
                    {
                        "id": "tool-docking",
                        "type": "tool",
                        "position": {"x": 640, "y": 0},
                        "tool_id": docking_tool.id,
                    },
                ],
                "edges": [
                    {"id": "edge-raw-prep", "source": "artifact-raw", "target": "tool-prep"},
                    {"id": "edge-prep-docking", "source": "tool-prep", "target": "tool-docking"},
                ],
                "viewport": {"x": 0, "y": 0, "zoom": 1},
            },
        ),
        owner,
        db_session,
    )
    draft = await create_workflow_draft(board_response["data"]["id"], owner, db_session)
    definition = draft["data"]["definition"]

    nodes_by_id = {node["id"]: node for node in definition["nodes"]}
    assert nodes_by_id["tool-prep"]["artifact_inputs"] == {
        "protein": "workflow_input:protein_structure@1"
    }
    assert nodes_by_id["tool-docking"]["artifact_inputs"] == {
        "protein": "node:tool-prep:prepared_protein"
    }

    workflow_response = await api_client.post(
        "/api/v1/workflows",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "name": draft["data"]["name"],
            "canvas_preset_id": "free-canvas",
            "nodes": definition["nodes"],
            "edges": definition["edges"],
            "selected_tool_by_node": definition["selected_tool_by_node"],
            "artifact_bindings_by_node": definition["artifact_bindings_by_node"],
        },
    )
    assert workflow_response.status_code == 200
    workflow = workflow_response.json()["data"]

    run_response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={"input_files": draft["data"]["input_files"]},
    )
    assert run_response.status_code == 200
    run = run_response.json()["data"]
    assert run["execution_order"] == ["tool-prep", "tool-docking"]
    prep_state = run["node_states"]["tool-prep"]
    docking_state = run["node_states"]["tool-docking"]
    assert prep_state["status"] == "waiting_task"
    assert prep_state["input_file_ids"] == [raw_file.id]
    assert prep_state["params"]["builtin_inputs"] == {"protein_structure@1": raw_file.id}
    assert docking_state["status"] == "pending"
    assert not docking_state.get("task_id")

    prepared_pdb = await _create_output_file(
        db_session,
        owner,
        filename="prepared.pdb",
        content=b"ATOM      1  N   ALA A   1\nEND\n",
        content_type="chemical/x-pdb",
    )
    receptor_pdbqt = await _create_output_file(
        db_session,
        owner,
        filename="receptor.pdbqt",
        content=b"REMARK receptor pdbqt\n",
        content_type="chemical/x-pdbqt",
    )
    prep_task = await db_session.get(Task, prep_state["task_id"])
    assert prep_task is not None
    prep_task.status = TaskStatus.SUCCESS.value
    db_session.add(
        TaskOutput(
            task_id=prep_task.id,
            result={
                "standard_artifacts": {
                    "artifact_version_ids_by_ref": {"prepared_protein": "prepared-version-1"},
                    "file_ids_by_artifact_ref": {
                        "prepared_protein": [prepared_pdb.id, receptor_pdbqt.id]
                    },
                }
            },
            file_ids=[prepared_pdb.id, receptor_pdbqt.id],
        )
    )
    await db_session.commit()

    sync_response = await api_client.post(
        f"/api/v1/workflows/runs/{run['id']}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )
    assert sync_response.status_code == 200
    synced = sync_response.json()["data"]
    synced_prep_state = synced["node_states"]["tool-prep"]
    synced_docking_state = synced["node_states"]["tool-docking"]
    assert synced_prep_state["status"] == "success"
    assert synced_prep_state["standard_artifacts"]["file_ids_by_artifact_ref"] == {
        "prepared_protein": [prepared_pdb.id, receptor_pdbqt.id]
    }
    assert synced_docking_state["status"] == "waiting_task"
    assert synced_docking_state["input_file_ids"] == [prepared_pdb.id, receptor_pdbqt.id]
    assert synced_docking_state["params"]["builtin_inputs"] == {
        "protein_structure@1": prepared_pdb.id
    }
