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
from app.tools.capability_registry import load_available_tool_capabilities
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

@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/tools", None),
        ("post", "/api/v1/tools/import-config", None),
        ("post", "/api/v1/tools/register-remote", None),
        ("post", "/api/v1/tools/legacy-tool/versions", None),
        ("get", "/api/v1/tool-templates", None),
        ("post", "/api/v1/tool-templates/vina-docking/draft", None),
    ],
)
async def test_legacy_registration_entrypoints_are_retired(
    api_client: httpx.AsyncClient,
    method: str,
    path: str,
    payload: dict | None,
):
    """旧管理员注册入口只保留明确的下线响应，不影响已有工具运行。"""
    request = getattr(api_client, method)
    kwargs = {"headers": {"Authorization": "Bearer admin-token"}}
    if payload is not None:
        kwargs["json"] = payload

    response = await request(path, **kwargs)

    assert response.status_code == 410
    assert "Tool Package" in response.json()["detail"]


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
