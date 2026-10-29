"""管理员系统路由测试。"""

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

from app.auth.dependencies import get_current_user
from app.auth.password import hash_password
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tools as _tool_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.tasks import Task
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
        password_hash=hash_password("AdminSecret123"),
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

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "expected_keys"),
    [
        ("/api/v1/system/info", {"app_name", "app_version", "environment"}),
        ("/api/v1/system/stats", {"total_users", "total_tools", "total_tasks"}),
        ("/api/v1/system/config", {"environment", "database", "storage"}),
        ("/api/v1/system/feature-flags", {"environment", "items", "total"}),
    ],
)
async def test_admin_system_routes_use_standard_response_shape(
    api_client: httpx.AsyncClient,
    path: str,
    expected_keys: set[str],
):
    """管理员系统接口应返回统一响应结构。"""
    response = await api_client.get(
        path,
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert expected_keys.issubset(payload["data"].keys())


@pytest.mark.asyncio
async def test_resource_workers_exposes_capability_and_dynamic_usage(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """管理员资源页应能读取 Worker 静态能力和动态租约占用。"""
    from app.cache.memory import MemoryCacheBackend
    from app.tasks.resource_admission import WorkerCapability
    from app.tasks.resource_lease import WorkerResourceLeaseManager
    from app.tasks.resource_profile import ResourceRequest
    from app.tasks.worker_capability_registry import WorkerCapabilityRegistry

    cache = MemoryCacheBackend()
    registry = WorkerCapabilityRegistry(cache=cache, ttl_seconds=60)
    capability = WorkerCapability(
        worker_id="admin-resource-worker",
        queue="admin-resource-queue",
        executor_types=("docker_image",),
        tiers=("heavy",),
        cpu_capacity=8,
        memory_capacity_gb=16,
        parallelism=2,
    )
    await registry.register(capability)
    await WorkerResourceLeaseManager(cache=cache).acquire(
        capability=capability,
        request=ResourceRequest(
            executor_type="docker_image",
            tier="heavy",
            cpu=4,
            memory_gb=8,
            cpu_limit=4,
            memory_limit="8g",
            gpu_required=False,
            gpu_count=0,
            gpu_memory_mb=0,
            timeout_sec=600,
            parallelism=1,
        ),
        lease_id="admin-resource-task",
        lease_phase="running",
    )
    await WorkerResourceLeaseManager(cache=cache).acquire(
        capability=capability,
        request=ResourceRequest(
            executor_type="docker_image",
            tier="heavy",
            cpu=1,
            memory_gb=1,
            cpu_limit=1,
            memory_limit="1g",
            gpu_required=False,
            gpu_count=0,
            gpu_memory_mb=0,
            timeout_sec=600,
            parallelism=1,
        ),
        lease_id="admin-resource-reservation",
        lease_phase="reserved",
    )
    monkeypatch.setattr("app.cache.get_cache", lambda: cache)

    response = await api_client.get(
        "/api/v1/system/resource-workers",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "healthy"
    assert payload["total_workers"] == 1
    assert payload["workers"][0]["worker_id"] == "admin-resource-worker"
    assert payload["workers"][0]["queue"] == "admin-resource-queue"
    assert payload["workers"][0]["cpu_used"] == 5.0
    assert payload["workers"][0]["cpu_available"] == 3.0
    assert payload["workers"][0]["parallelism_used"] == 2
    assert payload["workers"][0]["reservation_count"] == 1
    assert payload["workers"][0]["execution_count"] == 1


@pytest.mark.asyncio
async def test_resource_quotas_exposes_scope_usage_and_rejections(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """管理员资源页应能读取用户和项目 scope 的配额占用。"""
    from app.cache.memory import MemoryCacheBackend
    from app.tasks.resource_admission import WorkerCapability
    from app.tasks.resource_lease import WorkerResourceLeaseManager
    from app.tasks.resource_profile import ResourceRequest
    from app.tasks.resource_quota import ResourceQuotaManager

    monkeypatch.setattr("app.config.settings.RESOURCE_SCOPE_QUOTA_ENABLED", True)
    monkeypatch.setattr("app.config.settings.RESOURCE_USER_MAX_CPU", 8)
    monkeypatch.setattr("app.config.settings.RESOURCE_USER_MAX_MEMORY_GB", 16)
    monkeypatch.setattr("app.config.settings.RESOURCE_USER_MAX_PARALLELISM", 2)
    monkeypatch.setattr("app.config.settings.RESOURCE_PROJECT_MAX_CPU", 12)
    monkeypatch.setattr("app.config.settings.RESOURCE_PROJECT_MAX_MEMORY_GB", 24)
    monkeypatch.setattr("app.config.settings.RESOURCE_PROJECT_MAX_PARALLELISM", 3)

    cache = MemoryCacheBackend()
    capability = WorkerCapability(
        worker_id="quota-admin-worker",
        cpu_capacity=16,
        memory_capacity_gb=32,
        parallelism=4,
    )
    await WorkerResourceLeaseManager(cache=cache).acquire(
        capability=capability,
        request=ResourceRequest(
            executor_type="docker_image",
            tier="heavy",
            cpu=4,
            memory_gb=8,
            cpu_limit=4,
            memory_limit="8g",
            gpu_required=False,
            gpu_count=0,
            gpu_memory_mb=0,
            timeout_sec=600,
            parallelism=1,
        ),
        lease_id="quota-admin-task",
        user_id="quota-user",
        project_id="quota-project",
    )
    quota = ResourceQuotaManager(
        cache=cache,
        user_max_cpu=8,
        user_max_memory_gb=16,
        user_max_parallelism=2,
        project_max_cpu=12,
        project_max_memory_gb=24,
        project_max_parallelism=3,
    )
    await quota.record_rejection(
        scope_type="user",
        scope_id="quota-user",
        reason="user_cpu_quota_exhausted",
    )
    monkeypatch.setattr("app.cache.get_cache", lambda: cache)

    response = await api_client.get(
        "/api/v1/system/resource-quotas",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["enabled"] is True
    assert payload["gpu_scope_quota"] == "allocator_managed"
    scopes = {(item["scope_type"], item["scope_id"]): item for item in payload["scopes"]}
    assert scopes[("user", "quota-user")]["cpu_used"] == 4.0
    assert scopes[("user", "quota-user")]["cpu_limit"] == 8.0
    assert scopes[("user", "quota-user")]["rejection_counts"] == {
        "user_cpu_quota_exhausted": 1
    }
    assert scopes[("project", "quota-project")]["memory_used_gb"] == 8.0


@pytest.mark.asyncio
async def test_feature_flags_endpoint_exposes_aidd_release_gates(
    api_client: httpx.AsyncClient,
):
    """管理员应能审计首月 AIDD 发布门禁开关。"""
    response = await api_client.get(
        "/api/v1/system/feature-flags",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    items = {item["key"]: item for item in payload["items"]}
    expected_keys = {
        "AIDD_PROJECT_WORKSPACE_ENABLED",
        "TOOL_PACKAGE_V1_ENABLED",
        "LEGACY_AIDD_API_ENABLED",
    }

    assert set(items) == expected_keys
    assert payload["total"] == len(expected_keys)
    assert all(isinstance(item["enabled"], bool) for item in items.values())
    assert all(
        item["source"] in {"default", "configured", "environment"}
        for item in items.values()
    )
    assert all("rollout" in item for item in items.values())
    assert all(
        item["rollout"]["scope"] in {"all", "allowlist", "closed"}
        for item in items.values()
    )
    assert all(isinstance(item["rollout"]["user_count"], int) for item in items.values())


@pytest.mark.asyncio
async def test_system_health_reports_database_schema_revision(
    api_client: httpx.AsyncClient,
):
    """系统健康检查应暴露 Alembic schema 状态，避免迁移漏跑变成泛化 500。"""
    response = await api_client.get("/api/v1/system/health")

    assert response.status_code == 200
    payload = response.json()
    services = {item["name"]: item for item in payload["data"]["services"]}

    assert "database_schema" in services
    assert services["database_schema"]["status"] == "unhealthy"
    assert "Alembic" in services["database_schema"]["message"]
    assert payload["data"]["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_system_health_reports_tool_package_runtime_readiness(
    api_client: httpx.AsyncClient,
):
    """系统健康检查应暴露 Tool Package 运行时可用性，方便排查模型部署链路。"""
    response = await api_client.get("/api/v1/system/health")

    assert response.status_code == 200
    payload = response.json()
    services = {item["name"]: item for item in payload["data"]["services"]}

    assert "tool_package_runtime" in services
    assert services["tool_package_runtime"]["status"] in {"healthy", "unknown"}
    assert "Tool Package" in services["tool_package_runtime"]["message"]


@pytest.mark.asyncio
async def test_system_health_reports_executor_gateway_readiness(
    api_client: httpx.AsyncClient,
):
    """系统健康检查应暴露 Executor Gateway 和 V1 已登记执行器类型。"""
    response = await api_client.get("/api/v1/system/health")

    assert response.status_code == 200
    payload = response.json()
    services = {item["name"]: item for item in payload["data"]["services"]}

    assert "executor_gateway" in services
    assert services["executor_gateway"]["status"] == "healthy"
    message = services["executor_gateway"]["message"]
    assert "Executor Gateway" in message
    for executor_type in ("builtin", "python_script", "docker_image", "ssh_job"):
        assert executor_type in message
    assert "remote_api" not in message
