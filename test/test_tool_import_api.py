"""工具配置导入 API 测试。"""

from __future__ import annotations

import sys
import hashlib
from pathlib import Path

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
from app.agents.aidd.registry import load_available_tool_capabilities
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tool_capabilities as _tool_capability_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.files import File as FileModel
from app.models.tool_capabilities import ToolCapability
from app.models.tasks import Task
from app.models.tools import (
    Tool,
    ToolCategory,
    ToolProviderType,
    ToolReviewStatus,
    ToolStatus,
    ToolVersion,
)
from app.models.users import User, UserRole, UserStatus
from app.remote_tools.client import RemoteToolDiscoveryResult
from app.remote_tools.diagnostics import RemoteToolStageDiagnostic
from app.remote_tools.schemas import RemoteToolExamplesResponse, RemoteToolManifest


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


def build_remote_tool_manifest(version: str = "1.0.0") -> dict:
    """构造 remote-tool.v1 manifest。"""
    return {
        "api_version": "aidd.sciminer/remote-tool.v1",
        "kind": "RemoteTool",
        "metadata": {
            "slug": "lvpocket-api",
            "name": "LVpocket API",
            "version": version,
            "description": "Pocket prediction service",
        },
        "artifacts": {
            "inputs": [
                {"name": "protein", "type": "protein_structure@1", "required": True}
            ],
            "outputs": [
                {
                    "name": "pocket",
                    "type": "binding_pocket@1",
                    "cardinality": "one",
                    "required": True,
                }
            ],
        },
        "parameters_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "endpoints": {
            "invoke": "/invoke",
            "status": "/runs/{remote_run_id}",
            "logs": "/runs/{remote_run_id}/logs",
            "cancel": "/runs/{remote_run_id}/cancel",
            "artifacts": "/runs/{remote_run_id}/artifacts",
            "examples": "/examples",
            "health": "/health",
        },
        "capabilities": {"async": True, "logs": True, "cancel": True, "progress": True},
    }


def successful_remote_discovery(version: str = "1.0.0") -> RemoteToolDiscoveryResult:
    return RemoteToolDiscoveryResult(
        manifest=RemoteToolManifest.model_validate(build_remote_tool_manifest(version=version)),
        health={"status": "healthy"},
        examples=RemoteToolExamplesResponse.model_validate({"examples": []}),
        stages=[
            RemoteToolStageDiagnostic(
                name="fetch_manifest",
                status="success",
                message="Loaded",
            ),
            RemoteToolStageDiagnostic(
                name="validate_manifest",
                status="success",
                message="Manifest is valid",
            ),
            RemoteToolStageDiagnostic(
                name="health_check",
                status="success",
                message="Loaded",
            ),
            RemoteToolStageDiagnostic(
                name="fetch_examples",
                status="success",
                message="Loaded",
            ),
        ],
    )


def successful_remote_discovery_with_smoke_example(version: str = "1.0.0") -> RemoteToolDiscoveryResult:
    result = successful_remote_discovery(version=version)
    result.examples = RemoteToolExamplesResponse.model_validate(
        {
            "examples": [
                {
                    "name": "default",
                    "smoke": True,
                    "parameters": {"threshold": 0.5},
                    "input_artifacts": {},
                }
            ]
        }
    )
    return result


def successful_remote_discovery_with_smoke_files(version: str = "1.0.0") -> RemoteToolDiscoveryResult:
    structure_content = "ATOM\n"
    metadata_content = '{"chain_ids":["A"]}'
    result = successful_remote_discovery(version=version)
    result.examples = RemoteToolExamplesResponse.model_validate(
        {
            "examples": [
                {
                    "name": "default-with-files",
                    "smoke": True,
                    "parameters": {"threshold": 0.5},
                    "input_artifacts": {
                        "protein": {
                            "type": "protein_structure@1",
                            "metadata": {"chain_ids": ["A"]},
                            "files": {
                                "structure_file": {
                                    "filename": "protein.pdb",
                                    "content_type": "chemical/x-pdb",
                                    "encoding": "text",
                                    "content": structure_content,
                                    "sha256": hashlib.sha256(
                                        structure_content.encode("utf-8")
                                    ).hexdigest(),
                                },
                                "metadata_json": {
                                    "filename": "metadata.json",
                                    "content_type": "application/json",
                                    "encoding": "text",
                                    "content": metadata_content,
                                    "sha256": hashlib.sha256(
                                        metadata_content.encode("utf-8")
                                    ).hexdigest(),
                                },
                            },
                        }
                    },
                }
            ]
        }
    )
    return result


