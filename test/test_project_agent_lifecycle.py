"""Project-scoped AIDD Agent lifecycle tests."""

from __future__ import annotations

import hashlib

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.execution.contracts import ExecutionHandle, ExecutionState
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
from app.models.tool_packages import ToolPackage, ToolPackageVersion
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
        semantic_type="protein_pdb",
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
    )
    project_agent_db.add(protein)

    package = ToolPackage(
        owner_id=user.id,
        slug="lvpocket-pocket-prediction",
        name="LVpocket",
        status="published",
    )
    project_agent_db.add(package)
    await project_agent_db.flush()
    package_version = ToolPackageVersion(
        package_id=package.id,
        version="1.0.0",
        manifest={
            "variants": [
                {
                    "name": "nvidia-cuda",
                    "executor_types": ["remote_job"],
                    "resources": {"devices": ["nvidia.com/gpu"]},
                }
            ]
        },
        manifest_digest="a" * 64,
        is_signed=True,
        validation_status="valid",
    )
    project_agent_db.add(package_version)
    await project_agent_db.flush()
    package.current_version_id = package_version.id
    artifact.latest_version_id = protein.id
    await project_agent_db.commit()
    return {
        "user": user,
        "project": project,
        "conversation": conversation,
        "protein": protein,
        "package_version": package_version,
    }


class RecordingExecutionPort:
    def __init__(self) -> None:
        self.requests = []

    async def submit(self, request):
        self.requests.append(request)
        return ExecutionHandle(execution_id="execution-1", state=ExecutionState.QUEUED)


def test_legacy_agent_response_keeps_contract_and_adds_deprecation_metadata():
    from app.api.v1.agents import _legacy_success_response

    response = _legacy_success_response(data={"id": "run-1"}, message="created")

    assert response["code"] == 200
    assert response["message"] == "created"
    assert response["data"] == {"id": "run-1"}
    assert response["meta"] == {
        "deprecated": True,
        "replacement": "/api/v1/projects/{project_id}/conversations",
    }


@pytest.mark.asyncio
async def test_missing_protein_publishes_input_required_without_execution(
    project_agent_db: AsyncSession,
    project_context: dict,
):
    from app.agents.aidd.project_service import ProjectAgentService

    port = RecordingExecutionPort()
    service = ProjectAgentService(project_agent_db, execution_port=port)
    result = await service.create_plan(
        project_id=project_context["project"].id,
        conversation_id=project_context["conversation"].id,
        user=project_context["user"],
        goal="Find pockets",
        protein_artifact_version_id=None,
    )

    assert result.plan_version is None
    assert result.run.status == "input_required"
    assert port.requests == []
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
):
    from app.agents.aidd.project_service import ProjectAgentService

    port = RecordingExecutionPort()
    service = ProjectAgentService(project_agent_db, execution_port=port)
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
    assert port.requests == []

    created.plan_version.status = "approved"
    project_agent_db.add(
        PlanDecision(
            plan_version_id=created.plan_version.id,
            reviewer_id=project_context["user"].id,
            decision="approve",
        )
    )
    await project_agent_db.commit()
    handle = await service.submit_approved_plan(
        plan_version_id=created.plan_version.id,
        user=project_context["user"],
    )

    assert handle.execution_id == "execution-1"
    assert len(port.requests) == 1
    request = port.requests[0]
    assert request.tool_package_version_id == project_context["package_version"].id
    assert request.inputs[0].artifact_version_id == project_context["protein"].id
    assert request.variant == "nvidia-cuda"
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


@pytest.mark.asyncio
async def test_completion_publishes_artifact_analysis_and_goal_edit_branches_plan(
    project_agent_db: AsyncSession,
    project_context: dict,
):
    from app.agents.aidd.project_service import ProjectAgentService

    service = ProjectAgentService(
        project_agent_db, execution_port=RecordingExecutionPort()
    )
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
