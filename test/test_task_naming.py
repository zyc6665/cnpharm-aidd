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
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
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
