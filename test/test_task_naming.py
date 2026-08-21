"""任务命名功能测试。"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

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

from app.api.v1 import tasks as tasks_api
from app.auth.dependencies import get_current_user, get_current_user_optional
from app.config import settings as config_settings
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import projects as _project_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.artifacts import ArtifactVersionFile
from app.models.files import File as FileModel, FileSourceType
from app.models.projects import Organization, Project, ProjectMember
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.tasks.naming import (
    _sanitize_task_name,
    _build_default_task_name,
    resolve_task_display_name,
    _dedupe_file_ids,
    _extract_file_ids_from_result,
)


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
async def api_client(db_session: AsyncSession, admin_user: User):
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
        name="Molecular Docking",
        slug="molecular-docking",
        description="Tool for task naming tests",
        category="generation",
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


@pytest_asyncio.fixture
async def task_project(db_session: AsyncSession, admin_user: User) -> Project:
    """创建当前用户可访问的研究项目。"""
    organization = Organization(name="Task Center Lab", slug="task-center-lab")
    db_session.add(organization)
    await db_session.flush()

    project = Project(
        organization_id=organization.id,
        created_by=admin_user.id,
        name="Task Center Project",
        status="active",
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=admin_user.id, role="owner"))
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.fixture
def direct_runner_stub(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """将任务创建固定为 direct 模式，并屏蔽实际调度。"""
    runner = SimpleNamespace(
        scheduled=[],
        cancelled=[],
        schedule_task=lambda task_id, tool_version_id: runner.scheduled.append((task_id, tool_version_id)),
        cancel_task=lambda task_id: runner.cancelled.append(task_id) or True,
    )
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)
    return runner


@pytest.mark.asyncio
async def test_create_task_persists_explicit_name(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    direct_runner_stub: SimpleNamespace,
):
    """显式传入任务名时应持久化并透传给响应。"""
    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "name": "Pocket Screening Round 1",
            "params": {"foo": "bar"},
            "priority": "normal",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["name"] == "Pocket Screening Round 1"

    task = await db_session.get(Task, payload["id"])
    assert task is not None
    assert task.name == "Pocket Screening Round 1"


@pytest.mark.asyncio
async def test_create_task_without_name_generates_default_name(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    direct_runner_stub: SimpleNamespace,
):
    """未传任务名时应自动生成默认任务名。"""
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
    payload = response.json()["data"]
    assert payload["name"].startswith("Molecular Docking ")

    task = await db_session.get(Task, payload["id"])
    assert task is not None
    assert task.name == payload["name"]


@pytest.mark.asyncio
async def test_create_task_with_project_id_persists_project_context(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    task_project: Project,
    direct_runner_stub: SimpleNamespace,
):
    """直接任务中心传入 project_id 时应写入 Task.extra_data，供标准 Artifact 持久化使用。"""
    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "project_id": task_project.id,
            "params": {"foo": "bar"},
            "priority": "normal",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["project_id"] == task_project.id

    task = await db_session.get(Task, payload["id"])
    assert task is not None
    assert task.extra_data["project_id"] == task_project.id

    detail_response = await api_client.get(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["project_id"] == task_project.id

    list_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert list_response.status_code == 200
    matched = [
        item for item in list_response.json()["data"]["items"] if item["id"] == task.id
    ]
    assert matched[0]["project_id"] == task_project.id


async def _seed_standard_artifact_version(
    db_session: AsyncSession,
    *,
    project_id: str,
    user_id: str,
    standard_type: str = "protein_structure",
    standard_version: int = 1,
    status: str = "available",
) -> ArtifactVersion:
    artifact = Artifact(
        project_id=project_id,
        created_by=user_id,
        artifact_type=standard_type,
        semantic_type=standard_type,
        standard_type=standard_type,
        standard_version=standard_version,
        name=f"{standard_type}@{standard_version}",
    )
    db_session.add(artifact)
    await db_session.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=user_id,
        version=1,
        filename="artifact.json",
        content_type="application/json",
        size_bytes=2,
        sha256="0" * 64,
        storage_key="test/artifact.json",
        status=status,
        validation_status="passed",
        validation_errors=[],
        manifest_json={"type": f"{standard_type}@{standard_version}"},
        summary_json={},
        metrics_json={},
    )
    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(version)
    return version


async def _seed_prepared_protein_artifact_version(
    db_session: AsyncSession,
    *,
    project_id: str,
    user_id: str,
) -> tuple[ArtifactVersion, FileModel, FileModel]:
    raw_file = FileModel(
        project_id=project_id,
        owner_id=user_id,
        filename="raw.pdb",
        content_type="chemical/x-pdb",
        size_bytes=3,
        sha256="1" * 64,
        storage_path="/tmp/raw.pdb",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    prepared_file = FileModel(
        project_id=project_id,
        owner_id=user_id,
        filename="prepared.pdb",
        content_type="chemical/x-pdb",
        size_bytes=8,
        sha256="2" * 64,
        storage_path="/tmp/prepared.pdb",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    db_session.add_all([raw_file, prepared_file])
    await db_session.flush()
    artifact = Artifact(
        project_id=project_id,
        created_by=user_id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        standard_type="protein_structure",
        standard_version=1,
        name="prepared protein",
    )
    db_session.add(artifact)
    await db_session.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=user_id,
        version=1,
        filename="prepared.manifest.json",
        content_type="application/json",
        size_bytes=2,
        sha256="0" * 64,
        storage_key="test/prepared.manifest.json",
        status="available",
        validation_status="passed",
        validation_errors=[],
        manifest_json={"type": "protein_structure@1", "metadata": {"preparation_status": "prepared"}},
        summary_json={},
        metrics_json={},
    )
    db_session.add(version)
    await db_session.flush()
    db_session.add_all(
        [
            ArtifactVersionFile(
                artifact_version_id=version.id,
                role="structure_file",
                file_id=raw_file.id,
                is_primary=True,
                sort_order=0,
            ),
            ArtifactVersionFile(
                artifact_version_id=version.id,
                role="prepared_pdb",
                file_id=prepared_file.id,
                sort_order=1,
            ),
        ]
    )
    artifact.latest_version_id = version.id
    await db_session.commit()
    await db_session.refresh(version)
    await db_session.refresh(raw_file)
    await db_session.refresh(prepared_file)
    return version, raw_file, prepared_file


@pytest.mark.asyncio
async def test_create_task_with_input_bindings_persists_standard_artifact_context(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    task_project: Project,
    admin_user: User,
    direct_runner_stub: SimpleNamespace,
):
    """直接任务中心应保存标准 ArtifactVersion 输入绑定，供 v2 executor 构造 request.v1。"""
    artifact_version = await _seed_standard_artifact_version(
        db_session,
        project_id=task_project.id,
        user_id=admin_user.id,
    )

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "project_id": task_project.id,
            "params": {"threshold": 0.5},
            "input_bindings": {"protein": artifact_version.id},
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["project_id"] == task_project.id
    assert payload["input_bindings"] == {"protein": artifact_version.id}

    task = await db_session.get(Task, payload["id"])
    assert task is not None
    assert task.extra_data["project_id"] == task_project.id
    assert task.extra_data["input_bindings"] == {"protein": artifact_version.id}

    detail_response = await api_client.get(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["input_bindings"] == {"protein": artifact_version.id}
    assert detail["inputs"]["input_bindings"] == {"protein": artifact_version.id}


@pytest.mark.asyncio
async def test_create_task_with_input_binding_projects_selected_role_for_legacy_tool(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    task_project: Project,
    admin_user: User,
    direct_runner_stub: SimpleNamespace,
):
    """legacy ssh_job 独立运行也应由后端按 ArtifactVersion role 选择输入文件。"""
    artifact_version, raw_file, prepared_file = await _seed_prepared_protein_artifact_version(
        db_session,
        project_id=task_project.id,
        user_id=admin_user.id,
    )
    tool = Tool(
        owner_id=admin_user.id,
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
        is_active=True,
        config={
            "type": "ssh_job",
            "input_schema": {
                "type": "object",
                "properties": {
                    "protein_pdb": {"type": "string", "format": "file", "title": "Protein PDB"},
                    "model_choice": {"type": "string", "default": "auto"},
                },
                "required": ["protein_pdb"],
            },
        },
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
            "project_id": task_project.id,
            "params": {"params": {"model_choice": "auto"}},
            "input_bindings": {"protein": artifact_version.id},
        },
    )

    assert response.status_code == 200
    response_data = response.json()["data"]
    assert response_data["binding_decisions"]["protein"]["selected_role"] == "prepared_pdb"
    task = await db_session.get(Task, response.json()["data"]["id"])
    assert task is not None
    await db_session.refresh(task, ["inputs"])
    assert task.extra_data["input_bindings"] == {"protein": artifact_version.id}
    assert task.extra_data["binding_decisions"]["protein"]["selected_role"] == "prepared_pdb"
    assert task.inputs.file_ids == [prepared_file.id]
    assert raw_file.id not in task.inputs.file_ids
    assert task.inputs.params["input_files"] == {"protein_pdb": "input/prepared.pdb"}
    assert task.inputs.params["params"] == {"model_choice": "auto"}


@pytest.mark.asyncio
async def test_create_task_rejects_input_bindings_without_project_id(
    api_client: httpx.AsyncClient,
    published_tool: Tool,
    direct_runner_stub: SimpleNamespace,
):
    """标准 ArtifactVersion 绑定必须带 project_id，避免跨项目权限绕过。"""
    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "params": {},
            "input_bindings": {"protein": "version-1"},
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_task_rejects_input_binding_from_another_project(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    task_project: Project,
    admin_user: User,
    direct_runner_stub: SimpleNamespace,
):
    """输入绑定的 ArtifactVersion 必须属于任务 project_id。"""
    organization = Organization(name="Binding Other Lab", slug="binding-other-lab")
    db_session.add(organization)
    await db_session.flush()
    other_project = Project(
        organization_id=organization.id,
        created_by=admin_user.id,
        name="Other Binding Project",
        status="active",
    )
    db_session.add(other_project)
    await db_session.flush()
    artifact_version = await _seed_standard_artifact_version(
        db_session,
        project_id=other_project.id,
        user_id=admin_user.id,
    )

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "project_id": task_project.id,
            "params": {},
            "input_bindings": {"protein": artifact_version.id},
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_task_rejects_unavailable_input_binding(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    task_project: Project,
    admin_user: User,
    direct_runner_stub: SimpleNamespace,
):
    """不可用的 ArtifactVersion 不能作为标准输入绑定。"""
    artifact_version = await _seed_standard_artifact_version(
        db_session,
        project_id=task_project.id,
        user_id=admin_user.id,
        status="deleted",
    )

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "project_id": task_project.id,
            "params": {},
            "input_bindings": {"protein": artifact_version.id},
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_task_rejects_project_id_without_membership(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    direct_runner_stub: SimpleNamespace,
):
    """用户不是项目成员时，不能把任务挂到该项目下。"""
    organization = Organization(name="Other Lab", slug="other-lab")
    db_session.add(organization)
    await db_session.flush()
    project = Project(
        organization_id=organization.id,
        created_by="other-user",
        name="Other Project",
        status="active",
    )
    db_session.add(project)
    await db_session.commit()

    response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "project_id": project.id,
            "params": {"foo": "bar"},
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_and_detail_support_task_name_and_name_keyword_search(
    api_client: httpx.AsyncClient,
    published_tool: Tool,
    direct_runner_stub: SimpleNamespace,
):
    """任务列表和详情应返回任务名，且 keyword 能命中任务名。"""
    create_response = await api_client.post(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "tool_id": published_tool.id,
            "name": "Affinity Batch Alpha",
            "params": {"foo": "bar"},
        },
    )
    task_id = create_response.json()["data"]["id"]

    list_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
        params={"keyword": "Batch Alpha"},
    )
    assert list_response.status_code == 200
    items = list_response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == task_id
    assert items[0]["name"] == "Affinity Batch Alpha"

    detail_response = await api_client.get(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["name"] == "Affinity Batch Alpha"


@pytest.mark.asyncio
async def test_existing_task_without_name_returns_fallback_display_name(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    published_tool: Tool,
):
    """历史空任务名记录也应返回可显示的回退标题。"""
    task = Task(
        user_id=admin_user.id,
        tool_id=published_tool.id,
        tool_version_id=published_tool.current_version_id,
        status=TaskStatus.SUCCESS.value,
        priority="normal",
        progress=1.0,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskInput(task_id=task.id, params={"foo": "bar"}, file_ids=[]))
    await db_session.commit()

    detail_response = await api_client.get(
        f"/api/v1/tasks/{task.id}",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["name"].startswith("Molecular Docking ")

    list_response = await api_client.get(
        "/api/v1/tasks",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert list_response.status_code == 200
    matched = [item for item in list_response.json()["data"]["items"] if item["id"] == task.id]
    assert len(matched) == 1
    assert matched[0]["name"].startswith("Molecular Docking ")


def test_task_name_sql_migration_script_exists() -> None:
    """应提供给现有数据库补列的 SQL 迁移脚本。"""
    script_path = PROJECT_ROOT / "backend" / "scripts" / "add_task_name_column.sql"

    assert script_path.exists() is True

    source = script_path.read_text(encoding="utf-8")
    assert "ALTER TABLE tasks ADD COLUMN name" in source
    assert "CREATE INDEX" in source
    assert "tasks_name" in source


# ========== 共享工具函数单元测试 ==========


class TestSanitizeTaskName:
    def test_returns_none_for_none(self):
        assert _sanitize_task_name(None) is None

    def test_strips_whitespace(self):
        assert _sanitize_task_name("  hello  ") == "hello"

    def test_returns_none_for_empty_or_whitespace(self):
        assert _sanitize_task_name("") is None
        assert _sanitize_task_name("   ") is None


class TestBuildDefaultTaskName:
    def test_with_tool_name_and_created_at(self):
        dt = datetime(2024, 1, 2, 13, 45)
        assert _build_default_task_name(
            tool_name="Vina",
            created_at=dt,
            task_id="abc-123",
        ) == "Vina 2024-01-02 13:45"

    def test_falls_back_to_tool_name(self):
        assert _build_default_task_name(
            tool_name="Vina",
            created_at=None,
            task_id="abc-123",
        ) == "Vina"

    def test_falls_back_to_task_id(self):
        assert _build_default_task_name(
            tool_name=None,
            created_at=None,
            task_id="abc-123-def",
        ) == "Task abc-123-"

    def test_falls_back_to_task(self):
        assert _build_default_task_name(
            tool_name=None,
            created_at=None,
            task_id=None,
        ) == "Task"


class TestResolveTaskDisplayName:
    def test_uses_name_when_present(self):
        assert resolve_task_display_name(
            name="My Task",
            tool_name="Vina",
            created_at=datetime(2024, 1, 2, 13, 45),
            task_id="abc",
        ) == "My Task"

    def test_falls_back_to_default(self):
        assert resolve_task_display_name(
            name="  ",
            tool_name="Vina",
            created_at=None,
            task_id="abc",
        ) == "Vina"


class TestDedupeFileIds:
    def test_preserves_order_and_removes_duplicates(self):
        assert _dedupe_file_ids(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

    def test_skips_empty_values(self):
        assert _dedupe_file_ids(["a", "", None, "b"]) == ["a", "b"]


class TestExtractFileIdsFromResult:
    def test_empty_for_non_dict(self):
        assert _extract_file_ids_from_result("not a dict") == []

    def test_extracts_direct_output_file_ids(self):
        result = {"output_file_ids": ["a", "b"]}
        assert _extract_file_ids_from_result(result) == ["a", "b"]

    def test_extracts_nested_output_file_ids(self):
        result = {"result": {"output_file_ids": ["c", "d"]}}
        assert _extract_file_ids_from_result(result) == ["c", "d"]

    def test_combines_direct_and_nested(self):
        result = {
            "output_file_ids": ["a"],
            "result": {"output_file_ids": ["b"]},
        }
        assert _extract_file_ids_from_result(result) == ["a", "b"]

    def test_dedupe_and_skip_empty(self):
        result = {
            "output_file_ids": ["a", "", "a"],
            "result": {"output_file_ids": [None, "a", "b"]},
        }
        assert _extract_file_ids_from_result(result, dedupe=True, skip_empty=True) == ["a", "b"]

    def test_no_dedupe_by_default(self):
        result = {"output_file_ids": ["a", "a"]}
        assert _extract_file_ids_from_result(result) == ["a", "a"]
