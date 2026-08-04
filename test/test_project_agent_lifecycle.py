"""Project-scoped AIDD Agent lifecycle tests."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.config import settings as config_settings
from app.models.agent import AgentRun
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.conversations import (
    AgentEvent,
    Conversation,
    ConversationBranch,
    PlanDecision,
    PlanVersion,
)
from app.models.projects import Organization, Project, ProjectMember
from app.models.tasks import Task
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def project_agent_db() -> AsyncSession:
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
def project_direct_runner(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    runner = SimpleNamespace(
        scheduled=[],
        schedule_task=lambda task_id, tool_version_id: runner.scheduled.append(
            (task_id, tool_version_id)
        ),
    )
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    return runner


@pytest_asyncio.fixture
async def project_context(project_agent_db: AsyncSession) -> dict:
    user = User(
        email="project-agent@example.com",
        password_hash="hashed-password",
        display_name="Project Agent Owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    project_agent_db.add(user)
    await project_agent_db.flush()
    organization = Organization(name="AIDD Lab", slug="aidd-lab")
    project_agent_db.add(organization)
    await project_agent_db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=user.id,
        name="Pocket study",
        goal="Identify ligandable pockets",
        status="active",
    )
    project_agent_db.add(project)
    await project_agent_db.flush()
    project_agent_db.add(
        ProjectMember(project_id=project.id, user_id=user.id, role="owner")
    )
    conversation = Conversation(
        project_id=project.id,
        created_by=user.id,
        title="Pocket research",
    )
    project_agent_db.add(conversation)
    await project_agent_db.flush()
    project_agent_db.add(
        ConversationBranch(
            conversation_id=conversation.id,
            created_by=user.id,
            title="主分支",
            is_root=True,
        )
    )

    artifact = Artifact(
        project_id=project.id,
        created_by=user.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        standard_type="protein_structure",
        standard_version=1,
        name="protein.pdb",
    )
    project_agent_db.add(artifact)
    await project_agent_db.flush()
    protein = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=user.id,
        version=1,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"protein").hexdigest(),
        storage_key="projects/pocket-study/protein.pdb",
        status="available",
        validation_status="passed",
        manifest_json={"type": "protein_structure@1"},
    )
    project_agent_db.add(protein)

    tool = Tool(
        owner_id=user.id,
        name="LVpocket",
        slug="lvpocket-pocket-prediction",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        gpu_required=True,
    )
    project_agent_db.add(tool)
    await project_agent_db.flush()
    tool_version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "ssh_job",
            "tool_package_manifest": _lvpocket_tool_package_manifest(),
        },
        is_active=True,
    )
    project_agent_db.add(tool_version)
    await project_agent_db.flush()
    tool.current_version_id = tool_version.id
    artifact.latest_version_id = protein.id
    await project_agent_db.commit()
    return {
        "user": user,
        "project": project,
        "conversation": conversation,
        "protein": protein,
        "tool_version": tool_version,
    }


def test_legacy_agent_shutdown_detail_points_to_project_conversations():
    from app.api.v1.agents import LEGACY_AGENT_GONE_DETAIL

    assert LEGACY_AGENT_GONE_DETAIL == {
        "message": "旧 AIDD API 已下线，请使用项目会话 Agent Run 接口",
        "replacement": "/api/v1/projects/{project_id}/conversations",
    }


@pytest.mark.asyncio
async def test_missing_protein_publishes_input_required_without_execution(
    project_agent_db: AsyncSession,
    project_context: dict,
    project_direct_runner: SimpleNamespace,
):
    from app.agents.aidd.project_service import ProjectAgentService

    service = ProjectAgentService(project_agent_db, direct_runner=project_direct_runner)
    result = await service.create_plan(
        project_id=project_context["project"].id,
        conversation_id=project_context["conversation"].id,
        user=project_context["user"],
        goal="Find pockets",
        protein_artifact_version_id=None,
    )

    assert result.plan_version is None
    assert result.run.status == "input_required"
    assert project_direct_runner.scheduled == []
    events = (
        (
            await project_agent_db.execute(
                select(AgentEvent).where(AgentEvent.agent_run_id == result.run.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(event.sequence, event.event_type) for event in events] == [
        (1, "input_required")
    ]


@pytest.mark.asyncio
async def test_plan_is_immutable_and_approval_is_required_before_lvpocket_submission(
    project_agent_db: AsyncSession,
    project_context: dict,
    project_direct_runner: SimpleNamespace,
):
    from app.agents.aidd.project_service import ProjectAgentService

    service = ProjectAgentService(project_agent_db, direct_runner=project_direct_runner)
    created = await service.create_plan(
        project_id=project_context["project"].id,
        conversation_id=project_context["conversation"].id,
        user=project_context["user"],
        goal="Find pockets in chain A",
        protein_artifact_version_id=project_context["protein"].id,
    )
    original_content = dict(created.plan_version.content)

    with pytest.raises(HTTPException) as exc_info:
        await service.submit_approved_plan(
            plan_version_id=created.plan_version.id,
            user=project_context["user"],
    )
    assert exc_info.value.status_code == 409
    assert project_direct_runner.scheduled == []

    created.plan_version.status = "approved"
    project_agent_db.add(
        PlanDecision(
            plan_version_id=created.plan_version.id,
            reviewer_id=project_context["user"].id,
            decision="approve",
        )
    )
    await project_agent_db.commit()
    submission = await service.submit_approved_plan(
        plan_version_id=created.plan_version.id,
        user=project_context["user"],
    )

    assert submission.as_execution_payload()["task_id"] == submission.task.id
    task = await project_agent_db.get(Task, submission.task.id)
    assert task is not None
    assert task.project_id == project_context["project"].id
    assert task.tool_version_id == project_context["tool_version"].id
    assert task.extra_data["input_bindings"] == {
        "protein": project_context["protein"].id
    }
    assert project_direct_runner.scheduled == [
        (task.id, project_context["tool_version"].id)
    ]
    await project_agent_db.refresh(created.plan_version)
    assert created.plan_version.content == original_content
    events = (
        (
            await project_agent_db.execute(
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
    ]
    assert [event.sequence for event in events] == [1, 2, 3, 4]
    assert events[-2].payload["task_id"] == task.id
    assert events[-1].payload["task_id"] == task.id


@pytest.mark.asyncio
async def test_completion_publishes_artifact_analysis_and_goal_edit_branches_plan(
    project_agent_db: AsyncSession,
    project_context: dict,
):
    from app.agents.aidd.project_service import ProjectAgentService

    service = ProjectAgentService(project_agent_db)
    created = await service.create_plan(
        project_id=project_context["project"].id,
        conversation_id=project_context["conversation"].id,
        user=project_context["user"],
        goal="Find pockets in chain A",
        protein_artifact_version_id=project_context["protein"].id,
    )
    original_content = dict(created.plan_version.content)
    branched = await service.branch_plan_for_goal(
        plan_version_id=created.plan_version.id,
        user=project_context["user"],
        goal="Find pockets in chain B",
    )

    assert branched.id != created.plan_version.id
    assert branched.version == created.plan_version.version + 1
    assert branched.content["parent_plan_version_id"] == created.plan_version.id
    assert branched.content["goal"] == "Find pockets in chain B"
    await project_agent_db.refresh(created.plan_version)
    assert created.plan_version.content == original_content

    await service.complete_run(
        run_id=created.run.id,
        artifact_version_ids=["pocket-artifact-v1"],
        summary="LVpocket identified three candidate pockets.",
    )
    await project_agent_db.refresh(created.run)
    assert created.run.status == "success"
    assert created.run.summary == "LVpocket identified three candidate pockets."
    events = (
        (
            await project_agent_db.execute(
                select(AgentEvent)
                .where(AgentEvent.agent_run_id == created.run.id)
                .order_by(AgentEvent.sequence)
            )
        )
        .scalars()
        .all()
    )
    assert [event.event_type for event in events][-2:] == [
        "artifact_completed",
        "analysis_summary",
    ]
    assert events[-1].payload["summary"] == created.run.summary
