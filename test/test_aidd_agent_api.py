"""AIDD agent API tests."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

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
from app.models.agent import AgentRun, AgentRunStep  # noqa: E402
from app.models.files import File as FileModel, FileSourceType  # noqa: E402
from app.models.system_settings import ModelService  # noqa: E402
from app.models.tasks import Task, TaskOutput, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.models.workflows import WorkflowRun, WorkflowTemplate  # noqa: E402


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
async def current_user(db_session: AsyncSession) -> User:
    return await create_user(db_session, email="owner@example.com")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await create_user(db_session, email="other@example.com")


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = await create_user(db_session, email="admin@example.com")
    user.role = UserRole.ADMIN.value
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    current_user: User,
    other_user: User,
    admin_user: User,
):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == "Bearer owner-token":
            return current_user
        if authorization == "Bearer other-token":
            return other_user
        if authorization == "Bearer admin-token":
            return admin_user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


async def create_tool(
    db_session: AsyncSession,
    owner: User,
    *,
    slug: str,
    name: str,
) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name=name,
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "ssh_job", "input_schema": {"type": "object", "properties": {}}},
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest_asyncio.fixture
async def aidd_tools(db_session: AsyncSession, current_user: User) -> dict[str, Tool]:
    db_session.add(
        ModelService(
            name="Default Planner",
            provider_type="openai_compatible",
            base_url="https://api.example.com/v1",
            api_key_encrypted=None,
            model_name="planner",
            is_default=True,
            is_enabled=True,
        )
    )
    lvpocket = await create_tool(
        db_session,
        current_user,
        slug="lvpocket-pocket-prediction",
        name="LVpocket Pocket Prediction",
    )
    gcdm = await create_tool(
        db_session,
        current_user,
        slug="gcdm-pocket-generation",
        name="STD-Diff",
    )
    msign = await create_tool(
        db_session,
        current_user,
        slug="msign-affinity-prediction",
        name="MSIGN",
    )
    return {lvpocket.slug: lvpocket, gcdm.slug: gcdm, msign.slug: msign}


async def fake_structured_plan(service, prompt):
    return """
    {
      "intent": "generate_molecules_from_protein",
      "reasoning_summary": "识别到蛋白结构输入，先选择口袋预测能力，再把预测口袋用于分子生成。",
      "analysis_trace": [
        "输入判断：识别为蛋白结构文件。",
        "工具发现：发现口袋预测和分子生成两个可用能力。",
        "工具编排：先运行口袋预测，再把口袋产物交给分子生成。"
      ],
      "reasoning_content": "raw hidden chain should not be persisted",
      "steps": [
        {
          "step_key": "pocket_prediction",
          "capability": "pocket_prediction",
          "tool_slug": "lvpocket-pocket-prediction",
          "inputs": {"protein_pdb": "agent_input"},
          "params": {}
        },
        {
          "step_key": "molecule_generation",
          "capability": "molecule_generation",
          "tool_slug": "gcdm-pocket-generation",
          "inputs": {"pocket_pdb": "step:pocket_prediction:pocket_pdb"},
          "params": {}
        }
      ]
    }
    """


@pytest_asyncio.fixture
async def protein_file(db_session: AsyncSession, current_user: User) -> FileModel:
    file_record = FileModel(
        owner_id=current_user.id,
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


@pytest_asyncio.fixture
async def ligand_file(db_session: AsyncSession, current_user: User) -> FileModel:
    file_record = FileModel(
        owner_id=current_user.id,
        filename="ligand.pdb",
        content_type="chemical/x-pdb",
        size_bytes=96,
        sha256=hashlib.sha256(b"ligand").hexdigest(),
        source_type=FileSourceType.UPLOAD.value,
        storage_path="/tmp/ligand.pdb",
        is_public=False,
    )
    db_session.add(file_record)
    await db_session.commit()
    await db_session.refresh(file_record)
    return file_record


async def fake_affinity_plan(service, prompt):
    return """
    {
      "intent": "predict_affinity_from_uploaded_complex",
      "reasoning_summary": "识别到蛋白和配体输入，直接运行亲和力预测。",
      "analysis_trace": [
        "输入判断：识别为蛋白结构和配体结构文件。",
        "工具发现：发现亲和力预测能力。",
        "工具编排：把两个上传文件绑定到同一步骤。"
      ],
      "steps": [
        {
          "step_key": "affinity_prediction",
          "capability": "affinity_prediction",
          "tool_slug": "msign-affinity-prediction",
          "inputs": {
            "protein_pdb": "agent_input:protein_pdb",
            "ligand_pdb": "agent_input:ligand_pdb"
          },
          "params": {"device": "cpu"}
        }
      ]
    }
    """


@pytest.mark.asyncio
async def test_create_workflow_draft_does_not_create_runs_or_tasks(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    aidd_tools: dict[str, Tool],
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.agents.aidd.llm_client.request_structured_plan",
        fake_structured_plan,
    )

    response = await api_client.post(
        "/api/v1/agents/aidd/workflow-drafts",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "message": "上传蛋白后探索口袋并生成分子",
            "input_file_id": protein_file.id,
            "requested_outputs": ["generated_ligand"],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "上传蛋白后探索口袋并生成分子"
    assert data["intent"] == "generate_molecules_from_protein"
    assert data["input_files"] == {"protein_pdb": protein_file.id}
    assert data["requested_outputs"] == ["generated_ligand"]
    assert data["reasoning_summary"].startswith("识别到蛋白结构输入")
    assert [node["id"] for node in data["definition"]["nodes"]] == [
        "input-protein_pdb",
        "pocket_prediction",
        "molecule_generation",
    ]
    pocket_node = data["definition"]["nodes"][1]
    assert pocket_node["tool_id"] == aidd_tools["lvpocket-pocket-prediction"].id
    assert pocket_node["tool_version"]["id"]

    for model in (AgentRun, AgentRunStep, Task, WorkflowTemplate, WorkflowRun):
        count = await db_session.scalar(select(func.count()).select_from(model))
        assert count == 0


@pytest.mark.asyncio
async def test_create_agent_run_from_protein_creates_run_and_first_step(
    api_client: httpx.AsyncClient,
    aidd_tools: dict[str, Tool],
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        return SimpleNamespace(
            id="task-pocket",
            tool_id=task_data.tool_id,
            tool_version_id=None,
            status="PENDING",
            progress=0,
        )

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )
    monkeypatch.setattr(
        "app.agents.aidd.llm_client.request_structured_plan",
        fake_structured_plan,
    )

    response = await api_client.post(
        "/api/v1/agents/aidd/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "message": "上传蛋白后探索口袋并生成分子",
            "input_file_id": protein_file.id,
            "requested_outputs": ["generated_ligand"],
            "params": {"generation_count": 8},
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["intent"] == "generate_molecules_from_protein"
    assert data["status"] == "waiting_task"
    assert data["plan"]["reasoning_summary"] == "识别到蛋白结构输入，先选择口袋预测能力，再把预测口袋用于分子生成。"
    assert data["plan"]["analysis_trace"] == [
        "输入判断：识别为蛋白结构文件。",
        "工具发现：发现口袋预测和分子生成两个可用能力。",
        "工具编排：先运行口袋预测，再把口袋产物交给分子生成。",
    ]
    assert "reasoning_content" not in data["plan"]
    assert data["steps"][0]["tool_slug"] == "lvpocket-pocket-prediction"
    assert data["steps"][0]["task_id"] == "task-pocket"


@pytest.mark.asyncio
async def test_create_agent_run_accepts_multiple_semantic_input_files(
    api_client: httpx.AsyncClient,
    aidd_tools: dict[str, Tool],
    protein_file: FileModel,
    ligand_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
):
    created_payloads = []

    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        created_payloads.append(task_data)
        return SimpleNamespace(
            id="task-affinity",
            tool_id=task_data.tool_id,
            tool_version_id=None,
            status="PENDING",
            progress=0,
        )

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )
    monkeypatch.setattr(
        "app.agents.aidd.llm_client.request_structured_plan",
        fake_affinity_plan,
    )

    response = await api_client.post(
        "/api/v1/agents/aidd/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "message": "上传蛋白和配体预测亲和力",
            "input_file_id": protein_file.id,
            "input_files": {
                "protein_pdb": protein_file.id,
                "ligand_pdb": ligand_file.id,
            },
            "requested_outputs": ["affinity_report"],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["input_files"] == {
        "protein_pdb": protein_file.id,
        "ligand_pdb": ligand_file.id,
    }
    assert data["steps"][0]["tool_slug"] == "msign-affinity-prediction"
    assert data["steps"][0]["input_file_ids"] == [protein_file.id, ligand_file.id]
    assert created_payloads[0].file_ids == [protein_file.id, ligand_file.id]
    assert created_payloads[0].params["input_files"] == {
        "protein_pdb": "input/protein.pdb",
        "ligand_pdb": "input/ligand.pdb",
    }


@pytest.mark.asyncio
async def test_create_agent_run_classifies_uploaded_file_ids_without_semantic_labels(
    api_client: httpx.AsyncClient,
    aidd_tools: dict[str, Tool],
    protein_file: FileModel,
    ligand_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
):
    created_payloads = []

    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        created_payloads.append(task_data)
        return SimpleNamespace(
            id="task-affinity-auto",
            tool_id=task_data.tool_id,
            tool_version_id=None,
            status="PENDING",
            progress=0,
        )

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )
    monkeypatch.setattr(
        "app.agents.aidd.llm_client.request_structured_plan",
        fake_affinity_plan,
    )

    response = await api_client.post(
        "/api/v1/agents/aidd/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "message": "上传这两个文件，预测蛋白和配体的亲和力",
            "input_file_ids": [protein_file.id, ligand_file.id],
            "requested_outputs": ["affinity_report"],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["input_file_id"] == protein_file.id
    assert data["input_files"] == {
        "protein_pdb": protein_file.id,
        "ligand_pdb": ligand_file.id,
    }
    assert data["plan"]["input_files"] == data["input_files"]
    assert data["steps"][0]["input_file_ids"] == [protein_file.id, ligand_file.id]
    assert created_payloads[0].file_ids == [protein_file.id, ligand_file.id]


@pytest.mark.asyncio
async def test_other_user_cannot_read_agent_run(
    api_client: httpx.AsyncClient,
    aidd_tools: dict[str, Tool],
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        return SimpleNamespace(id="task-pocket", tool_id=task_data.tool_id)

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )
    monkeypatch.setattr(
        "app.agents.aidd.llm_client.request_structured_plan",
        fake_structured_plan,
    )

    create_response = await api_client.post(
        "/api/v1/agents/aidd/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "message": "上传蛋白后探索口袋并生成分子",
            "input_file_id": protein_file.id,
        },
    )
    run_id = create_response.json()["data"]["id"]

    response = await api_client.get(
        f"/api/v1/agents/aidd/runs/{run_id}",
        headers={"Authorization": "Bearer other-token"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unsupported_input_type_is_rejected(
    api_client: httpx.AsyncClient,
    protein_file: FileModel,
):
    response = await api_client.post(
        "/api/v1/agents/aidd/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "message": "做一下分析",
            "input_file_id": protein_file.id,
            "input_type": "ligand_sdf",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_can_list_all_agent_runs(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    current_user: User,
    other_user: User,
):
    db_session.add_all(
        [
            AgentRun(
                user_id=current_user.id,
                message="owner run",
                intent="pocket_exploration",
                status="success",
                input_type="protein_pdb",
                requested_outputs=["generated_ligand"],
                plan={},
            ),
            AgentRun(
                user_id=other_user.id,
                message="other run",
                intent="molecule_generation",
                status="success",
                input_type="pocket_pdb",
                requested_outputs=["generated_ligand"],
                plan={},
            ),
        ]
    )
    await db_session.commit()

    response = await api_client.get(
        "/api/v1/agents/aidd/runs",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert {item["message"] for item in data["items"]} == {"owner run", "other run"}


@pytest.mark.asyncio
async def test_owner_can_delete_agent_run_history(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    current_user: User,
):
    run = AgentRun(
        user_id=current_user.id,
        message="delete me",
        intent="pocket_exploration",
        status="success",
        input_type="protein_pdb",
        requested_outputs=["generated_ligand"],
        plan={},
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    response = await api_client.delete(
        f"/api/v1/agents/aidd/runs/{run.id}",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == run.id
    assert await db_session.get(AgentRun, run.id) is None


@pytest.mark.asyncio
async def test_owner_can_cascade_delete_agent_run_tasks_and_artifacts(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    current_user: User,
    aidd_tools: dict[str, Tool],
    protein_file: FileModel,
):
    output_file = FileModel(
        owner_id=current_user.id,
        filename="generated.sdf",
        content_type="chemical/x-mdl-sdfile",
        size_bytes=256,
        sha256=hashlib.sha256(b"generated").hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path="/tmp/generated.sdf",
        is_public=False,
    )
    db_session.add(output_file)
    await db_session.flush()

    tool = aidd_tools["gcdm-pocket-generation"]
    task = Task(
        user_id=current_user.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        status=TaskStatus.SUCCESS.value,
    )
    db_session.add(task)
    await db_session.flush()

    db_session.add(
        TaskOutput(
            task_id=task.id,
            result={"files": [output_file.id]},
            file_ids=[output_file.id],
            output_type="file",
        )
    )

    run = AgentRun(
        user_id=current_user.id,
        message="cascade delete me",
        intent="molecule_generation",
        status="success",
        input_type="protein_pdb",
        input_file_id=protein_file.id,
        requested_outputs=["generated_ligand"],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()

    db_session.add(
        AgentRunStep(
            agent_run_id=run.id,
            step_key="molecule_generation",
            tool_slug="gcdm-pocket-generation",
            task_id=task.id,
            status="success",
            sort_order=0,
            output_file_ids=[output_file.id],
        )
    )
    await db_session.commit()

    response = await api_client.delete(
        f"/api/v1/agents/aidd/runs/{run.id}",
        params={"cascade": "true"},
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == run.id
    assert data["deleted_tasks"] == 1
    assert data["deleted_artifacts"] == 1
    assert await db_session.get(AgentRun, run.id) is None
    assert await db_session.get(Task, task.id) is None
    assert await db_session.get(FileModel, output_file.id) is None
    assert await db_session.get(FileModel, protein_file.id) is not None


@pytest.mark.asyncio
async def test_sync_agent_run_endpoint_reconciles_waiting_steps(
    api_client: httpx.AsyncClient,
    aidd_tools: dict[str, Tool],
    protein_file: FileModel,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        return SimpleNamespace(id="task-pocket", tool_id=task_data.tool_id)

    reconciled: list[str | None] = []

    async def fake_reconcile(db, *, run_id=None):
        reconciled.append(run_id)
        return 1

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )
    monkeypatch.setattr(
        "app.agents.aidd.llm_client.request_structured_plan",
        fake_structured_plan,
    )
    monkeypatch.setattr(
        "app.api.v1.agents.reconcile_waiting_agent_steps",
        fake_reconcile,
    )

    create_response = await api_client.post(
        "/api/v1/agents/aidd/runs",
        headers={"Authorization": "Bearer owner-token"},
        json={
            "message": "上传蛋白后探索口袋并生成分子",
            "input_file_id": protein_file.id,
        },
    )
    run_id = create_response.json()["data"]["id"]

    response = await api_client.post(
        f"/api/v1/agents/aidd/runs/{run_id}/sync",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 200
    assert reconciled == [run_id]


@pytest.mark.asyncio
async def test_cancel_agent_run_cancels_linked_platform_task(
    db_session: AsyncSession,
    current_user: User,
    aidd_tools: dict[str, Tool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.aidd.service import cancel_agent_run

    tool = aidd_tools["gcdm-pocket-generation"]
    task = Task(
        user_id=current_user.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        status=TaskStatus.PENDING.value,
    )
    db_session.add(task)
    await db_session.flush()
    run = AgentRun(
        user_id=current_user.id,
        message="cancel me",
        intent="molecule_generation",
        status="waiting_task",
        input_type="protein_pdb",
        requested_outputs=[],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(
        AgentRunStep(
            agent_run_id=run.id,
            step_key="molecule_generation",
            tool_slug=tool.slug,
            task_id=task.id,
            status="waiting_task",
            sort_order=0,
        )
    )
    await db_session.commit()

    canceled_task_ids: list[str] = []

    async def fake_cancel_task(db, *, task, current_user):
        canceled_task_ids.append(task.id)
        task.status = TaskStatus.CANCELED.value

    monkeypatch.setattr("app.agents.aidd.service.cancel_platform_task", fake_cancel_task)

    canceled_run = await cancel_agent_run(db_session, current_user=current_user, run_id=run.id)

    assert canceled_task_ids == [task.id]
    assert canceled_run.status == "canceled"


@pytest.mark.asyncio
async def test_claim_ready_agent_step_is_atomic(
    db_session: AsyncSession,
    current_user: User,
) -> None:
    from app.agents.aidd.service import claim_agent_step_for_dispatch

    run = AgentRun(
        user_id=current_user.id,
        message="claim me",
        intent="test",
        status="pending",
        input_type="protein_pdb",
        requested_outputs=[],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    step = AgentRunStep(
        agent_run_id=run.id,
        step_key="only_step",
        tool_slug="test-tool",
        status="pending",
        sort_order=0,
    )
    db_session.add(step)
    await db_session.commit()

    assert await claim_agent_step_for_dispatch(db_session, step.id) is True
    assert await claim_agent_step_for_dispatch(db_session, step.id) is False