def successful_remote_discovery_with_bad_smoke_file(version: str = "1.0.0") -> RemoteToolDiscoveryResult:
    result = successful_remote_discovery_with_smoke_files(version=version)
    result.examples.examples[0].input_artifacts["protein"].files["structure_file"].sha256 = "0" * 64
    return result


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


def build_invalid_workflow_capability_config(version: str = "1.0.0") -> dict:
    config = build_remote_api_config(version=version)
    config["tool_config"]["agent_capability"] = {
        "enabled": True,
        "capability": "molecule_generation",
        "stage": "molecule_generation",
        "inputs": [],
        "outputs": [],
    }
    return config


def build_agent_capability_config(version: str = "1.0.0") -> dict:
    """构造包含有效 AIDD 能力声明的导入配置。"""
    config = build_remote_api_config(version=version)
    config["tool_config"]["agent_capability"] = {
        "enabled": True,
        "capability": "molecule_generation",
        "stage": "molecule_generation",
        "inputs": [{"semantic_type": "pocket_pdb", "field": "pocket_file"}],
        "outputs": [
            {
                "semantic_type": "sdf",
                "source": "output_files",
                "match": {"extension": ".sdf"},
            }
        ],
    }
    return config


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
async def test_admin_can_list_drug_discovery_tool_templates(
    api_client: httpx.AsyncClient,
):
    """管理员可以浏览药物研发工具模板。"""
    response = await api_client.get(
        "/api/v1/tool-templates",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    template_by_key = {item["template_key"]: item for item in payload}
    assert "vina-docking" in template_by_key
    assert template_by_key["vina-docking"]["capability"] == "molecular_docking"
    assert template_by_key["vina-docking"]["resource_profile"]["tier"] == "medium"
    assert "docker_image" in template_by_key["vina-docking"]["executor_types"]
    assert template_by_key["vina-docking"]["implementation"]["provider"] == "AutoDock Vina"
    assert template_by_key["vina-docking"]["implementation"]["recommended_executor"] == "docker_image"


@pytest.mark.asyncio
async def test_admin_can_create_tool_draft_from_drug_discovery_template(
    api_client: httpx.AsyncClient,
    enabled_category: ToolCategory,
):
    """管理员可以从模板和执行器配置创建现有 Tool 草稿。"""
    response = await api_client.post(
        "/api/v1/tool-templates/vina-docking/draft",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "category_id": enabled_category.id,
            "executor_type": "docker_image",
            "executor_config": {
                "image": "ghcr.io/sciminer/vina:latest",
                "command": ["/app/run"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["created_new_tool"] is True
    assert payload["tool"]["slug"] == "vina-docking"
    assert payload["tool"]["status"] == "draft"
    assert payload["tool"]["category_id"] == enabled_category.id
    config = payload["version"]["config"]
    assert config["type"] == "docker_image"
    assert config["image"] == "ghcr.io/sciminer/vina:latest"
    assert config["tool_family"] == "drug_discovery"
    assert config["resource_profile"]["tier"] == "medium"
    assert config["output_schema"]["properties"]["result_version"]["const"] == (
        "aidd.sciminer/result.v2"
    )


@pytest.mark.asyncio
async def test_regular_user_cannot_create_tool_draft_from_template(
    api_client: httpx.AsyncClient,
    enabled_category: ToolCategory,
):
    """普通用户不能从模板创建工具草稿。"""
    response = await api_client.post(
        "/api/v1/tool-templates/vina-docking/draft",
        headers={"Authorization": "Bearer user-token"},
        json={
            "category_id": enabled_category.id,
            "executor_type": "docker_image",
            "executor_config": {
                "image": "ghcr.io/sciminer/vina:latest",
                "command": ["/app/run"],
            },
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_register_remote_tool_from_service_manifest(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    enabled_category: ToolCategory,
    monkeypatch: pytest.MonkeyPatch,
):
    """管理员只提供服务根 URL 即可注册 remote-tool.v1 草稿。"""

    class FakeDiscoveryClient:
        def __init__(self, base_url: str, **_kwargs):
            assert base_url == "https://model.example.com"

        async def discover(self) -> RemoteToolDiscoveryResult:
            return successful_remote_discovery()

    monkeypatch.setattr(
        "app.api.v1.tools_admin.RemoteToolDiscoveryClient",
        FakeDiscoveryClient,
    )

    response = await api_client.post(
        "/api/v1/tools/register-remote",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "base_url": "https://model.example.com",
            "category_id": enabled_category.id,
            "run_smoke_test": False,
            "publish_on_success": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["created_new_tool"] is True
    assert payload["tool"]["slug"] == "lvpocket-api"
    assert payload["tool"]["category_id"] == enabled_category.id
    assert payload["tool"]["status"] == "draft"
    assert payload["version"]["version"] == "1.0.0"
    assert payload["smoke_test_task_id"] is None
    assert payload["stages"][-1]["name"] == "persist_draft"
    assert payload["stages"][-1]["status"] == "success"

    tool = await db_session.scalar(select(Tool).where(Tool.slug == "lvpocket-api"))
    assert tool is not None
    version = await db_session.scalar(
        select(ToolVersion).where(ToolVersion.tool_id == tool.id)
    )
    assert version is not None
    assert version.config["type"] == "remote_api"
    assert version.config["mode"] == "remote_tool_v1"
    assert version.config["base_url"] == "https://model.example.com"
    assert version.config["tool_slug"] == "lvpocket-api"
    assert len(version.config["manifest_sha256"]) == 64
    assert version.config["manifest"]["metadata"]["slug"] == "lvpocket-api"


@pytest.mark.asyncio
async def test_register_remote_tool_rejects_published_version_overwrite(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    enabled_category: ToolCategory,
    monkeypatch: pytest.MonkeyPatch,
):
    """已发布的 slug + version 不能被自注册静默覆盖。"""
    tool = Tool(
        owner_id=admin_user.id,
        name="LVpocket API",
        slug="lvpocket-api",
        description="Published version",
        category_id=enabled_category.id,
        category=enabled_category.name,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
        review_status=ToolReviewStatus.NOT_REQUIRED.value,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "remote_api", "mode": "remote_tool_v1"},
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()

    class FakeDiscoveryClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def discover(self) -> RemoteToolDiscoveryResult:
            return successful_remote_discovery(version="1.0.0")

    monkeypatch.setattr(
        "app.api.v1.tools_admin.RemoteToolDiscoveryClient",
        FakeDiscoveryClient,
    )

    response = await api_client.post(
        "/api/v1/tools/register-remote",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "base_url": "https://model.example.com",
            "category_id": enabled_category.id,
            "run_smoke_test": False,
            "publish_on_success": False,
        },
    )

    assert response.status_code == 409
    assert "已发布版本不能覆盖" in response.json()["message"]


@pytest.mark.asyncio
async def test_register_remote_tool_schedules_smoke_test_when_requested(
    api_client: httpx.AsyncClient,
    enabled_category: ToolCategory,
    monkeypatch: pytest.MonkeyPatch,
):
    """注册时请求 smoke test 应创建平台任务并返回任务 ID。"""
    scheduled: list[dict] = []

    class FakeDiscoveryClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def discover(self) -> RemoteToolDiscoveryResult:
            return successful_remote_discovery_with_smoke_example()

    async def fake_create_and_schedule_tool_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append({
            "params": task_data.params,
            "extra_data": kwargs.get("extra_data"),
        })
        return Task(id="smoke-task-id")

    monkeypatch.setattr(
        "app.api.v1.tools_admin.RemoteToolDiscoveryClient",
        FakeDiscoveryClient,
    )
    monkeypatch.setattr(
        "app.api.v1.tool_route_utils.create_and_schedule_tool_task",
        fake_create_and_schedule_tool_task,
    )

    response = await api_client.post(
        "/api/v1/tools/register-remote",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "base_url": "https://model.example.com",
            "category_id": enabled_category.id,
            "run_smoke_test": True,
            "publish_on_success": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["smoke_test_task_id"] == "smoke-task-id"
    assert payload["stages"][-1]["name"] == "create_smoke_test"
    assert payload["stages"][-1]["status"] == "success"
    assert scheduled[0]["params"] == {"threshold": 0.5}
    assert scheduled[0]["extra_data"]["smoke_test"] is True
    assert scheduled[0]["extra_data"]["publish_on_success"] is True


@pytest.mark.asyncio
async def test_register_remote_tool_records_scheduled_smoke_test(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    enabled_category: ToolCategory,
    monkeypatch: pytest.MonkeyPatch,
):
    """创建 smoke 任务后应立即在版本配置中记录可追踪任务。"""

    class FakeDiscoveryClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def discover(self) -> RemoteToolDiscoveryResult:
            return successful_remote_discovery_with_smoke_example()

    async def fake_create_and_schedule_tool_task(**_kwargs):
        return Task(id="smoke-task-id")

    monkeypatch.setattr(
        "app.api.v1.tools_admin.RemoteToolDiscoveryClient",
        FakeDiscoveryClient,
    )
    monkeypatch.setattr(
        "app.api.v1.tool_route_utils.create_and_schedule_tool_task",
        fake_create_and_schedule_tool_task,
    )

    response = await api_client.post(
        "/api/v1/tools/register-remote",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "base_url": "https://model.example.com",
            "category_id": enabled_category.id,
            "run_smoke_test": True,
            "publish_on_success": False,
        },
    )

    assert response.status_code == 200
    tool = await db_session.scalar(select(Tool).where(Tool.slug == "lvpocket-api"))
    assert tool is not None
    version = await db_session.get(ToolVersion, tool.current_version_id)
    assert version is not None
    assert version.config["last_smoke_test"]["status"] == "scheduled"
    assert version.config["last_smoke_test"]["task_id"] == "smoke-task-id"
    assert (
        version.config["last_smoke_test"]["manifest_sha256"]
        == response.json()["data"]["manifest_sha256"]
    )
    assert version.config["last_smoke_test"]["example_name"] == "default"


@pytest.mark.asyncio
async def test_register_remote_tool_materializes_smoke_example_files(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    enabled_category: ToolCategory,
    monkeypatch: pytest.MonkeyPatch,
):
    """远端 examples 返回的样例文件会落到平台文件表并传入 smoke 任务。"""
    scheduled: list[dict] = []

    class FakeDiscoveryClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def discover(self) -> RemoteToolDiscoveryResult:
            return successful_remote_discovery_with_smoke_files()

    async def fake_create_and_schedule_tool_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append({
            "file_ids": list(task_data.file_ids),
            "extra_data": kwargs.get("extra_data"),
        })
        return Task(id="smoke-task-id")

    monkeypatch.setattr(
        "app.api.v1.tools_admin.RemoteToolDiscoveryClient",
        FakeDiscoveryClient,
    )
    monkeypatch.setattr(
        "app.api.v1.tool_route_utils.create_and_schedule_tool_task",
        fake_create_and_schedule_tool_task,
    )
    response = await api_client.post(
        "/api/v1/tools/register-remote",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "base_url": "https://model.example.com",
            "category_id": enabled_category.id,
            "run_smoke_test": True,
            "publish_on_success": False,
        },
    )

    assert response.status_code == 200
    assert len(scheduled[0]["file_ids"]) == 2
    example_inputs = scheduled[0]["extra_data"]["remote_example_inputs"]
    role_file_id = example_inputs["protein"]["files"]["structure_file"]
    file_record = await db_session.get(FileModel, role_file_id)
    assert file_record is not None
    assert file_record.filename == "protein.pdb"
    assert Path(file_record.storage_path).read_text(encoding="utf-8") == "ATOM\n"
    assert role_file_id in scheduled[0]["file_ids"]


@pytest.mark.asyncio
async def test_register_remote_tool_keeps_draft_when_smoke_example_is_bad(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    enabled_category: ToolCategory,
    monkeypatch: pytest.MonkeyPatch,
):
    """smoke test 创建失败不应丢掉已注册草稿。"""

    class FakeDiscoveryClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def discover(self) -> RemoteToolDiscoveryResult:
            return successful_remote_discovery_with_bad_smoke_file()

    monkeypatch.setattr(
        "app.api.v1.tools_admin.RemoteToolDiscoveryClient",
        FakeDiscoveryClient,
    )

    response = await api_client.post(
        "/api/v1/tools/register-remote",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "base_url": "https://model.example.com",
            "category_id": enabled_category.id,
            "run_smoke_test": True,
            "publish_on_success": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["tool"]["status"] == "draft"
    assert payload["smoke_test_task_id"] is None
    assert payload["stages"][-1]["name"] == "create_smoke_test"
    assert payload["stages"][-1]["status"] == "failure"
    tool = await db_session.scalar(select(Tool).where(Tool.slug == "lvpocket-api"))
    assert tool is not None


@pytest.mark.asyncio
async def test_publish_remote_tool_requires_successful_smoke_test(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    enabled_category: ToolCategory,
):
    """remote_tool_v1 当前版本发布前必须有成功且匹配 manifest 的 smoke test。"""
    tool = Tool(
        owner_id=admin_user.id,
        name="LVpocket API",
        slug="lvpocket-api",
        description="Remote tool",
        category_id=enabled_category.id,
        category=enabled_category.name,
        status=ToolStatus.DRAFT.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
        review_status=ToolReviewStatus.NOT_REQUIRED.value,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "remote_api",
            "mode": "remote_tool_v1",
            "manifest_sha256": "a" * 64,
            "manifest": build_remote_tool_manifest(),
        },
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()

    response = await api_client.post(
        f"/api/v1/tools/{tool.id}/publish",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 422
    assert "smoke test" in response.json()["message"]


@pytest.mark.asyncio
async def test_publish_remote_tool_accepts_matching_successful_smoke_test(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    enabled_category: ToolCategory,
):
    """remote_tool_v1 成功 smoke test 摘要与当前 manifest 匹配时可以发布。"""
    manifest_hash = "a" * 64
    tool = Tool(
        owner_id=admin_user.id,
        name="LVpocket API",
        slug="lvpocket-api-success",
        description="Remote tool",
        category_id=enabled_category.id,
        category=enabled_category.name,
        status=ToolStatus.DRAFT.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
        review_status=ToolReviewStatus.NOT_REQUIRED.value,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "remote_api",
            "mode": "remote_tool_v1",
            "manifest_sha256": manifest_hash,
            "manifest": build_remote_tool_manifest(),
            "last_smoke_test": {
                "status": "success",
                "task_id": "smoke-task-id",
                "manifest_sha256": manifest_hash,
            },
        },
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()

    response = await api_client.post(
        f"/api/v1/tools/{tool.id}/publish",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200


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
async def test_import_tool_config_syncs_agent_capability(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """带能力声明的已发布工具导入后应立即可被 AIDD 注册表发现。"""
    response = await api_client.post(
        "/api/v1/tools/import-config",
        headers={"Authorization": "Bearer admin-token"},
        json={"config": build_agent_capability_config(), "publish": True},
    )

    assert response.status_code == 200
    tool_id = response.json()["data"]["tool"]["id"]

    capability = await db_session.scalar(
        select(ToolCapability).where(ToolCapability.tool_id == tool_id)
    )
    assert capability is not None
    assert capability.capability == "molecule_generation"
    assert capability.stage == "molecule_generation"
    assert capability.inputs == [{"semantic_type": "pocket_pdb", "field": "pocket_file"}]
    assert capability.outputs == [
        {
            "semantic_type": "sdf",
            "source": "output_files",
            "match": {"extension": ".sdf"},
        }
    ]

    available_capabilities = await load_available_tool_capabilities(db_session)
    assert any(item.tool_slug == "targetdiff-service" for item in available_capabilities)


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


@pytest.mark.asyncio
async def test_import_tool_config_rejects_invalid_enabled_agent_capability(
    api_client: httpx.AsyncClient,
):
    """导入时应拒绝启用但不完整的工作流能力配置。"""
    response = await api_client.post(
        "/api/v1/tools/import-config",
        headers={"Authorization": "Bearer admin-token"},
        json={"config": build_invalid_workflow_capability_config()},
    )

    assert response.status_code == 422
    assert "agent_capability.outputs" in response.json()["message"]


@pytest.mark.asyncio
async def test_publish_tool_rejects_invalid_current_version_contract(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
):
    """发布时应拒绝当前版本契约无效的工具。"""
    tool = Tool(
        owner_id=admin_user.id,
        name="Broken Workflow Tool",
        slug="broken-workflow-tool",
        description="Broken workflow capability",
        category="generation",
        status=ToolStatus.DRAFT.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
        review_status=ToolReviewStatus.NOT_REQUIRED.value,
        timeout_sec=120,
    )
    db_session.add(tool)
    await db_session.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="0.1.0",
        changelog="Initial import",
        config=build_invalid_workflow_capability_config()["tool_config"],
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()

    tool.current_version_id = version.id
    await db_session.commit()

    response = await api_client.post(
        f"/api/v1/tools/{tool.id}/publish",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 422
    assert "agent_capability.inputs" in response.json()["message"]


@pytest.mark.asyncio
async def test_get_tool_contract_returns_actionable_validation_errors(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
):
    """查询契约时应返回可操作的校验错误。"""
    tool = Tool(
        owner_id=admin_user.id,
        name="Broken Contract Tool",
        slug="broken-contract-tool",
        description="Broken contract capability",
        category="generation",
        status=ToolStatus.DRAFT.value,
        is_public=False,
        provider_type=ToolProviderType.PLATFORM.value,
        review_status=ToolReviewStatus.NOT_REQUIRED.value,
        timeout_sec=120,
    )
    db_session.add(tool)
    await db_session.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="0.1.0",
        changelog="Initial import",
        config=build_invalid_workflow_capability_config()["tool_config"],
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()

    tool.current_version_id = version.id
    await db_session.commit()

    response = await api_client.get(
        f"/api/v1/tools/{tool.id}/contract",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["validation"]["status"] == "invalid"
    assert any("agent_capability.inputs" in error for error in payload["validation"]["errors"])


@pytest.mark.asyncio
async def test_public_tool_versions_require_public_tool_and_redact_runtime_config(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
):
    public_tool = Tool(
        owner_id=admin_user.id,
        name="Published Runtime Tool",
        slug="published-runtime-tool",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    private_tool = Tool(
        owner_id=admin_user.id,
        name="Draft Runtime Tool",
        slug="draft-runtime-tool",
        status=ToolStatus.DRAFT.value,
        is_public=True,
    )
    db_session.add_all([public_tool, private_tool])
    await db_session.flush()

    config = {
        "type": "docker_image",
        "endpoint": "https://internal.example/run",
        "headers": {"Authorization": "Bearer secret"},
        "image": "private.registry/tool:latest",
        "command": ["/srv/private-runner"],
        "input_schema": {
            "type": "object",
            "properties": {"protein": {"type": "string"}},
        },
    }
    public_version = ToolVersion(
        tool_id=public_tool.id,
        version="1.0.0",
        changelog="Initial",
        config=config,
        is_active=True,
    )
    private_version = ToolVersion(
        tool_id=private_tool.id,
        version="0.1.0",
        changelog="Draft",
        config=config,
        is_active=True,
    )
    db_session.add_all([public_version, private_version])
    await db_session.flush()
    public_tool.current_version_id = public_version.id
    private_tool.current_version_id = private_version.id
    await db_session.commit()

    public_response = await api_client.get(
        f"/api/v1/tools/{public_tool.id}/versions"
    )
    draft_response = await api_client.get(
        f"/api/v1/tools/{private_tool.id}/versions"
    )
    draft_example_response = await api_client.get(
        f"/api/v1/tools/{private_tool.id}/example"
    )

    assert public_response.status_code == 200
    public_version = public_response.json()["data"][0]
    assert public_version["version"] == "1.0.0"
    assert "config" not in public_version
    assert "endpoint" not in public_version
    assert "headers" not in public_version
    assert "script_content" not in public_version
    assert draft_response.status_code == 404
    assert draft_example_response.status_code == 404
