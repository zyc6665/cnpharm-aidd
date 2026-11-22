"""开发模式 direct 任务执行测试。"""

from __future__ import annotations

import asyncio
import hashlib
import sys
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

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.config import settings as config_settings
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import artifacts as _artifacts_models  # noqa: F401
from app.models import files as _files_models  # noqa: F401
from app.models import projects as _project_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.artifacts import ArtifactVersion
from app.models.files import File, FileSourceType
from app.models.projects import Organization, Project, ProjectMember
from app.models.tasks import TaskLog, TaskOutput
from app.models.statistics import ToolStatistics
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.tasks.direct_runner import DirectTaskRunner
from app.tasks.queue_manager import TaskQueueManager
from app.api.v1 import tasks as tasks_api


class RecordingDirectRunner:
    """记录 direct runner 调度行为。"""

    def __init__(self) -> None:
        self.scheduled: list[tuple[str, str]] = []
        self.cancelled: list[str] = []

    def schedule_task(self, task_id: str, tool_version_id: str) -> None:
        self.scheduled.append((task_id, tool_version_id))

    def cancel_task(self, task_id: str) -> bool:
        self.cancelled.append(task_id)
        return True




def test_use_direct_task_execution_falls_back_when_celery_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未配置 Celery Broker 时应自动回退到 direct 模式。"""
    from app.config import settings, use_direct_task_execution

    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr(settings, "CELERY_BROKER_URL", None, raising=False)

    assert use_direct_task_execution() is True


def test_workflow_reconciliation_settings_are_exposed() -> None:
    """工作流后台对账应暴露显式配置项。"""
    from app.config import settings

    assert hasattr(settings, "WORKFLOW_RECONCILE_INTERVAL_SECONDS")
    assert hasattr(settings, "WORKFLOW_RECONCILE_BATCH_SIZE")
    assert settings.WORKFLOW_RECONCILE_INTERVAL_SECONDS > 0
    assert settings.WORKFLOW_RECONCILE_BATCH_SIZE > 0


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """创建隔离数据库会话。"""
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


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """创建管理员用户。"""
    user = User(
        email="admin@example.com",
        password_hash="hashed-password",
        display_name="Admin",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    admin_user: User,
):
    """创建带依赖覆盖的 API 客户端。"""

    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == "Bearer admin-token":
            return admin_user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    async def override_get_current_user_optional(
        authorization: str | None = Header(default=None),
    ) -> User | None:
        if authorization == "Bearer admin-token":
            return admin_user
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def published_tool(db_session: AsyncSession, admin_user: User) -> Tool:
    """创建带当前版本的测试工具。"""
    tool = Tool(
        owner_id=admin_user.id,
        name="Direct Runner Tool",
        slug="direct-runner-tool",
        description="Tool for direct execution tests",
        category="generation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "k8s_job"},
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()

    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest.mark.asyncio
async def test_record_tool_usage_creates_missing_statistics(
    db_session: AsyncSession,
    admin_user: User,
):
    """缺失统计行时应自动创建并记录一次使用。"""
    tool = Tool(
        owner_id=admin_user.id,
        name="Statistics Creation Tool",
        slug="statistics-creation-tool",
        description="Tool without statistics row",
        category="generation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    await tasks_api._record_tool_usage(db_session, str(tool.id))
    await db_session.commit()

    statistics = await db_session.get(ToolStatistics, str(tool.id))
    assert statistics is not None
    assert statistics.usage_count == 1
    assert statistics.last_used_at is not None


@pytest.mark.asyncio
async def test_record_tool_usage_increments_existing_statistics(
    db_session: AsyncSession,
    admin_user: User,
):
    """已有统计行时应原地递增 usage_count。"""
    tool = Tool(
        owner_id=admin_user.id,
        name="Statistics Increment Tool",
        slug="statistics-increment-tool",
        description="Tool with statistics row",
        category="generation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    db_session.add(ToolStatistics(tool_id=str(tool.id), usage_count=3))
    await db_session.commit()
    await db_session.refresh(tool)

    await tasks_api._record_tool_usage(db_session, str(tool.id))
    await db_session.commit()

    statistics = await db_session.get(ToolStatistics, str(tool.id))
    assert statistics is not None
    assert statistics.usage_count == 4
    assert statistics.last_used_at is not None


@pytest.mark.asyncio
async def test_create_task_uses_direct_runner_when_enabled(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
):
    """direct 模式下创建任务应直接注册后台协程，而不是发送到 Celery。"""
    runner = RecordingDirectRunner()
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)

    def fail_enqueue(*args, **kwargs):
        raise AssertionError("direct 模式不应调用 Celery 入队")

    monkeypatch.setattr(TaskQueueManager, "enqueue_task", classmethod(lambda cls, *args, **kwargs: fail_enqueue(*args, **kwargs)))

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "params": {"foo": "bar"},
            "priority": "normal",
        },
    )

    assert response.status_code == 200
    response_data = response.json()["data"]
    task_id = response_data["id"]
    assert runner.scheduled == [(task_id, published_tool.current_version_id)]
    assert response_data["tool_slug"] == published_tool.slug
    assert response_data["tool"]["current_version"]["id"] == published_tool.current_version_id
    assert response_data["tool"]["current_version"]["version"] == "1.0.0"
    assert response_data["resource_snapshot"] == {
        "executor_type": "k8s_job",
        "gpu_required": False,
        "gpu_memory_mb": 0,
        "timeout_sec": 600,
        "resource_request": {
            "executor_type": "k8s_job",
            "tier": None,
            "cpu": None,
            "memory_gb": None,
            "cpu_limit": None,
            "memory_limit": None,
            "gpu_required": False,
            "gpu_count": 0,
            "gpu_memory_mb": 0,
            "timeout_sec": 600,
            "parallelism": 1,
        },
        "resource_profile": {},
    }
    assert response_data["dispatch"] == {"mode": "direct", "queue": None}

    task = await db_session.get(Task, task_id)
    assert task is not None
    assert task.celery_task_id is None
    assert task.extra_data["resource_snapshot"]["executor_type"] == "k8s_job"
    assert task.extra_data["dispatch"] == {"mode": "direct", "queue": None}


@pytest.mark.asyncio
async def test_create_task_cpu_device_overrides_tool_gpu_requirement(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
):
    """显式 CPU 运行的工具任务不应因为工具默认 GPU 标记而申请 GPU。"""
    runner = RecordingDirectRunner()
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)
    published_tool.gpu_required = True
    published_tool.gpu_memory_mb = 24576
    await db_session.commit()

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "params": {"device": "cpu", "timesteps": 1},
            "priority": "normal",
        },
    )

    assert response.status_code == 200
    response_data = response.json()["data"]
    assert response_data["resource_snapshot"]["gpu_required"] is False
    assert response_data["resource_snapshot"]["gpu_memory_mb"] == 0

    task = await db_session.get(Task, response_data["id"])
    assert task.extra_data["resource_snapshot"]["gpu_required"] is False


@pytest.mark.asyncio
async def test_create_task_rejects_inactive_candidate_version(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
):
    candidate = ToolVersion(
        tool_id=published_tool.id,
        version="2.0.0-k8s-candidate",
        config={"type": "k8s_job"},
        is_active=False,
    )
    db_session.add(candidate)
    await db_session.commit()

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "tool_version_id": candidate.id,
        },
    )

    assert response.status_code == 422
    assert "不可运行" in response.json()["message"]


@pytest.mark.asyncio
async def test_create_task_rejects_version_from_another_tool(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    admin_user: User,
):
    other_tool = Tool(
        owner_id=admin_user.id,
        name="Other Direct Runner Tool",
        slug="other-direct-runner-tool",
        status=ToolStatus.PUBLISHED.value,
    )
    db_session.add(other_tool)
    await db_session.flush()
    other_version = ToolVersion(
        tool_id=other_tool.id,
        version="1.0.0",
        config={"type": "k8s_job"},
        is_active=True,
    )
    db_session.add(other_version)
    await db_session.commit()

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "tool_version_id": other_version.id,
        },
    )

    assert response.status_code == 422
    assert "不属于该工具" in response.json()["message"]


@pytest.mark.asyncio
async def test_create_task_api_uses_shared_task_creation_service(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
):
    """任务 API 应保持现有行为，后续 agent 可以复用同一任务创建服务。"""
    runner = RecordingDirectRunner()
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "params": {"alpha": 1},
            "file_ids": [],
        },
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["id"]
    assert runner.scheduled == [(task_id, published_tool.current_version_id)]


@pytest.mark.asyncio
async def test_standard_artifact_task_without_project_uses_default_project(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    """会产生标准产物的直接任务未传 project_id 时应自动落到用户默认项目。"""
    runner = RecordingDirectRunner()
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)

    tool = Tool(
        owner_id=admin_user.id,
        name="Fetch PDB Structure",
        slug="builtin-fetch-pdb",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "builtin",
            "builtin_slug": "builtin-fetch-pdb",
            "artifacts": {
                "outputs": [
                    {"name": "protein", "type": "protein_structure@1", "required": True}
                ]
            },
        },
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": tool.id,
            "params": {"pdb_id": "1a2b"},
        },
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["id"]
    project_id = response.json()["data"]["project_id"]
    assert project_id
    assert runner.scheduled == [(task_id, version.id)]

    task = await db_session.get(Task, task_id)
    assert task is not None
    assert task.extra_data["project_id"] == project_id

    project = await db_session.get(Project, project_id)
    assert project is not None
    assert project.created_by == admin_user.id
    assert (project.data_policy or {}).get("migration_default") is True

    membership_result = await db_session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == admin_user.id,
            ProjectMember.role == "owner",
        )
    )
    assert membership_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_retry_task_uses_direct_runner_when_enabled(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    """direct 模式下重试任务应再次注册后台协程，而不是重新入 Celery。"""
    runner = RecordingDirectRunner()
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)

    def fail_enqueue(*args, **kwargs):
        raise AssertionError("direct 模式不应调用 Celery 入队")

    monkeypatch.setattr(TaskQueueManager, "enqueue_task", classmethod(lambda cls, *args, **kwargs: fail_enqueue(*args, **kwargs)))

    task = Task(
        user_id=admin_user.id,
        tool_id=published_tool.id,
        tool_version_id=published_tool.current_version_id,
        status=TaskStatus.FAILURE.value,
        priority="normal",
        progress=0.0,
        error_message="boom",
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskInput(task_id=task.id, params={"foo": "bar"}, file_ids=[]))
    await db_session.commit()

    response = await api_client.post(
        f"/api/v1/tasks/{task.id}/retry",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert runner.scheduled == [(task.id, published_tool.current_version_id)]

    refreshed_task = await db_session.get(Task, task.id)
    assert refreshed_task is not None
    assert refreshed_task.status == TaskStatus.QUEUED.value
    assert refreshed_task.retry_count == 1
    assert refreshed_task.celery_task_id is None


@pytest.mark.asyncio
async def test_retry_waits_for_canceled_attempt_to_stop_and_clears_control(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    runner = RecordingDirectRunner()
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)
    task = Task(
        user_id=admin_user.id,
        tool_id=published_tool.id,
        tool_version_id=published_tool.current_version_id,
        status=TaskStatus.CANCELED.value,
        priority="normal",
        progress=0.0,
        extra_data={
            "execution_attempt_id": "attempt-old",
            "execution_control": {
                "state": "cancel_requested",
                "attempt_id": "attempt-old",
            },
        },
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskInput(task_id=task.id, params={"foo": "bar"}, file_ids=[]))
    await db_session.commit()

    blocked_response = await api_client.post(
        f"/api/v1/tasks/{task.id}/retry",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert blocked_response.status_code == 409
    assert runner.scheduled == []

    task.extra_data["execution_control"]["state"] = "released"
    await db_session.commit()
    retry_response = await api_client.post(
        f"/api/v1/tasks/{task.id}/retry",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert retry_response.status_code == 200
    assert runner.scheduled == [(task.id, published_tool.current_version_id)]
    await db_session.refresh(task)
    assert "execution_control" not in task.extra_data


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [TaskStatus.FAILURE.value, TaskStatus.CANCELED.value])
async def test_retry_task_rejects_when_max_retries_reached(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
):
    """达到最大重试次数的失败或取消任务不可再次调度。"""
    runner = RecordingDirectRunner()
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)

    task = Task(
        user_id=admin_user.id,
        tool_id=published_tool.id,
        tool_version_id=published_tool.current_version_id,
        status=status,
        priority="normal",
        progress=0.0,
        error_message="boom" if status == TaskStatus.FAILURE.value else None,
        retry_count=3,
        max_retries=3,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskInput(task_id=task.id, params={"foo": "bar"}, file_ids=[]))
    await db_session.commit()

    response = await api_client.post(
        f"/api/v1/tasks/{task.id}/retry",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 422
    assert "最大重试次数" in response.json()["message"]
    assert runner.scheduled == []

    refreshed_task = await db_session.get(Task, task.id)
    assert refreshed_task is not None
    assert refreshed_task.status == status
    assert refreshed_task.retry_count == 3


@pytest.mark.asyncio
async def test_retry_task_replaces_stale_celery_dispatch_when_direct_enabled(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    """切换到 direct 重试时应清理上一次 Celery 调度信息。"""
    runner = RecordingDirectRunner()
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)

    task = Task(
        user_id=admin_user.id,
        tool_id=published_tool.id,
        tool_version_id=published_tool.current_version_id,
        status=TaskStatus.FAILURE.value,
        priority="normal",
        progress=0.0,
        error_message="boom",
        celery_task_id="previous-celery-task",
        extra_data={"dispatch": {"mode": "celery", "queue": "gpu", "queue_priority": 9}},
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskInput(task_id=task.id, params={"foo": "bar"}, file_ids=[]))
    await db_session.commit()

    response = await api_client.post(
        f"/api/v1/tasks/{task.id}/retry",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert runner.scheduled == [(task.id, published_tool.current_version_id)]

    refreshed_task = await db_session.get(Task, task.id)
    assert refreshed_task is not None
    assert refreshed_task.celery_task_id is None
    assert refreshed_task.extra_data["dispatch"] == {"mode": "direct", "queue": None}


@pytest.mark.asyncio
async def test_retry_task_uses_tool_gpu_config_without_resource_snapshot(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
):
    """重试旧任务没有资源快照时，应回退使用工具版本的 GPU 配置选队列。"""
    task_user = User(
        email="runner@example.com",
        password_hash="hashed-password",
        display_name="Runner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(task_user)
    await db_session.flush()

    version = await db_session.get(ToolVersion, published_tool.current_version_id)
    assert version is not None
    version.config = {**version.config, "gpu_required": True}

    task = Task(
        user_id=task_user.id,
        tool_id=published_tool.id,
        tool_version_id=published_tool.current_version_id,
        status=TaskStatus.FAILURE.value,
        priority="normal",
        progress=0.0,
        error_message="boom",
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskInput(task_id=task.id, params={"foo": "bar"}, file_ids=[]))
    await db_session.commit()

    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr(config_settings, "CELERY_BROKER_URL", "redis://test", raising=False)
    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(
            lambda cls, task_id, tool_version_id, queue: (
                queued.append((task_id, queue))
                or type("DummyCeleryTask", (), {"id": "celery-retry-task"})()
            )
        ),
    )

    response = await api_client.post(
        f"/api/v1/tasks/{task.id}/retry",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert queued == [(task.id, "gpu_queue")]

    refreshed_task = await db_session.get(Task, task.id)
    assert refreshed_task is not None
    assert refreshed_task.celery_task_id == "celery-retry-task"
    assert refreshed_task.extra_data["dispatch"] == {
        "mode": "celery",
        "queue": "gpu_queue",
        "queue_priority": 5,
        # 测试环境没有真实 Worker，派发时的探测会把这个事实记进 dispatch
        "worker_available": False,
    }


@pytest.mark.asyncio
async def test_cancel_task_cancels_registered_direct_task(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
):
    """direct 模式下取消任务应调用 direct runner 取消当前进程内任务。"""
    runner = RecordingDirectRunner()
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)

    task = Task(
        user_id=admin_user.id,
        tool_id=published_tool.id,
        tool_version_id=published_tool.current_version_id,
        status=TaskStatus.RUNNING.value,
        priority="normal",
        progress=0.2,
    )
    db_session.add(task)
    await db_session.commit()

    response = await api_client.post(
        f"/api/v1/tasks/{task.id}/cancel",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert runner.cancelled == [task.id]

    refreshed_task = await db_session.get(Task, task.id)
    assert refreshed_task is not None
    assert refreshed_task.status == TaskStatus.CANCELED.value


@pytest.mark.asyncio
async def test_direct_runner_shutdown_does_not_mark_task_canceled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """进程关闭引发的 direct 中断不应误记为用户取消。"""
    runner = DirectTaskRunner()
    canceled_task_ids: list[str] = []

    async def fake_impl(task_id: str, tool_version_id: str) -> None:
        await asyncio.sleep(10)

    async def fake_mark(task_id: str, message: str) -> None:
        canceled_task_ids.append(task_id)

    monkeypatch.setattr("app.worker.tasks._execute_tool_task_impl", fake_impl)
    monkeypatch.setattr(runner, "_mark_task_canceled", fake_mark)

    runner.schedule_task("task-shutdown", "tool-version")
    await asyncio.sleep(0)
    await runner.shutdown()

    assert canceled_task_ids == []


@pytest.mark.asyncio
async def test_direct_runner_old_completion_callback_does_not_remove_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一任务替换调度时，旧任务回调不得移除新任务注册。"""
    runner = DirectTaskRunner()

    class FakeTask:
        def __init__(self) -> None:
            self.is_done = False
            self.callbacks = []

        def done(self) -> bool:
            return self.is_done

        def add_done_callback(self, callback) -> None:
            self.callbacks.append(callback)

        def fire_done_callbacks(self) -> None:
            for callback in self.callbacks:
                callback(self)

    created_tasks: list[FakeTask] = []

    async def fake_run(task_id: str, tool_version_id: str) -> None:
        return None

    def fake_create_task(coro, *, name: str):
        coro.close()
        task = FakeTask()
        created_tasks.append(task)
        return task

    monkeypatch.setattr(runner, "_run_task", fake_run)
    monkeypatch.setattr("app.tasks.direct_runner.asyncio.create_task", fake_create_task)

    first = runner.schedule_task("task-replaced", "version-1")
    first.is_done = True
    second = runner.schedule_task("task-replaced", "version-2")
    first.fire_done_callbacks()

    assert runner._tasks.get("task-replaced") is second


@pytest.mark.asyncio
async def test_direct_runner_requeues_after_current_task_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """direct 模式 GPU 重试应等待当前协程退出后再启动下一次。"""
    runner = DirectTaskRunner()
    release = asyncio.Event()
    first_started = asyncio.Event()
    calls: list[tuple[str, str]] = []

    async def fake_run(task_id: str, tool_version_id: str) -> None:
        calls.append((task_id, tool_version_id))
        if len(calls) == 1:
            first_started.set()
            await release.wait()

    monkeypatch.setattr(runner, "_run_task", fake_run)

    first = runner.schedule_task("task-gpu-retry", "version-1")
    await first_started.wait()
    runner.schedule_task_after_current(
        "task-gpu-retry",
        "version-2",
        delay_seconds=0.01,
    )
    await asyncio.sleep(0)

    assert calls == [("task-gpu-retry", "version-1")]

    release.set()
    await first
    await asyncio.sleep(0)
    assert calls == [("task-gpu-retry", "version-1")]

    for _ in range(10):
        await asyncio.sleep(0.005)
        if len(calls) == 2:
            break

    assert calls == [
        ("task-gpu-retry", "version-1"),
        ("task-gpu-retry", "version-2"),
    ]
