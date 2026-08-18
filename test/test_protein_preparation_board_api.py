"""Protein preparation research board API tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1 import protein_preparation
from app.database.base import Base
from app.models import artifacts as _artifacts  # noqa: F401
from app.models import files as _files  # noqa: F401
from app.models import projects as _projects  # noqa: F401
from app.models import statistics as _statistics  # noqa: F401
from app.models import tasks as _tasks  # noqa: F401
from app.models import tools as _tools  # noqa: F401
from app.models import users as _users  # noqa: F401
from app.models import workflows as _workflows  # noqa: F401
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.files import File as FileModel, FileSourceType
from app.models.projects import Organization, Project, ProjectMember
from app.models.tasks import Task, TaskOutput, TaskStatus
from app.models.tools import Tool, ToolProviderType, ToolReviewStatus, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.models.workflows import ResearchBoard
from app.schemas.protein_preparation import ProteinPreparationRequest


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


async def _seed_board_with_protein_artifact(db: AsyncSession):
    owner = User(
        email="protein-board-owner@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    system_user = User(
        email="aidd-system@example.com",
        password_hash="hashed-password",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add_all([owner, system_user])
    await db.flush()
    organization = Organization(name="Protein Prep Lab", slug="protein-prep-lab")
    db.add(organization)
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name="Protein Prep Project",
        status="active",
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))

    artifact = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure@1",
        standard_type="protein_structure",
        standard_version=1,
        name="1ABC",
    )
    db.add(artifact)
    await db.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename="1ABC.pdb",
        content_type="chemical/x-pdb",
        size_bytes=24,
        sha256="a" * 64,
        storage_key="/tmp/1ABC.pdb",
        status="available",
    )
    file_record = FileModel(
        project_id=project.id,
        owner_id=owner.id,
        filename="1ABC.pdb",
        content_type="chemical/x-pdb",
        size_bytes=24,
        sha256="a" * 64,
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

    board = ResearchBoard(
        project_id=project.id,
        owner_id=owner.id,
        name="Protein board",
        content={
            "nodes": [
                {
                    "id": "artifact-protein",
                    "type": "artifact",
                    "position": {"x": 0, "y": 0},
                    "artifact_id": artifact.id,
                }
            ],
            "edges": [],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
        version=1,
    )
    db.add(board)
    await db.commit()
    return owner, system_user, board, artifact, version, file_record


@pytest.mark.asyncio
async def test_start_protein_preparation_creates_board_node_and_task(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, system_user, board, artifact, version, file_record = await _seed_board_with_protein_artifact(
        db_session
    )
    scheduled: list[dict] = []

    async def fake_create_and_schedule_tool_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append(
            {
                "params": task_data.params,
                "file_ids": task_data.file_ids,
                "input_bindings": task_data.input_bindings,
                "tool_id": task_data.tool_id,
            }
        )
        return SimpleNamespace(id="task-prep-1")

    monkeypatch.setattr(protein_preparation.settings, "AIDD_SYSTEM_USER_ID", system_user.id)
    monkeypatch.setattr(
        protein_preparation,
        "create_and_schedule_tool_task",
        fake_create_and_schedule_tool_task,
    )

    response = await protein_preparation.start_protein_preparation(
        board.id,
        ProteinPreparationRequest(
            artifact_id=artifact.id,
            source_node_id="artifact-protein",
            position={"x": 320, "y": 0},
        ),
        owner,
        db_session,
    )

    data = response["data"]
    node = data["preparation_node"]
    edge = data["edge"]
    assert data["task_id"] == "task-prep-1"
    assert node["type"] == "tool"
    assert node["task_id"] == "task-prep-1"
    assert node["status"] == "pending"
    assert edge["source"] == "artifact-protein"
    assert edge["target"] == node["id"]
    assert scheduled[0]["params"]["builtin_inputs"] == {
        "protein_structure@1": file_record.id
    }
    assert scheduled[0]["params"]["options"]["ph"] == 7.4
    assert scheduled[0]["input_bindings"] == {"protein": version.id}

    await db_session.refresh(board)
    content = board.content
    assert board.version == 2
    assert any(item.get("id") == node["id"] for item in content["nodes"])
    assert any(item.get("id") == edge["id"] for item in content["edges"])


@pytest.mark.asyncio
async def test_sync_protein_preparation_adds_prepared_artifact_node(
    db_session: AsyncSession,
) -> None:
    owner, system_user, board, _artifact, _version, _file_record = await _seed_board_with_protein_artifact(
        db_session
    )
    tool = Tool(
        owner_id=system_user.id,
        name="Protein Preparation",
        slug="builtin-protein-preparation-sync-test",
        status=ToolStatus.PUBLISHED.value,
        provider_type=ToolProviderType.PLATFORM.value,
        review_status=ToolReviewStatus.NOT_REQUIRED.value,
    )
    db_session.add(tool)
    await db_session.flush()
    tool_version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "builtin", "builtin_slug": "builtin-protein-preparation"},
        is_active=True,
    )
    db_session.add(tool_version)
    await db_session.flush()
    tool.current_version_id = tool_version.id
    task = Task(
        id="task-prep-sync",
        user_id=owner.id,
        tool_id=tool.id,
        tool_version_id=tool_version.id,
        status=TaskStatus.SUCCESS.value,
        extra_data={"project_id": board.project_id},
    )
    prepared_artifact = Artifact(
        project_id=board.project_id,
        created_by=owner.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure@1",
        standard_type="protein_structure",
        standard_version=1,
        name="Prepared 1ABC",
        source_task_id=task.id,
    )
    db_session.add_all([task, prepared_artifact])
    await db_session.flush()
    db_session.add(
        TaskOutput(
            task_id=task.id,
            result={
                "standard_artifacts": {
                    "artifact_ids_by_ref": {"prepared_protein": prepared_artifact.id},
                    "artifact_version_ids_by_ref": {"prepared_protein": "version-prepared"},
                    "file_ids_by_artifact_ref": {"prepared_protein": ["file-prepared"]},
                }
            },
            file_ids=["file-prepared"],
        )
    )
    board.content = {
        "nodes": [
            *board.content["nodes"],
            {
                "id": "protein-preparation:task-prep-sync",
                "type": "tool",
                "position": {"x": 320, "y": 0},
                "tool_id": tool.id,
                "task_id": task.id,
                "status": "pending",
            },
        ],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    await db_session.commit()

    response = await protein_preparation.sync_protein_preparation(
        board.id,
        task.id,
        owner,
        db_session,
    )

    data = response["data"]
    assert data["preparation_node"]["status"] == "success"
    assert data["preparation_node"]["output_artifact_id"] == prepared_artifact.id
    assert data["artifact_node"]["type"] == "artifact"
    assert data["artifact_node"]["artifact_id"] == prepared_artifact.id
    assert data["edge"]["source"] == "protein-preparation:task-prep-sync"
    assert data["edge"]["target"] == data["artifact_node"]["id"]

    await db_session.refresh(board)
    assert any(
        node.get("artifact_id") == prepared_artifact.id
        for node in board.content["nodes"]
    )
