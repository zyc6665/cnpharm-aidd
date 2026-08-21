"""我的产物接口测试。"""

from __future__ import annotations

import hashlib
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
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import artifacts as _artifact_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.files import File as FileModel, FileSourceType
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.tasks import Task, TaskOutput, TaskStatus
from app.models.tools import Tool, ToolCategory, ToolStatus, ToolVersion
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
async def current_user(db_session: AsyncSession) -> User:
    """创建当前登录用户。"""
    user = User(
        email="owner@example.com",
        password_hash="hashed-password",
        display_name="Owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    """创建其他用户。"""
    user = User(
        email="other@example.com",
        password_hash="hashed-password",
        display_name="Other",
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
    current_user: User,
    other_user: User,
):
    """创建带依赖覆盖的 API 客户端。"""

    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == "Bearer owner-token":
            return current_user
        if authorization == "Bearer other-token":
            return other_user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def tool_category(db_session: AsyncSession) -> ToolCategory:
    """创建工具分类。"""
    category = ToolCategory(
        name="Docking",
        slug="docking",
        sort_order=0,
        is_enabled=True,
    )
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


async def create_tool_with_version(
    db_session: AsyncSession,
    owner: User,
    tool_category: ToolCategory,
    *,
    name: str,
    slug: str,
) -> tuple[Tool, ToolVersion]:
    """创建带版本的工具。"""
    tool = Tool(
        owner_id=owner.id,
        name=name,
        slug=slug,
        description=f"{name} description",
        category_id=tool_category.id,
        category=tool_category.name,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"input_schema": {}, "output_schema": {}},
        is_active=True,
        deprecated=False,
    )
    db_session.add(version)
    await db_session.flush()

    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    await db_session.refresh(version)
    return tool, version


async def create_file_record(
    db_session: AsyncSession,
    owner: User,
    *,
    filename: str,
    source_type: FileSourceType,
) -> FileModel:
    """创建文件记录。"""
    file_record = FileModel(
        owner_id=owner.id,
        filename=filename,
        content_type="application/octet-stream",
        size_bytes=128,
        sha256=hashlib.sha256(filename.encode("utf-8")).hexdigest(),
        source_type=source_type.value,
        storage_path=f"/tmp/{filename}",
        is_public=False,
    )
    db_session.add(file_record)
    await db_session.commit()
    await db_session.refresh(file_record)
    return file_record


async def create_task_with_output(
    db_session: AsyncSession,
    user: User,
    tool: Tool,
    version: ToolVersion,
    *,
    output_file_ids: list[str],
    task_name: str | None = None,
) -> Task:
    """创建带输出文件的任务。"""
    task = Task(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        status=TaskStatus.SUCCESS.value,
        name=task_name,
    )
    db_session.add(task)
    await db_session.flush()

    task_output = TaskOutput(
        task_id=task.id,
        result={"ok": True},
        file_ids=output_file_ids,
        output_type="file",
    )
    db_session.add(task_output)
    await db_session.commit()
    await db_session.refresh(task)
    return task


@pytest.mark.asyncio
async def test_artifacts_api_only_returns_current_users_tool_output_files(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    current_user: User,
    tool_category: ToolCategory,
):
    """接口只返回当前用户自己的工具输出文件。"""
    tool, version = await create_tool_with_version(
        db_session,
        current_user,
        tool_category,
        name="Artifact Tool",
        slug="artifact-tool",
    )
    artifact_file = await create_file_record(
        db_session,
        current_user,
        filename="artifact-output.sdf",
        source_type=FileSourceType.TOOL_OUTPUT,
    )
    await create_task_with_output(
        db_session,
        current_user,
        tool,
        version,
        output_file_ids=[artifact_file.id],
    )

    response = await api_client.get(
        "/api/v1/files/artifacts",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["total"] == 1
    assert [item["filename"] for item in payload["data"]["items"]] == ["artifact-output.sdf"]


@pytest.mark.asyncio
async def test_artifacts_api_excludes_other_users_outputs_and_upload_files(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    current_user: User,
    other_user: User,
    tool_category: ToolCategory,
):
    """接口不返回他人输出文件，也不返回普通上传文件。"""
    owner_tool, owner_version = await create_tool_with_version(
        db_session,
        current_user,
        tool_category,
        name="Owner Tool",
        slug="owner-tool",
    )
    other_tool, other_version = await create_tool_with_version(
        db_session,
        other_user,
        tool_category,
        name="Other Tool",
        slug="other-tool",
    )

    visible_artifact = await create_file_record(
        db_session,
        current_user,
        filename="visible-output.pdb",
        source_type=FileSourceType.TOOL_OUTPUT,
    )
    upload_file = await create_file_record(
        db_session,
        current_user,
        filename="uploaded-input.pdb",
        source_type=FileSourceType.UPLOAD,
    )
    other_artifact = await create_file_record(
        db_session,
        other_user,
        filename="other-output.pdb",
        source_type=FileSourceType.TOOL_OUTPUT,
    )

    await create_task_with_output(
        db_session,
        current_user,
        owner_tool,
        owner_version,
        output_file_ids=[visible_artifact.id, upload_file.id],
    )
    await create_task_with_output(
        db_session,
        other_user,
        other_tool,
        other_version,
        output_file_ids=[other_artifact.id],
    )

    response = await api_client.get(
        "/api/v1/files/artifacts",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["filename"] for item in payload["data"]["items"]] == ["visible-output.pdb"]


@pytest.mark.asyncio
async def test_artifacts_api_returns_task_and_tool_summary_fields(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    current_user: User,
    tool_category: ToolCategory,
):
    """接口返回任务和工具摘要字段。"""
    tool, version = await create_tool_with_version(
        db_session,
        current_user,
        tool_category,
        name="Pocket Generator",
        slug="pocket-generator",
    )
    artifact_file = await create_file_record(
        db_session,
        current_user,
        filename="pocket-output.zip",
        source_type=FileSourceType.TOOL_OUTPUT,
    )
    task = await create_task_with_output(
        db_session,
        current_user,
        tool,
        version,
        output_file_ids=[artifact_file.id],
    )

    response = await api_client.get(
        "/api/v1/files/artifacts",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["task_id"] == task.id
    assert item["task_name"] is None
    assert item["tool_id"] == tool.id
    assert item["tool_name"] == "Pocket Generator"
    assert item["tool_slug"] == "pocket-generator"
    assert item["download_url"] == f"/api/v1/files/{artifact_file.id}/download"


@pytest.mark.asyncio
async def test_artifacts_api_returns_standard_artifact_version_metadata(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    current_user: User,
    tool_category: ToolCategory,
):
    """标准产物文件应带回 ArtifactVersion 和 role，供工作流独立运行提交 input_bindings。"""
    tool, version = await create_tool_with_version(
        db_session,
        current_user,
        tool_category,
        name="Protein Prep",
        slug="protein-prep",
    )
    prepared_file = await create_file_record(
        db_session,
        current_user,
        filename="prepared.pdb",
        source_type=FileSourceType.TOOL_OUTPUT,
    )
    task = await create_task_with_output(
        db_session,
        current_user,
        tool,
        version,
        output_file_ids=[prepared_file.id],
    )
    artifact = Artifact(
        project_id="project-1",
        created_by=current_user.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        standard_type="protein_structure",
        standard_version=1,
        name="prepared protein",
        source_task_id=task.id,
    )
    db_session.add(artifact)
    await db_session.flush()
    artifact_version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=current_user.id,
        version=1,
        filename="prepared.pdb",
        content_type="chemical/x-pdb",
        size_bytes=prepared_file.size_bytes,
        sha256=prepared_file.sha256,
        storage_key=prepared_file.storage_path,
        status="available",
        validation_status="passed",
        validation_errors=[],
        manifest_json={"type": "protein_structure@1"},
        summary_json={},
        metrics_json={},
    )
    db_session.add(artifact_version)
    await db_session.flush()
    db_session.add(
        ArtifactVersionFile(
            artifact_version_id=artifact_version.id,
            role="prepared_pdb",
            file_id=prepared_file.id,
            is_primary=True,
            sort_order=0,
        )
    )
    artifact.latest_version_id = artifact_version.id
    await db_session.commit()

    response = await api_client.get(
        "/api/v1/files/artifacts",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["artifact_id"] == artifact.id
    assert item["artifact_version_id"] == artifact_version.id
    assert item["standard_artifact_role"] == "prepared_pdb"
    assert item["semantic_type"] == "protein_structure@1"


@pytest.mark.asyncio
async def test_artifacts_api_returns_task_name_when_available(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    current_user: User,
    tool_category: ToolCategory,
):
    """接口应返回任务名称，供工作台优先展示任务名。"""
    tool, version = await create_tool_with_version(
        db_session,
        current_user,
        tool_category,
        name="Lead Finder",
        slug="lead-finder",
    )
    artifact_file = await create_file_record(
        db_session,
        current_user,
        filename="lead-output.sdf",
        source_type=FileSourceType.TOOL_OUTPUT,
    )
    await create_task_with_output(
        db_session,
        current_user,
        tool,
        version,
        output_file_ids=[artifact_file.id],
        task_name="先导化合物筛选批次 A",
    )

    response = await api_client.get(
        "/api/v1/files/artifacts",
        headers={"Authorization": "Bearer owner-token"},
    )

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["task_name"] == "先导化合物筛选批次 A"
