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
from app.tasks.direct_recovery import reconcile_orphaned_direct_tasks
from app.tasks.direct_runner import DirectTaskRunner
from app.tasks.executor import SSHJobExecutor
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


def _direct_recovery_v2_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "recover-standard-pocket",
            "name": "Recover Standard Pocket",
            "version": "1.0.0",
        },
        "artifacts": {
            "inputs": [{"name": "protein", "type": "protein_structure@1"}],
            "outputs": [{"name": "pocket", "type": "binding_pocket@1"}],
        },
        "parameters_schema": {"type": "object"},
        "runtime": {
            "python": "3.10",
            "executor_support": ["ssh_docker_exec"],
            "selection_policy": "test runtime fixture",
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": "registry.example/sciminer/recover-standard-pocket:1.0.0",
                    "image_digest": "sha256:test",
                },
                "fallback": {
                    "kind": "conda_pack",
                    "uri": "artifacts://model-envs/recover-standard-pocket/1.0.0/env.tar.gz",
                    "sha256": "test",
                },
            },
            "weights": {
                "manifest_uri": "artifacts://model-weights/recover-standard-pocket/1.0.0/weights.json",
                "manifest_sha256": "test",
            },
            "cache_policy": {
                "key_fields": ["metadata.slug", "metadata.version"],
                "mutable_host_paths_forbidden": True,
            },
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["cli"],
                "entrypoint": ["/app/platform_run.sh"],
            }
        ],
    }


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
        config={
            "type": "ssh_job",
            "host": "10.202.2.228",
            "username": "zhouyc",
            "auth_type": "password",
            "password_ref": "ssh_4090_zhouyc",
            "runner_mode": "docker_exec",
            "remote_base_dir": "/srv/platform-jobs",
            "entrypoint": "/app/platform_run.sh",
            "container_name": "kaiwu",
        },
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
    assert response_data["resource_snapshot"] == {
        "executor_type": "ssh_job",
        "gpu_required": False,
        "gpu_memory_mb": 0,
        "timeout_sec": 600,
        "resource_profile": {},
    }
    assert response_data["dispatch"] == {"mode": "direct", "queue": None}

    task = await db_session.get(Task, task_id)
    assert task is not None
    assert task.celery_task_id is None
    assert task.extra_data["resource_snapshot"]["executor_type"] == "ssh_job"
    assert task.extra_data["dispatch"] == {"mode": "direct", "queue": None}


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
    assert refreshed_task.status == TaskStatus.PENDING.value
    assert refreshed_task.retry_count == 1
    assert refreshed_task.celery_task_id is None


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
@pytest.mark.parametrize("initial_status", [TaskStatus.RUNNING.value, TaskStatus.CANCELED.value])
async def test_reconcile_orphaned_direct_tasks_recovers_remote_success_result(
    db_session: AsyncSession,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
    initial_status: str,
) -> None:
    """热重载后可从远端 output 目录补回 ssh_job 成功结果。"""
    tool = Tool(
        owner_id=admin_user.id,
        name="Recover SSH Tool",
        slug=f"recover-ssh-tool-{initial_status.lower()}",
        description="Recoverable ssh_job tool",
        category="generation",
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
            "host": "10.202.2.228",
            "username": "zhouyc",
            "auth_type": "password",
            "password_ref": "ssh_4090_zhouyc",
            "runner_mode": "docker_exec",
            "remote_base_dir": "/srv/platform-jobs",
            "entrypoint": "/app/platform_run.sh",
            "container_name": "kaiwu",
        },
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()

    task = Task(
        user_id=admin_user.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        status=initial_status,
        priority="normal",
        progress=0.0,
        progress_message="开发模式 direct 任务已取消" if initial_status == TaskStatus.CANCELED.value else "任务开始执行",
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskInput(task_id=task.id, params={"foo": "bar"}, file_ids=[]))
    await db_session.commit()

    async def fake_recover(self) -> dict:
        return {
            "success": True,
            "result": {
                "success": True,
                "message": "recovered",
                "metrics": {"duration_sec": 12.7},
                "output_file_ids": ["file-1", "file-2"],
            },
            "output_file_ids": ["file-1", "file-2"],
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr(SSHJobExecutor, "recover_remote_result", fake_recover)

    recovered = await reconcile_orphaned_direct_tasks(db_session)
    assert recovered == 1

    refreshed_task = await db_session.get(Task, task.id)
    assert refreshed_task is not None
    assert refreshed_task.status == TaskStatus.SUCCESS.value
    assert refreshed_task.progress == 100.0
    assert refreshed_task.progress_message == "任务执行成功（远端结果自动补回）"
    assert refreshed_task.execution_time_sec == 12

    result = await db_session.execute(select(TaskOutput).where(TaskOutput.task_id == task.id))
    task_output = result.scalar_one_or_none()
    assert task_output is not None
    assert task_output.output_type == "visualization"
    assert task_output.file_ids == ["file-1", "file-2"]

    log_result = await db_session.execute(select(TaskLog).where(TaskLog.task_id == task.id))
    logs = log_result.scalars().all()
    assert any(log.message == "从远端 output 目录自动补回任务结果" for log in logs)


@pytest.mark.asyncio
async def test_reconcile_orphaned_direct_tasks_persists_standard_artifacts(
    db_session: AsyncSession,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """direct recovery 补回标准 result.v2 时也应创建标准 ArtifactVersion。"""
    organization = Organization(name="Recovery Lab", slug="recovery-lab")
    db_session.add(organization)
    await db_session.flush()
    project = Project(
        organization_id=organization.id,
        created_by=admin_user.id,
        name="Recovered standard output",
        status="active",
    )
    db_session.add(project)
    await db_session.flush()
    tool = Tool(
        owner_id=admin_user.id,
        name="Recover Standard Tool",
        slug="recover-standard-tool",
        description="Recoverable standard ssh_job tool",
        category="generation",
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
            "host": "10.202.2.228",
            "username": "zhouyc",
            "auth_type": "password",
            "password_ref": "ssh_4090_zhouyc",
            "runner_mode": "docker_exec",
            "remote_base_dir": "/srv/platform-jobs",
            "entrypoint": "/app/platform_run.sh",
            "container_name": "kaiwu",
            "tool_package_manifest": _direct_recovery_v2_manifest(),
        },
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()

    task = Task(
        user_id=admin_user.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        status=TaskStatus.RUNNING.value,
        priority="normal",
        progress=0.0,
        progress_message="任务开始执行",
        extra_data={"project_id": project.id},
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskInput(task_id=task.id, params={}, file_ids=[]))

    files_by_role = {
        "residue_pocket_pdb": ("artifacts/pocket/residue.pdb", b"residue"),
        "atom_pocket_pdb": ("artifacts/pocket/atom.pdb", b"atom"),
        "pocket_metadata_json": ("artifacts/pocket/metadata.json", b"{}"),
    }
    output_file_ids: list[str] = []
    result_files: dict[str, dict[str, str]] = {}
    for role, (relative_path, content) in files_by_role.items():
        storage_path = tmp_path / relative_path
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        file_record = File(
            project_id=project.id,
            owner_id=admin_user.id,
            filename=relative_path.replace("/", "__"),
            content_type="application/json" if relative_path.endswith(".json") else "chemical/x-pdb",
            size_bytes=len(content),
            sha256=digest,
            storage_path=str(storage_path),
            source_type=FileSourceType.TOOL_OUTPUT.value,
            file_meta={"relative_path": relative_path},
        )
        db_session.add(file_record)
        await db_session.flush()
        output_file_ids.append(str(file_record.id))
        result_files[role] = {"path": relative_path, "sha256": digest}
    await db_session.commit()

    async def fake_recover(self) -> dict:
        return {
            "success": True,
            "result": {
                "result_version": "aidd.sciminer/result.v2",
                "artifacts": {
                    "pocket": {
                        "name": "Recovered pocket",
                        "type": "binding_pocket@1",
                        "files": result_files,
                    }
                },
                "relations": [],
            },
            "output_file_ids": output_file_ids,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr(SSHJobExecutor, "recover_remote_result", fake_recover)

    recovered = await reconcile_orphaned_direct_tasks(db_session)

    task_output = (
        await db_session.execute(select(TaskOutput).where(TaskOutput.task_id == task.id))
    ).scalar_one()
    artifact_versions = (await db_session.execute(select(ArtifactVersion))).scalars().all()

    assert recovered == 1
    assert task_output.result["standard_artifacts"]["artifact_version_ids_by_ref"]["pocket"]
    assert len(artifact_versions) == 1
    assert artifact_versions[0].manifest_json["type"] == "binding_pocket@1"


@pytest.mark.asyncio
async def test_reconcile_orphaned_direct_tasks_triggers_workflow_reconciliation_for_workflow_tasks(
    db_session: AsyncSession,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """补回工作流节点任务后，应主动触发工作流对账续跑。"""
    from app.config import settings

    tool = Tool(
        owner_id=admin_user.id,
        name="Recover Workflow SSH Tool",
        slug="recover-workflow-ssh-tool",
        description="Recoverable workflow ssh_job tool",
        category="generation",
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
            "host": "10.202.2.228",
            "username": "zhouyc",
            "auth_type": "password",
            "password_ref": "ssh_4090_zhouyc",
            "runner_mode": "docker_exec",
            "remote_base_dir": "/srv/platform-jobs",
            "entrypoint": "/app/platform_run.sh",
            "container_name": "kaiwu",
        },
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()

    task = Task(
        user_id=admin_user.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        status=TaskStatus.RUNNING.value,
        priority="normal",
        progress=0.0,
        progress_message="任务开始执行",
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(
        TaskInput(
            task_id=task.id,
            params={
                "workflow_run_id": "run-1",
                "workflow_node_id": "node-1",
            },
            file_ids=[],
        )
    )
    await db_session.commit()

    async def fake_recover(self) -> dict:
        return {
            "success": True,
            "result": {
                "success": True,
                "message": "recovered",
                "metrics": {"duration_sec": 3},
                "output_file_ids": ["file-1"],
            },
            "output_file_ids": ["file-1"],
            "stdout": "",
            "stderr": "",
        }

    calls: list[tuple[int, object]] = []

    async def fake_reconcile_workflows(db, *, batch_size, schedule_task_fn) -> int:
        calls.append((batch_size, schedule_task_fn))
        return 1

    monkeypatch.setattr(SSHJobExecutor, "recover_remote_result", fake_recover)
    monkeypatch.setattr(
        "app.tasks.direct_recovery.reconcile_waiting_workflow_runs",
        fake_reconcile_workflows,
    )

    recovered = await reconcile_orphaned_direct_tasks(db_session)

    assert recovered == 1
    assert len(calls) == 1
    assert calls[0][0] == settings.WORKFLOW_RECONCILE_BATCH_SIZE
    assert calls[0][1] is not None
