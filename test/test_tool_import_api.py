"""工具配置导入 API 测试。"""

from __future__ import annotations

import sys
from pathlib import Path

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

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.tools import ToolCategory
from app.models.users import User, UserRole, UserStatus


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
async def regular_user(db_session: AsyncSession) -> User:
    """创建普通用户。"""
    user = User(
        email="user@example.com",
        password_hash="hashed-password",
        display_name="User",
        role=UserRole.USER.value,
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
    regular_user: User,
):
    """创建带依赖覆盖的 API 客户端。"""

    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == "Bearer admin-token":
            return admin_user
        if authorization == "Bearer user-token":
            return regular_user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    async def override_get_current_user_optional(
        authorization: str | None = Header(default=None),
    ) -> User | None:
        if authorization == "Bearer admin-token":
            return admin_user
        if authorization == "Bearer user-token":
            return regular_user
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def enabled_category(db_session: AsyncSession) -> ToolCategory:
    """创建可用工具分类。"""
    category = ToolCategory(
        name="Generation",
        slug="generation",
        sort_order=0,
        is_enabled=True,
    )
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


def build_remote_api_config(version: str = "1.0.0") -> dict:
    """构造导入配置。"""
    return {
        "name": "TargetDiff Service",
        "slug": "targetdiff-service",
        "description": "Pocket-conditioned molecule generation service",
        "category": "generation",
        "version": version,
        "changelog": "Initial import",
        "tool_config": {
            "type": "remote_api",
            "endpoint": "http://targetdiff.example/api/predict",
            "method": "post",
            "timeout": 120,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
            },
            "required": ["task_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
            },
        },
    }


def build_ssh_job_config(version: str = "1.0.0") -> dict:
    """构造 ssh_job 导入配置。"""
    return {
        "name": "TargetDiff SSH Job",
        "slug": "targetdiff-ssh-job",
        "description": "Reuse an existing remote TargetDiff container over SSH",
        "category": "generation",
        "version": version,
        "changelog": "Initial ssh_job import",
        "tool_config": {
            "type": "ssh_job",
            "host": "gpu-node-01.internal",
            "port": 22,
            "username": "platform_runner",
            "auth_ref": "ssh_gpu_node_01",
            "runner_mode": "docker_exec",
            "remote_base_dir": "/srv/platform-jobs",
            "container_base_dir": "/workspace/platform-jobs",
            "entrypoint": "/app/platform_run.sh",
            "container_name": "targetdiff-prod",
            "timeout_sec": 3600,
            "cleanup_remote": True,
            "strict_host_key_checking": True,
            "output_globs": [
                "output/result.json",
                "output/logs/run.log",
                "output/artifacts/**/*",
            ],
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "params": {"type": "object"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "artifacts": {"type": "array"},
            },
        },
    }


@pytest.mark.asyncio
async def test_admin_can_import_tool_config_and_normalize_legacy_schema(
    api_client: httpx.AsyncClient,
    enabled_category: ToolCategory,
):
    """管理员可以导入 platform_tool 配置并归一化旧字段。"""
    response = await api_client.post(
        "/api/v1/tools/import-config",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "config": build_remote_api_config(),
            "category_id": enabled_category.id,
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["created_new_tool"] is True
    assert payload["tool"]["slug"] == "targetdiff-service"
    assert payload["tool"]["category_id"] == enabled_category.id
    assert payload["tool"]["status"] == "draft"
    assert payload["version"]["version"] == "1.0.0"
    assert payload["version"]["config"]["method"] == "POST"
    assert payload["version"]["config"]["timeout_sec"] == 120
    assert payload["version"]["config"]["input_schema"]["required"] == ["task_id"]
    assert "output_schema" in payload["version"]["config"]


@pytest.mark.asyncio
async def test_import_tool_config_reuses_existing_tool_and_creates_new_version(
    api_client: httpx.AsyncClient,
):
    """同 slug 导入应复用工具并创建新版本。"""
    first_response = await api_client.post(
        "/api/v1/tools/import-config",
        headers={"Authorization": "Bearer admin-token"},
        json={"config": build_remote_api_config(version="1.0.0")},
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()["data"]

    second_response = await api_client.post(
        "/api/v1/tools/import-config",
        headers={"Authorization": "Bearer admin-token"},
        json={"config": build_remote_api_config(version="1.1.0")},
    )

    assert second_response.status_code == 200
    second_payload = second_response.json()["data"]
    assert second_payload["created_new_tool"] is False
    assert second_payload["tool"]["id"] == first_payload["tool"]["id"]
    assert second_payload["version"]["version"] == "1.1.0"
    assert second_payload["tool"]["current_version"]["version"] == "1.1.0"


@pytest.mark.asyncio
async def test_admin_can_import_ssh_job_tool_config(
    api_client: httpx.AsyncClient,
):
    """管理员可以导入 ssh_job 工具配置。"""
    response = await api_client.post(
        "/api/v1/tools/import-config",
        headers={"Authorization": "Bearer admin-token"},
        json={"config": build_ssh_job_config()},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["tool"]["slug"] == "targetdiff-ssh-job"
    assert payload["version"]["config"]["type"] == "ssh_job"
    assert payload["version"]["config"]["runner_mode"] == "docker_exec"
    assert payload["version"]["config"]["container_base_dir"] == "/workspace/platform-jobs"


@pytest.mark.asyncio
async def test_regular_user_cannot_import_tool_config(
    api_client: httpx.AsyncClient,
):
    """普通用户不能导入工具配置。"""
    response = await api_client.post(
        "/api/v1/tools/import-config",
        headers={"Authorization": "Bearer user-token"},
        json={"config": build_remote_api_config()},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_import_tool_config_rejects_invalid_config(
    api_client: httpx.AsyncClient,
):
    """非法导入配置会被拒绝。"""
    invalid_config = build_remote_api_config()
    invalid_config["tool_config"]["method"] = "DELETE"

    response = await api_client.post(
        "/api/v1/tools/import-config",
        headers={"Authorization": "Bearer admin-token"},
        json={"config": invalid_config},
    )

    assert response.status_code == 422
    assert "tool_config.method" in response.json()["message"]
