"""工具示例 API 测试。"""

from __future__ import annotations

import json
import sys
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

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.services import tool_examples


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
async def api_client(db_session: AsyncSession, regular_user: User):
    """创建带依赖覆盖的 API 客户端。"""

    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == "Bearer user-token":
            return regular_user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    async def override_get_current_user_optional(
        authorization: str | None = Header(default=None),
    ) -> User | None:
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


async def create_tool_with_config(db_session: AsyncSession, config: dict, slug: str = "example-tool") -> Tool:
    """创建带当前版本配置的工具。"""
    tool = Tool(
        owner_id="owner-id",
        name="Example Tool",
        slug=slug,
        description="Tool with examples",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config=config,
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()

    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


def test_resolve_example_base_dir_reuses_slug_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """未显式配置 example_base_dir 时，同一索引应复用而不是每次递归扫描。"""
    example_root = tmp_path / "example"
    tool_dir = example_root / "cached-tool"
    tool_dir.mkdir(parents=True)
    (tool_dir / "platform_tool.json").write_text(
        json.dumps({"slug": "cached-tool"}),
        encoding="utf-8",
    )
    original_rglob = Path.rglob
    scan_count = 0

    def counting_rglob(self: Path, pattern: str):
        nonlocal scan_count
        if self == example_root and pattern == "platform_tool*.json":
            scan_count += 1
        return original_rglob(self, pattern)

    monkeypatch.setattr(tool_examples, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(Path, "rglob", counting_rglob)

    tool = SimpleNamespace(slug="cached-tool")
    config: dict = {}

    assert tool_examples.resolve_example_base_dir(tool, config) == tool_dir.resolve()
    assert tool_examples.resolve_example_base_dir(tool, config) == tool_dir.resolve()
    assert scan_count == 1


@pytest.mark.asyncio
async def test_get_tool_example_returns_default_example_with_files(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
):
    """获取工具示例应返回参数与声明的示例文件元数据。"""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "protein.pdb").write_text("ATOM      1  N   GLY A   1\n", encoding="utf-8")
    tool = await create_tool_with_config(
        db_session,
        {
            "type": "ssh_job",
            "example_base_dir": str(tmp_path),
            "examples": [
                {
                    "name": "默认示例",
                    "description": "使用内置 PDB 文件",
                    "params": {"model_choice": "auto"},
                    "input_files": {"protein_pdb": "input/protein.pdb"},
                }
            ],
            "input_schema": {"type": "object", "properties": {}},
            "output_schema": {"type": "object", "properties": {}},
        },
    )

    response = await api_client.get(f"/api/v1/tools/{tool.id}/example")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["name"] == "默认示例"
    assert payload["params"] == {"model_choice": "auto"}
    assert payload["input_files"][0]["field"] == "protein_pdb"
    assert payload["input_files"][0]["filename"] == "protein.pdb"
    assert payload["input_files"][0]["exists"] is True
    assert payload["input_files"][0]["previewable"] is True


@pytest.mark.asyncio
async def test_get_tool_example_falls_back_to_schema_default_for_builtin_fetch_pdb(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """仅声明 schema 的内置查询工具也应在详情页暴露可一键填入的示例。"""
    tool = await create_tool_with_config(
        db_session,
        {
            "type": "builtin",
            "builtin_slug": "builtin-fetch-pdb",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pdb_id": {
                        "type": "string",
                        "title": "PDB ID",
                        "description": "RCSB PDB entry ID, e.g. 1ABC",
                    }
                },
                "required": ["pdb_id"],
            },
            "output_schema": {"type": "object", "properties": {}},
        },
        slug="builtin-fetch-pdb",
    )

    response = await api_client.get(f"/api/v1/tools/{tool.id}/example")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["name"] == "默认示例"
    assert payload["params"] == {"pdb_id": "1A2B"}
    assert payload["input_files"] == []


@pytest.mark.asyncio
async def test_tool_example_infers_file_input_from_schema_and_applies_it(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
):
    """文件输入工具没有显式 examples 时，应从 schema/default 与本地示例文件生成可应用示例。"""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "protein.pdb").write_text("ATOM      1  N   GLY A   1\n", encoding="utf-8")
    tool = await create_tool_with_config(
        db_session,
        {
            "type": "ssh_job",
            "example_base_dir": str(tmp_path),
            "input_schema": {
                "type": "object",
                "properties": {
                    "protein_pdb": {
                        "type": "string",
                        "format": "file",
                        "title": "Protein PDB",
                        "ui:accept": ".pdb",
                    },
                    "model_choice": {
                        "type": "string",
                        "default": "auto",
                    },
                    "device": {
                        "type": "string",
                        "default": "auto",
                    },
                },
                "required": ["protein_pdb"],
            },
            "output_schema": {"type": "object", "properties": {}},
        },
        slug="lvpocket-pocket-prediction",
    )

    response = await api_client.get(f"/api/v1/tools/{tool.id}/example")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["params"] == {"model_choice": "auto", "device": "auto"}
    assert payload["input_files"][0]["field"] == "protein_pdb"
    assert payload["input_files"][0]["path"] == "input/protein.pdb"
    assert payload["input_files"][0]["exists"] is True

    apply_response = await api_client.post(
        f"/api/v1/tools/{tool.id}/example/apply",
        headers={"Authorization": "Bearer user-token"},
    )

    assert apply_response.status_code == 200
    apply_payload = apply_response.json()["data"]
    assert apply_payload["params"] == {"model_choice": "auto", "device": "auto"}
    assert apply_payload["files"]["protein_pdb"]["filename"] == "protein.pdb"


