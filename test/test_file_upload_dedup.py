"""文件上传去重回归测试。"""

from __future__ import annotations

import hashlib
import sys
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


@pytest.mark.asyncio
async def test_convert_uploaded_sdf_to_pdb_creates_pdb_file(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
):
    """上传 SDF 转 PDB 应生成可直接绑定工具输入的 PDB 文件记录。"""
    sdf_content = b"""
  demo
  platform

  3  2  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.1000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  1  3  1  0
M  END
$$$$
"""

    response = await api_client.post(
        "/api/v1/files/convert/sdf-to-pdb",
        headers={"Authorization": "Bearer admin-token"},
        files={"file": ("ligand.sdf", sdf_content, "chemical/x-mdl-sdfile")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["filename"] == "ligand.pdb"
    assert body["data"]["content_type"] == "chemical/x-pdb"

    result = await db_session.execute(
        select(FileModel).where(FileModel.id == body["data"]["id"])
    )
    converted_file = result.scalar_one()

    assert converted_file.owner_id == admin_user.id
    assert converted_file.source_type == FileSourceType.UPLOAD.value
    assert converted_file.file_meta["converted_from"] == "ligand.sdf"
    assert converted_file.file_meta["converter"] in {"rdkit", "openbabel"}
    pdb_text = Path(converted_file.storage_path).read_text(encoding="utf-8")
    assert "HETATM" in pdb_text
    assert pdb_text.rstrip().endswith("END")


@pytest.mark.asyncio
async def test_convert_uploaded_sdf_with_blank_title_line(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """RDKit 生成的 SDF 可能第一行标题为空，转换时必须保留三行 header。"""
    sdf_content = b"""
     RDKit          3D

  3  2  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.1000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  1  3  1  0
M  END
$$$$
"""

    response = await api_client.post(
        "/api/v1/files/convert/sdf-to-pdb",
        headers={"Authorization": "Bearer admin-token"},
        files={"file": ("rdkit.sdf", sdf_content, "chemical/x-mdl-sdfile")},
    )

    assert response.status_code == 200
    body = response.json()
    result = await db_session.execute(
        select(FileModel).where(FileModel.id == body["data"]["id"])
    )
    converted_file = result.scalar_one()
    pdb_text = Path(converted_file.storage_path).read_text(encoding="utf-8")

    assert "HETATM" in pdb_text
    assert converted_file.file_meta["converter"] in {"rdkit", "openbabel"}
