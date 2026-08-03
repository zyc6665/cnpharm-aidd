"""AIDD project-to-board vertical slice regression test."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.research_boards import create_research_board
from app.config import settings as config_settings
from app.database.base import Base
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.conversations import (
    AgentEvent,
    Conversation,
    ConversationBranch,
    PlanDecision,
)
from app.models.projects import Organization, Project, ProjectMember
from app.models.tasks import Task
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.schemas.research_boards import ResearchBoardCreate


@pytest_asyncio.fixture
async def vertical_db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, autoflush=False
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def _lvpocket_tool_package_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "lvpocket-pocket-prediction",
            "name": "LVpocket",
            "version": "1.0.0",
        },
        "artifacts": {
            "inputs": [{"name": "protein", "type": "protein_structure@1", "required": True}],
            "outputs": [{"name": "pocket", "type": "binding_pocket@1", "required": True}],
        },
        "runtime": {
            "python": "3.10",
            "executor_support": ["ssh_docker_exec"],
            "selection_policy": "test runtime fixture",
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": "registry.example/sciminer/lvpocket:1.0.0",
                    "image_digest": "sha256:test",
                },
                "fallback": {
                    "kind": "conda_pack",
                    "uri": "artifacts://model-envs/lvpocket/1.0.0/conda-env.tar.gz",
                    "sha256": "test",
                },
            },
            "weights": {
                "manifest_uri": "artifacts://model-weights/lvpocket/1.0.0/weights.json",
                "manifest_sha256": "test",
            },
            "cache_policy": {
                "key_fields": ["metadata.slug", "metadata.version"],
                "mutable_host_paths_forbidden": True,
            },
        },
        "variants": [
            {
                "name": "nvidia-cuda",
                "accelerator": "nvidia_cuda",
                "executor_types": ["remote_job"],
                "entrypoint": ["runner/platform_run_v2.sh"],
            }
        ],
    }


@pytest.fixture
def vertical_direct_runner(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    runner = SimpleNamespace(
        scheduled=[],
        schedule_task=lambda task_id, tool_version_id: runner.scheduled.append(
            (task_id, tool_version_id)
        ),
    )
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    return runner


async def _seed_project_context(
    db: AsyncSession,
) -> tuple[User, Project, Conversation, ArtifactVersion, ToolVersion]:
    user = User(
        email="vertical-owner@example.com",
        password_hash="hashed-password",
        display_name="Vertical Owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    organization = Organization(name="Vertical Lab", slug="vertical-lab")
    db.add_all([user, organization])
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=user.id,
        name="LVpocket vertical slice",
        goal="Identify ligandable pockets",
        status="active",
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    conversation = Conversation(
        project_id=project.id,
        created_by=user.id,
        title="Pocket analysis",
    )
    protein = Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        standard_type="protein_structure",
        standard_version=1,
        name="target.pdb",
    )
    db.add_all([conversation, protein])
    await db.flush()
    db.add(
        ConversationBranch(
            conversation_id=conversation.id,
            created_by=user.id,
            title="主分支",
            is_root=True,
        )
    )
    protein_version = ArtifactVersion(
        artifact_id=protein.id,
        created_by=user.id,
        version=1,
        filename="target.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"protein").hexdigest(),
        storage_key="projects/vertical/target.pdb",
        status="available",
        validation_status="passed",
        manifest_json={"type": "protein_structure@1"},
    )
    tool = Tool(
        owner_id=user.id,
        name="LVpocket",
        slug="lvpocket-pocket-prediction",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        gpu_required=True,
    )
    db.add_all([protein_version, tool])
    await db.flush()
    tool_version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "ssh_job",
            "tool_package_manifest": _lvpocket_tool_package_manifest(),
        },
        is_active=True,
    )
    db.add(tool_version)
    await db.flush()
    protein.latest_version_id = protein_version.id
    tool.current_version_id = tool_version.id
    await db.commit()
    return user, project, conversation, protein_version, tool_version


@pytest.mark.asyncio
async def test_approved_lvpocket_result_can_be_referenced_from_its_project_board(
    vertical_db: AsyncSession,
    vertical_direct_runner: SimpleNamespace,
):
    from app.agents.aidd.project_service import ProjectAgentService

    user, project, conversation, protein_version, tool_version = await _seed_project_context(
        vertical_db
    )
    service = ProjectAgentService(vertical_db, direct_runner=vertical_direct_runner)

    created = await service.create_plan(
        project_id=project.id,
        conversation_id=conversation.id,
        user=user,
        goal="Find ligandable pockets in chain A",
        protein_artifact_version_id=protein_version.id,
    )
    assert created.plan_version is not None
    created.plan_version.status = "approved"
    vertical_db.add(
        PlanDecision(
            plan_version_id=created.plan_version.id,
            reviewer_id=user.id,
            decision="approve",
        )
    )
    await vertical_db.commit()

    submission = await service.submit_approved_plan(
        plan_version_id=created.plan_version.id,
        user=user,
    )
    task = await vertical_db.get(Task, submission.task.id)
    assert task is not None
    assert task.tool_version_id == tool_version.id
    assert task.extra_data["input_bindings"] == {"protein": protein_version.id}
    assert vertical_direct_runner.scheduled == [(task.id, tool_version.id)]

    pocket = Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type="pocket_result",
        semantic_type="pocket_result",
        name="lvpocket-result.json",
    )
    vertical_db.add(pocket)
    await vertical_db.flush()
    pocket_version = ArtifactVersion(
        artifact_id=pocket.id,
        created_by=user.id,
        version=1,
        filename="lvpocket-result.json",
        content_type="application/json",
        size_bytes=256,
        sha256=hashlib.sha256(b"pocket-result").hexdigest(),
        storage_key="projects/vertical/lvpocket-result.json",
        status="available",
    )
    vertical_db.add(pocket_version)
    await vertical_db.flush()
    pocket.latest_version_id = pocket_version.id
    await vertical_db.commit()
    await service.complete_run(
        run_id=created.run.id,
        artifact_version_ids=[pocket_version.id],
        summary="Fake LVpocket run identified three candidate pockets.",
    )

    board = await create_research_board(
        ResearchBoardCreate(
            name="Pocket evidence",
            project_id=project.id,
            content={
                "nodes": [
                    {
                        "id": "pocket-result",
                        "type": "artifact",
                        "position": {"x": 0, "y": 0},
                        "artifact_id": pocket.id,
                    }
                ],
                "edges": [],
                "viewport": {"x": 0, "y": 0, "zoom": 1},
            },
        ),
        user,
        vertical_db,
    )

    events = (
        (
            await vertical_db.execute(
                select(AgentEvent)
                .where(AgentEvent.agent_run_id == created.run.id)
                .order_by(AgentEvent.sequence)
            )
        )
        .scalars()
        .all()
    )
    assert [event.event_type for event in events] == [
        "plan_created",
        "approval_required",
        "execution_submitted",
        "execution_queued",
        "artifact_completed",
        "analysis_summary",
    ]
    assert board["data"]["project_id"] == project.id
    assert board["data"]["content"]["nodes"][0]["artifact_id"] == pocket.id
