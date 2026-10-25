"""分片上传会话 API tests (docs/05 §4.2, docs/04 §5.8).

覆盖一次完整上传的四段生命周期：创建（幂等）→ 逐片上报（可乱序、可重传）→
合并（缺片 422、超限 422、成功后落 files 表）→ 取消（409 后不可续传）。
关键回归点：``parts`` 是 JSON 列，若实现里原地 ``append`` 而没整列重新赋值，
用例 4 会立刻变红——这正是本文件存在的理由。
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import get_current_user  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.files import File as FileModel  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services import uploads as uploads_service  # noqa: E402

OWNER = "owner"
VIEWER = "viewer"
OUTSIDER = "outsider"

PART_SIZE = 16 * 1024 * 1024


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session
    await engine.dispose()


async def _create_user(db: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        display_name=email.split("@")[0],
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def users(db_session: AsyncSession) -> dict[str, User]:
    return {
        OWNER: await _create_user(db_session, "owner@example.com"),
        VIEWER: await _create_user(db_session, "viewer@example.com"),
        OUTSIDER: await _create_user(db_session, "outsider@example.com"),
    }


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    organization = Organization(name="Upload Lab", slug="upload-lab")
    db_session.add(organization)
    await db_session.flush()
    record = Project(
        organization_id=organization.id,
        created_by=users[OWNER].id,
        name="Upload program",
        status="active",
    )
    db_session.add(record)
    await db_session.flush()
    db_session.add(
        ProjectMember(project_id=record.id, user_id=users[OWNER].id, role="owner")
    )
    db_session.add(
        ProjectMember(project_id=record.id, user_id=users[VIEWER].id, role="viewer")
    )
    await db_session.commit()
    await db_session.refresh(record)
    return record


@pytest_asyncio.fixture
async def storage_root(tmp_path, monkeypatch) -> Path:
    """把分片目录与文件落库目录都指到 tmp_path，避免污染开发者 storage/。"""
    root = tmp_path / "storage"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.files.storage_path.STORAGE_PATH", root)
    monkeypatch.setattr(uploads_service.settings, "STORAGE_PATH", str(root))
    return root


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, users: dict[str, User], storage_root):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in users:
            return users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
    app.dependency_overrides.clear()


def _headers(user: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {user}"}
    if idempotency_key is not None:
        headers["X-Idempotency-Key"] = idempotency_key
    return headers


async def _create_upload(
    client: httpx.AsyncClient,
    project_id: str,
    *,
    size: int = 40,
    filename: str = "compound_lib.sdf",
    idempotency_key: str = "idem-create-1",
) -> dict:
    response = await client.post(
        "/api/v1/uploads",
        headers=_headers(OWNER, idempotency_key=idempotency_key),
        json={
            "projectId": project_id,
            "filename": filename,
            "size": size,
            "contentType": "chemical/x-mdl-sdfile",
            "sha256": None,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _put_part(client: httpx.AsyncClient, upload_id: str, number: int, content: bytes):
    return await client.put(
        f"/api/v1/uploads/{upload_id}/parts/{number}",
        headers={**_headers(OWNER), "Content-Type": "application/octet-stream"},
        content=content,
    )


# ---------------------------------------------------------------------------
# 1) 创建会话的响应契约
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_upload_session_returns_part_plan(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """创建返回 uploadId / objectKey / partSize=16MB / partCount=ceil(size/partSize)。"""

    size = 33 * 1024 * 1024
    data = await _create_upload(api_client, project.id, size=size, idempotency_key="k1")

    assert data["uploadId"]
    assert data["objectKey"].startswith(f"{project.id}/upload/")
    assert data["partSize"] == PART_SIZE
    assert data["partCount"] == 3  # ceil(33MB / 16MB)
    assert data["state"] == "INITIATED"
    assert data["missingPartNumbers"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 2) 幂等键是必填头
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_upload_requires_idempotency_header(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """缺 X-Idempotency-Key → 422（头声明为 Header(...)，不可省略）。"""

    response = await api_client.post(
        "/api/v1/uploads",
        headers=_headers(OWNER),
        json={"projectId": project.id, "filename": "a.sdf", "size": 10},
    )
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# 3) 同一幂等键只产生一个会话
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_upload_is_idempotent(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """同 project + 同幂等键二次创建返回同一 uploadId（不新建会话）。"""

    first = await _create_upload(api_client, project.id, idempotency_key="same-key")
    second = await _create_upload(api_client, project.id, idempotency_key="same-key")

    assert first["uploadId"] == second["uploadId"]
    assert first["objectKey"] == second["objectKey"]


# ---------------------------------------------------------------------------
# 4) parts 追加而非覆盖
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_parts_append_in_report_order(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """先传第 3 片再传第 1 片：两片都在，且按上报顺序追加，互不覆盖。"""

    data = await _create_upload(
        api_client, project.id, size=3 * PART_SIZE, idempotency_key="k4"
    )
    upload_id = data["uploadId"]

    assert (await _put_part(api_client, upload_id, 3, b"third-part")).status_code == 200
    assert (await _put_part(api_client, upload_id, 1, b"first-part")).status_code == 200

    detail = await api_client.get(f"/api/v1/uploads/{upload_id}", headers=_headers(OWNER))
    assert detail.status_code == 200, detail.text
    payload = detail.json()["data"]

    assert [item["partNumber"] for item in payload["parts"]] == [3, 1]
    assert payload["receivedPartNumbers"] == [1, 3]
    assert payload["state"] == "UPLOADING"


# ---------------------------------------------------------------------------
# 5) 片号越界
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_part_out_of_range_is_rejected(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """上报超出 partCount 的片号 → 422。"""

    data = await _create_upload(api_client, project.id, size=32, idempotency_key="k5")
    upload_id = data["uploadId"]
    assert data["partCount"] == 1

    response = await _put_part(api_client, upload_id, 2, b"overflow")
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# 6) 缺片不可合并
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_with_missing_part_is_rejected(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """complete 少传一片 → 422 且 message 含「缺少分片」。"""

    data = await _create_upload(
        api_client, project.id, size=2 * PART_SIZE, idempotency_key="k6"
    )
    upload_id = data["uploadId"]
    await _put_part(api_client, upload_id, 1, b"only-first")

    response = await api_client.post(
        f"/api/v1/uploads/{upload_id}:complete",
        headers=_headers(OWNER),
        json={"parts": [{"partNumber": 1, "etag": "x"}]},
    )
    assert response.status_code == 422, response.text
    assert "缺少分片" in response.json()["message"]


# ---------------------------------------------------------------------------
# 7) 合并成功并落 files 表
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_upload_stores_file(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """合并后返回 urn/size/sha256，``files`` 表多一行且 sha256 与实际内容一致。"""

    before = await db_session.scalar(select(func.count(FileModel.id)))

    data = await _create_upload(api_client, project.id, size=20, idempotency_key="k7")
    upload_id = data["uploadId"]
    await _put_part(api_client, upload_id, 1, b"HEAD" + b"-payload")

    response = await api_client.post(
        f"/api/v1/uploads/{upload_id}:complete",
        headers=_headers(OWNER),
        json={"parts": [{"partNumber": 1, "etag": "ignored"}]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]

    assert payload["urn"].startswith("file:")
    assert payload["size"] == len(b"HEAD-payload")
    assert payload["sha256"] == __import__("hashlib").sha256(b"HEAD-payload").hexdigest()
    assert payload["state"] == "COMPLETED"

    after = await db_session.scalar(select(func.count(FileModel.id)))
    assert after == before + 1


# ---------------------------------------------------------------------------
# 8) 已完成会话不可再写分片
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_part_on_completed_session_conflicts(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """会话 COMPLETED 后再 PUT → 409。"""

    data = await _create_upload(api_client, project.id, size=6, idempotency_key="k8")
    upload_id = data["uploadId"]
    await _put_part(api_client, upload_id, 1, b"abcdef")

    complete = await api_client.post(
        f"/api/v1/uploads/{upload_id}:complete",
        headers=_headers(OWNER),
        json={"parts": [{"partNumber": 1, "etag": "e"}]},
    )
    assert complete.status_code == 200, complete.text

    response = await _put_part(api_client, upload_id, 1, b"again")
    assert response.status_code == 409, response.text


# ---------------------------------------------------------------------------
# 9) 取消会话
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_upload_aborts_session(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """DELETE 后 state=ABORTED，再 PUT → 409。"""

    data = await _create_upload(api_client, project.id, size=64, idempotency_key="k9")
    upload_id = data["uploadId"]
    await _put_part(api_client, upload_id, 1, b"chunk")

    deleted = await api_client.delete(
        f"/api/v1/uploads/{upload_id}", headers=_headers(OWNER)
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["state"] == "ABORTED"

    response = await _put_part(api_client, upload_id, 1, b"chunk-again")
    assert response.status_code == 409, response.text


# ---------------------------------------------------------------------------
# 10) 超过本地拼装上限
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_over_assembly_limit_points_to_minio(
    api_client: httpx.AsyncClient, project: Project, monkeypatch
) -> None:
    """累计字节 > UPLOAD_MAX_ASSEMBLY_BYTES → 422，message 指向后续 MinIO 直传。"""

    # 把小文件真正写满 256MB 会让用例跑几十秒并吃掉 256MB 内存；这里把上限压到
    # 4 字节，语义等价（比较的是累计字节数与常量），又不牺牲执行速度。
    monkeypatch.setattr(uploads_service, "UPLOAD_MAX_ASSEMBLY_BYTES", 4)

    data = await _create_upload(api_client, project.id, size=8, idempotency_key="k10")
    upload_id = data["uploadId"]
    await _put_part(api_client, upload_id, 1, b"12345678")

    response = await api_client.post(
        f"/api/v1/uploads/{upload_id}:complete",
        headers=_headers(OWNER),
        json={"parts": [{"partNumber": 1, "etag": "e"}]},
    )
    assert response.status_code == 422, response.text
    assert "MinIO" in response.json()["message"]
