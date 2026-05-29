"""文件上传去重回归测试。"""

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

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.files import File as FileModel, FileSourceType
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


@pytest.mark.asyncio
async def test_upload_file_returns_existing_record_when_duplicate_rows_exist(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
):
    """去重查询命中多条历史记录时，上传接口仍应返回已存在文件而不是 500。"""
    content = b"duplicate receptor pdb content"
    sha256 = hashlib.sha256(content).hexdigest()

    older_file = FileModel(
        owner_id=admin_user.id,
        filename="receptor-old.pdb",
        content_type="chemical/x-pdb",
        size_bytes=len(content),
        sha256=sha256,
        source_type=FileSourceType.UPLOAD,
        storage_path="/tmp/receptor-old.pdb",
    )
    tool_output_file = FileModel(
        owner_id=admin_user.id,
        filename="artifacts__receptor-copy.pdb",
        content_type="chemical/x-pdb",
        size_bytes=len(content),
        sha256=sha256,
        source_type=FileSourceType.TOOL_OUTPUT,
        storage_path="/tmp/artifacts__receptor-copy.pdb",
    )
    newer_file = FileModel(
        owner_id=admin_user.id,
        filename="receptor-new.pdb",
        content_type="chemical/x-pdb",
        size_bytes=len(content),
        sha256=sha256,
        source_type=FileSourceType.UPLOAD,
        storage_path="/tmp/receptor-new.pdb",
    )
    db_session.add_all([older_file, tool_output_file, newer_file])
    await db_session.commit()
    await db_session.refresh(older_file)
    await db_session.refresh(tool_output_file)
    await db_session.refresh(newer_file)

    response = await api_client.post(
        "/api/v1/files/upload",
        headers={"Authorization": "Bearer admin-token"},
        files={"file": ("receptor.pdb", content, "chemical/x-pdb")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "文件已存在（去重）"
    assert body["data"]["id"] == newer_file.id
    assert body["data"]["filename"] == "receptor-new.pdb"
    assert body["data"]["sha256"] == sha256
