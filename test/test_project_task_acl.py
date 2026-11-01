"""Project task ACL and filtering API tests."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1 import tasks as tasks_api  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.common.time import utcnow  # noqa: E402
from app.config import settings as config_settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import projects as _project_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _user_models  # noqa: F401,E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.tasks import Task, TaskInput, TaskLog, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402


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
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _create_user(db: AsyncSession, email: str, *, role: str = UserRole.USER.value) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        display_name=email.split("@")[0],
        role=role,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def users(db_session: AsyncSession) -> dict[str, User]:
    created = {
        "owner": await _create_user(db_session, "owner@example.com"),
        "editor": await _create_user(db_session, "editor@example.com"),
        "runner": await _create_user(db_session, "runner@example.com"),
        "viewer": await _create_user(db_session, "viewer@example.com"),
        "outsider": await _create_user(db_session, "outsider@example.com"),
        "admin": await _create_user(db_session, "admin@example.com", role=UserRole.ADMIN.value),
    }
    await db_session.commit()
    return created


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, users: dict[str, User]):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(authorization: str | None = Header(default=None)) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in users:
            return users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def published_tool(db_session: AsyncSession, users: dict[str, User]) -> Tool:
    tool = Tool(
        owner_id=users["owner"].id,
        name="Project Docking",
        slug="project-docking",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "python_script"},
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


async def _create_project_with_members(db: AsyncSession, users: dict[str, User]) -> Project:
    organization = Organization(name="Project Task Lab", slug="project-task-lab")
    db.add(organization)
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=users["owner"].id,
        name="Project task ACL",
        status="active",
    )
    db.add(project)
    await db.flush()
    db.add_all(
        [
            ProjectMember(project_id=project.id, user_id=users["owner"].id, role="owner"),
            ProjectMember(project_id=project.id, user_id=users["editor"].id, role="editor"),
            ProjectMember(project_id=project.id, user_id=users["runner"].id, role="runner"),
            ProjectMember(project_id=project.id, user_id=users["viewer"].id, role="viewer"),
        ]
    )
    await db.commit()
    await db.refresh(project)
    return project


async def _create_task(
    db: AsyncSession,
    *,
    user: User,
    tool: Tool,
    project_id: str,
    name: str,
    status: str,
) -> Task:
    task = Task(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        name=name,
        status=status,
        progress=25,
        extra_data={"project_id": project_id},
    )
    db.add(task)
    await db.flush()
    db.add(TaskInput(task_id=task.id, params={"seed": 1}, file_ids=[]))
    db.add(TaskLog(task_id=task.id, level="INFO", message=f"{name} log"))
    await db.commit()
    await db.refresh(task)
    return task


@pytest.mark.asyncio
async def test_project_task_list_detail_and_logs_use_project_membership(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    published_tool: Tool,
) -> None:
    project = await _create_project_with_members(db_session, users)
    task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Owner project task",
        status=TaskStatus.SUCCESS.value,
    )

    member_list_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer viewer"},
        params={"project_id": project.id},
    )
    personal_list_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer viewer"},
    )
    detail_response = await api_client.get(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": "Bearer viewer"},
    )
    logs_response = await api_client.get(
        f"/api/v1/tasks/{task.id}/logs",
        headers={"Authorization": "Bearer viewer"},
    )
    outsider_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer outsider"},
        params={"project_id": project.id},
    )

    assert member_list_response.status_code == 200
    assert [item["id"] for item in member_list_response.json()["data"]["items"]] == [task.id]
    assert personal_list_response.status_code == 200
    assert personal_list_response.json()["data"]["items"] == []
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["project_id"] == project.id
    assert logs_response.status_code == 200
    assert logs_response.json()["data"]["items"][0]["message"] == "Owner project task log"
    assert outsider_response.status_code == 404


@pytest.mark.asyncio
async def test_project_task_list_supports_system_view_filters(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    published_tool: Tool,
) -> None:
    project = await _create_project_with_members(db_session, users)
    pending_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Pending project task",
        status=TaskStatus.PENDING.value,
    )
    running_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Running project task",
        status=TaskStatus.RUNNING.value,
    )
    success_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Successful project task",
        status=TaskStatus.SUCCESS.value,
    )
    failed_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Failed project task",
        status=TaskStatus.FAILURE.value,
    )
    canceled_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Canceled project task",
        status=TaskStatus.CANCELED.value,
    )

    running_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer viewer"},
        params={"project_id": project.id, "view": "running"},
    )
    history_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer viewer"},
        params={"project_id": project.id, "view": "history"},
    )
    needs_attention_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer viewer"},
        params={"project_id": project.id, "view": "needs_attention"},
    )

    assert running_response.status_code == 200
    assert {
        item["id"] for item in running_response.json()["data"]["items"]
    } == {pending_task.id, running_task.id}
    assert history_response.status_code == 200
    assert {
        item["id"] for item in history_response.json()["data"]["items"]
    } == {success_task.id, failed_task.id, canceled_task.id}
    assert needs_attention_response.status_code == 200
    assert [
        item["id"] for item in needs_attention_response.json()["data"]["items"]
    ] == [failed_task.id]


@pytest.mark.asyncio
async def test_project_task_counts_support_system_views_and_keyword_filter(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    published_tool: Tool,
) -> None:
    project = await _create_project_with_members(db_session, users)
    await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Pending project task",
        status=TaskStatus.PENDING.value,
    )
    await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Running project task",
        status=TaskStatus.RUNNING.value,
    )
    await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Successful project task",
        status=TaskStatus.SUCCESS.value,
    )
    failed_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Failed ligand prep",
        status=TaskStatus.FAILURE.value,
    )
    failed_task.error_message = "Ligand conversion failed: invalid SDF block"
    await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Canceled project task",
        status=TaskStatus.CANCELED.value,
    )
    await db_session.commit()

    all_counts_response = await api_client.get(
        "/api/v1/tasks/counts",
        headers={"Authorization": "Bearer viewer"},
        params={"project_id": project.id},
    )
    filtered_counts_response = await api_client.get(
        "/api/v1/tasks/counts",
        headers={"Authorization": "Bearer viewer"},
        params={"project_id": project.id, "keyword": "Failed ligand"},
    )

    assert all_counts_response.status_code == 200
    assert all_counts_response.json()["data"] == {
        "all": 5,
        "running": 2,
        "history": 3,
        "needs_attention": 1,
        "recent_results": 1,
    }
    assert filtered_counts_response.status_code == 200
    assert filtered_counts_response.json()["data"] == {
        "all": 1,
        "running": 0,
        "history": 1,
        "needs_attention": 1,
        "recent_results": 0,
    }


@pytest.mark.asyncio
async def test_project_task_list_supports_created_time_range_filter(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    published_tool: Tool,
) -> None:
    project = await _create_project_with_members(db_session, users)
    old_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Old failed project task",
        status=TaskStatus.FAILURE.value,
    )
    recent_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Recent failed project task",
        status=TaskStatus.FAILURE.value,
    )
    old_task.created_at = utcnow() - timedelta(days=5)
    recent_task.created_at = utcnow() - timedelta(hours=2)
    await db_session.commit()

    response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer viewer"},
        params={
            "project_id": project.id,
            "view": "history",
            "created_from": (utcnow() - timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]["items"]] == [recent_task.id]


@pytest.mark.asyncio
async def test_project_task_list_supports_workflow_node_filters(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    published_tool: Tool,
) -> None:
    project = await _create_project_with_members(db_session, users)
    matching_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Workflow matching task",
        status=TaskStatus.RUNNING.value,
    )
    other_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Workflow other task",
        status=TaskStatus.RUNNING.value,
    )
    matching_input = (
        await db_session.execute(select(TaskInput).where(TaskInput.task_id == matching_task.id))
    ).scalar_one()
    other_input = (
        await db_session.execute(select(TaskInput).where(TaskInput.task_id == other_task.id))
    ).scalar_one()
    matching_input.params = {
        "workflow_run_id": "workflow-run-1",
        "workflow_definition_id": "workflow-def-1",
        "workflow_node_id": "protein_preparation",
    }
    other_input.params = {
        "workflow_run_id": "workflow-run-1",
        "workflow_definition_id": "workflow-def-1",
        "workflow_node_id": "lvpocket",
    }
    # 真实建任务路径同时写 `task_inputs.params` 与 `tasks` 上的真列（迁移
    # 20261030_06 已把历史数据从 params 回填）；列表筛选现在按真列走索引，
    # 这里必须一起写，否则测的是不存在的旧数据形态。
    matching_task.workflow_run_id = "workflow-run-1"
    matching_task.workflow_node_id = "protein_preparation"
    other_task.workflow_run_id = "workflow-run-1"
    other_task.workflow_node_id = "lvpocket"
    await db_session.commit()

    response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer viewer"},
        params={
            "project_id": project.id,
            "workflow_run_id": "workflow-run-1",
            "workflow_node_id": "protein_preparation",
        },
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]["items"]] == [matching_task.id]


@pytest.mark.asyncio
async def test_project_task_list_keyword_search_stays_on_identifier_fields(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    published_tool: Tool,
) -> None:
    project = await _create_project_with_members(db_session, users)
    matching_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Failed ligand prep",
        status=TaskStatus.FAILURE.value,
    )
    other_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Failed pocket prep",
        status=TaskStatus.FAILURE.value,
    )
    matching_task.error_message = "Ligand conversion failed: invalid SDF block"
    other_task.error_message = "Pocket prediction failed: no cavities detected"
    await db_session.commit()

    error_text_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer viewer"},
        params={"project_id": project.id, "keyword": "invalid SDF"},
    )
    name_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer viewer"},
        params={"project_id": project.id, "keyword": "Failed ligand"},
    )

    # 关键字搜索只覆盖标识类短字段（任务名/工具名/用户名 + 任务 ID 精确匹配），
    # 不再扫 error_message/progress_message 两个长文本列（见 docs/20 §5.1）。
    assert error_text_response.status_code == 200
    assert error_text_response.json()["data"]["items"] == []
    assert name_response.status_code == 200
    assert [item["id"] for item in name_response.json()["data"]["items"]] == [matching_task.id]


@pytest.mark.asyncio
async def test_project_task_operations_require_write_or_runner_role(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.logging.audit import AuditAction, AuditResult

    audit_events: list[dict[str, object]] = []

    class AuditRecorder:
        def log_task_operation(self, **kwargs):
            audit_events.append(kwargs)

    runner = SimpleNamespace(
        scheduled=[],
        cancelled=[],
        schedule_task=lambda task_id, tool_version_id: runner.scheduled.append((task_id, tool_version_id)),
        cancel_task=lambda task_id: runner.cancelled.append(task_id) or True,
    )
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)
    monkeypatch.setattr(
        "app.tasks.cancellation.get_audit_logger",
        lambda: AuditRecorder(),
        raising=False,
    )
    project = await _create_project_with_members(db_session, users)
    running_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Running project task",
        status=TaskStatus.RUNNING.value,
    )
    failed_task = await _create_task(
        db_session,
        user=users["owner"],
        tool=published_tool,
        project_id=project.id,
        name="Failed project task",
        status=TaskStatus.FAILURE.value,
    )

    viewer_cancel_response = await api_client.post(
        f"/api/v1/tasks/{running_task.id}/cancel",
        headers={"Authorization": "Bearer viewer"},
    )
    runner_cancel_response = await api_client.post(
        f"/api/v1/tasks/{running_task.id}/cancel",
        headers={"Authorization": "Bearer runner"},
    )
    viewer_retry_response = await api_client.post(
        f"/api/v1/tasks/{failed_task.id}/retry",
        headers={"Authorization": "Bearer viewer"},
    )
    editor_retry_response = await api_client.post(
        f"/api/v1/tasks/{failed_task.id}/retry",
        headers={"Authorization": "Bearer editor"},
    )

    assert viewer_cancel_response.status_code == 403
    assert runner_cancel_response.status_code == 200
    assert runner.cancelled == [running_task.id]
    assert audit_events == [
        {
            "action": AuditAction.TASK_CANCEL,
            "user_id": users["runner"].id,
            "task_id": running_task.id,
            "result": AuditResult.SUCCESS,
            "project_id": project.id,
            "tool_id": published_tool.id,
            "tool_version_id": published_tool.current_version_id,
        }
    ]
    assert viewer_retry_response.status_code == 403
    assert editor_retry_response.status_code == 200
    assert runner.scheduled == [(failed_task.id, published_tool.current_version_id)]