@pytest.mark.asyncio
async def test_tool_package_v2_example_uses_parameter_schema_before_legacy_schema(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """Tool Package v2 详情页示例应贴合 parameters_schema，而不是旧 input_schema。"""
    tool = await create_tool_with_config(
        db_session,
        {
            "type": "ssh_job",
            "example_params": {"smiles_csv": "input/smiles.csv", "device": "cpu"},
            "input_schema": {
                "type": "object",
                "properties": {
                    "smiles_csv": {"type": "string", "format": "file", "ui:accept": ".csv"},
                    "device": {"type": "string", "default": "cpu"},
                },
            },
            "tool_package_manifest": {
                "api_version": "aidd.sciminer/tool-package.v2",
                "metadata": {"slug": "molp-pc-property-prediction", "version": "0.1.1"},
                "artifacts": {
                    "inputs": [{"name": "molecules", "type": "molecule_table@1", "required": True}],
                    "outputs": [],
                },
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "task_groups": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["Absorption", "Toxicology"],
                        }
                    },
                },
            },
        },
        slug="molp-pc-property-prediction",
    )

    response = await api_client.get(f"/api/v1/tools/{tool.id}/example")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["params"] == {"task_groups": ["Absorption", "Toxicology"]}
    assert payload["input_files"] == []


@pytest.mark.asyncio
async def test_tool_example_apply_registers_example_file_for_user(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
):
    """应用示例应把示例文件注册为当前用户可提交文件。"""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "protein.pdb").write_text("ATOM      1  N   GLY A   1\n", encoding="utf-8")
    tool = await create_tool_with_config(
        db_session,
        {
            "type": "ssh_job",
            "example_base_dir": str(tmp_path),
            "example_params": {
                "params": {"device": "cpu"},
                "input_files": {"protein_pdb": "input/protein.pdb"},
            },
            "input_schema": {"type": "object", "properties": {}},
            "output_schema": {"type": "object", "properties": {}},
        },
    )

    response = await api_client.post(
        f"/api/v1/tools/{tool.id}/example/apply",
        headers={"Authorization": "Bearer user-token"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["params"] == {"device": "cpu"}
    assert payload["files"]["protein_pdb"]["filename"] == "protein.pdb"
    assert payload["files"]["protein_pdb"]["id"]


@pytest.mark.asyncio
async def test_tool_example_file_preview_returns_text_content(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
):
    """示例文件预览应返回文本内容。"""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "protein.pdb").write_text("ATOM      1  N   GLY A   1\n", encoding="utf-8")
    tool = await create_tool_with_config(
        db_session,
        {
            "type": "ssh_job",
            "example_base_dir": str(tmp_path),
            "examples": [
                {
                    "name": "默认示例",
                    "params": {},
                    "input_files": {"protein_pdb": "input/protein.pdb"},
                }
            ],
            "input_schema": {"type": "object", "properties": {}},
            "output_schema": {"type": "object", "properties": {}},
        },
    )

    response = await api_client.get(f"/api/v1/tools/{tool.id}/example/files/protein_pdb/preview")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["filename"] == "protein.pdb"
    assert payload["previewable"] is True
    assert "ATOM" in payload["content"]
    assert payload["truncated"] is False


@pytest.mark.asyncio
async def test_tool_example_rejects_path_traversal(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
):
    """示例路径不能越过示例根目录。"""
    tool = await create_tool_with_config(
        db_session,
        {
            "type": "ssh_job",
            "example_base_dir": str(tmp_path),
            "examples": [
                {
                    "name": "默认示例",
                    "params": {},
                    "input_files": {"protein_pdb": "../secret.txt"},
                }
            ],
            "input_schema": {"type": "object", "properties": {}},
            "output_schema": {"type": "object", "properties": {}},
        },
    )

    response = await api_client.get(f"/api/v1/tools/{tool.id}/example")

    assert response.status_code == 422
