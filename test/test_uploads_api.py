"""分片上传会话 API tests (docs/05 §4.2, docs/04 §5.8).

覆盖一次完整上传的四段生命周期：创建（幂等）→ 逐片上报（可乱序、可重传）→
合并（缺片 422、字节数不符 422、超限 422、成功后落 files 表）→ 取消（409 后不可续传）。
关键回归点有两处：

1. 分片索引落在 ``upload_parts`` 行级表（``session_id`` + ``part_number`` 复合主键），
   不再复用 ``upload_sessions.parts`` 这个 JSON 列——JSON 列只能整列读写，并发上报
   时后提交者会覆盖前者，**字节没丢但索引丢了**，断点续传直接失效；
2. 会话过期要在三个业务入口都检查（创建后用户关掉页面就再没有入口碰到它），
   并由 ``upload_maintenance`` 的定时任务兜底。
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
# 4) 乱序上报互不覆盖（分片索引按片号成行，不靠整列覆盖）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_parts_keep_every_reported_part(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """先传第 3 片再传第 1 片：两片都在，互不覆盖。"""

    data = await _create_upload(
        api_client, project.id, size=3 * PART_SIZE, idempotency_key="k4"
    )
    upload_id = data["uploadId"]

    assert (await _put_part(api_client, upload_id, 3, b"third-part")).status_code == 200
    assert (await _put_part(api_client, upload_id, 1, b"first-part")).status_code == 200

    detail = await api_client.get(f"/api/v1/uploads/{upload_id}", headers=_headers(OWNER))
    assert detail.status_code == 200, detail.text
    payload = detail.json()["data"]

    assert sorted(item["partNumber"] for item in payload["parts"]) == [1, 3]
    assert payload["receivedPartNumbers"] == [1, 3]
    assert payload["missingPartNumbers"] == [2]
    assert payload["state"] == "UPLOADING"


@pytest.mark.asyncio
async def test_stale_session_cannot_drop_another_part(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """用「过期的内存视图」写第 2 片，不会冲掉别人已写的第 1 片（B1 回归）。

    这正是 JSON 列版本的失败形态：旧实现读 ``session.parts`` 拿整列再写回，
    一个在写第 1 片之前就已经加载过的会话对象，``parts`` 仍是空列表，它写第 2
    片时会把第 1 片覆盖掉。改成 ``upload_parts`` 行级记录后，两个片号是两行，
    互相看不见也就互相覆盖不了。
    """

    from sqlalchemy.ext.asyncio import async_sessionmaker

    data = await _create_upload(
        api_client, project.id, size=3 * PART_SIZE, idempotency_key="k4b"
    )
    upload_id = data["uploadId"]

    # 先在一个「旧」会话里把对象加载出来（此时还没有任何分片）。
    # 注意用 ``db_session.bind``（AsyncEngine）而不是 ``get_bind()``，后者返回的
    # 同步 Engine 不能喂给 ``async_sessionmaker``。
    stale_factory = async_sessionmaker(
        db_session.bind, expire_on_commit=False, autoflush=False
    )
    async with stale_factory() as stale:
        stale_session = await uploads_service.get_upload_session(
            stale, upload_id=upload_id
        )
        assert stale_session.part_records == []

        # 期间另一个请求写入了第 3 片并提交。
        assert (
            await _put_part(api_client, upload_id, 3, b"third-part")
        ).status_code == 200

        # 旧会话再写第 1 片：若实现是整列覆盖，第 3 片会消失。
        await uploads_service.record_upload_part(
            stale, session=stale_session, part_number=1, content=b"first-part"
        )

    detail = await api_client.get(f"/api/v1/uploads/{upload_id}", headers=_headers(OWNER))
    payload = detail.json()["data"]
    assert payload["receivedPartNumbers"] == [1, 3]
    assert payload["missingPartNumbers"] == [2]


@pytest.mark.asyncio
async def test_part_write_compiles_to_upsert(db_session: AsyncSession) -> None:
    """分片写入必须编译成 ``ON CONFLICT ... DO UPDATE``，而不是读整列再写回。"""

    from sqlalchemy.dialects import sqlite

    from app.services.uploads import _upsert_part_statement

    statement = _upsert_part_statement(
        db_session, session_id="session-1", part_number=2, etag="e" * 32, size=1024
    )
    assert statement is not None
    compiled = str(statement.compile(dialect=sqlite.dialect())).upper()
    assert "ON CONFLICT" in compiled
    assert "DO UPDATE" in compiled


@pytest.mark.asyncio
async def test_create_recovers_from_idempotency_race(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, monkeypatch
) -> None:
    """并发下「先查后插」都会看到空结果，插入失败方必须回滚重查并复用（B2 回归）。

    这里让第一次 ``find_idempotent_session`` 假装没查到（模拟两个请求同时进入），
    于是服务层会撞上 ``uq_upload_sessions_project_idem``；捕获 ``IntegrityError``
    后重查，应返回对方已落库的会话而不是抛出 500。
    """

    first = await _create_upload(api_client, project.id, idempotency_key="race-key")

    original = uploads_service.find_idempotent_session
    calls = {"count": 0}

    async def pretend_missed(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return await original(*args, **kwargs)

    monkeypatch.setattr(uploads_service, "find_idempotent_session", pretend_missed)

    second = await _create_upload(api_client, project.id, idempotency_key="race-key")

    assert calls["count"] >= 2, "应进入「插入失败 → 重查」分支"
    assert second["uploadId"] == first["uploadId"]
    assert second["objectKey"] == first["objectKey"]



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
    """合并后返回 urn/size/sha256，``files`` 表多一行且 sha256 与实际内容一致。

    ``size`` 必须与实际上报的字节数一致：合并阶段会校验总字节数是否等于创建时
    声明的 ``declared_size``，不一致就 422——这条校验挡的是「客户端少传一片但
    片号都在」的场景。
    """

    before = await db_session.scalar(select(func.count(FileModel.id)))

    payload_bytes = b"HEAD" + b"-payload"
    data = await _create_upload(
        api_client, project.id, size=len(payload_bytes), idempotency_key="k7"
    )
    upload_id = data["uploadId"]
    await _put_part(api_client, upload_id, 1, payload_bytes)

    response = await api_client.post(
        f"/api/v1/uploads/{upload_id}:complete",
        headers=_headers(OWNER),
        json={"parts": [{"partNumber": 1, "etag": "ignored"}]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]

    assert payload["urn"].startswith("file:")
    assert payload["size"] == len(payload_bytes)
    assert (
        payload["sha256"]
        == __import__("hashlib").sha256(payload_bytes).hexdigest()
    )
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
# 10) 超过服务端合并上限
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_over_assembly_limit_is_rejected(
    api_client: httpx.AsyncClient, project: Project, monkeypatch
) -> None:
    """累计字节 > UPLOAD_MAX_ASSEMBLY_BYTES → 422，message 指向合并上限配置项。"""

    # 把小文件真正写满 2GB 会让用例跑几十秒并吃掉同等磁盘；这里把上限压到
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
    assert "UPLOAD_MAX_ASSEMBLY_BYTES" in response.json()["message"]


# ---------------------------------------------------------------------------
# 11) 合并字节数与声明不符
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_rejects_size_mismatch(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """纯客户端侧无法伪造：声明的 size 与实收字节不符 → 422。

    ``declared_size`` 是创建会话时由客户端声明的，服务端在合并时校验实际字节数，
    避免「片号齐了但内容被截断」的静默成功。
    """

    data = await _create_upload(api_client, project.id, size=100, idempotency_key="k11")
    upload_id = data["uploadId"]
    await _put_part(api_client, upload_id, 1, b"short")

    response = await api_client.post(
        f"/api/v1/uploads/{upload_id}:complete",
        headers=_headers(OWNER),
        json={"parts": [{"partNumber": 1, "etag": "e"}]},
    )
    assert response.status_code == 422, response.text
    assert "不一致" in response.json()["message"]


# ---------------------------------------------------------------------------
# 12) 声明了 sha256 时合并后校验
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_verifies_declared_sha256(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """客户端声明了 sha256 且与实际不符 → 422（docs/05 §4.2 的 42205 口径）。"""

    import hashlib

    content = b"declared-digest-check"
    response = await api_client.post(
        "/api/v1/uploads",
        headers=_headers(OWNER, idempotency_key="k12"),
        json={
            "projectId": project.id,
            "filename": "digest.sdf",
            "size": len(content),
            "sha256": hashlib.sha256(b"other-content").hexdigest(),
        },
    )
    assert response.status_code == 200, response.text
    upload_id = response.json()["data"]["uploadId"]
    await _put_part(api_client, upload_id, 1, content)

    completed = await api_client.post(
        f"/api/v1/uploads/{upload_id}:complete",
        headers=_headers(OWNER),
        json={"parts": [{"partNumber": 1, "etag": "e"}]},
    )
    assert completed.status_code == 422, completed.text
    assert "sha256" in completed.json()["message"]


# ---------------------------------------------------------------------------
# 13) 过期会话不可再传
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_session_rejects_new_parts(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """``expires_at`` 已过 → PUT 409 且会话被置为 EXPIRED（PR2 评审 B4 的回归用例）。"""

    from datetime import timedelta

    from app.common.time import utcnow
    from app.models.uploads import UploadSession

    data = await _create_upload(api_client, project.id, size=32, idempotency_key="k13")
    upload_id = data["uploadId"]

    session = await db_session.scalar(
        select(UploadSession).where(UploadSession.id == upload_id)
    )
    assert session is not None
    session.expires_at = utcnow() - timedelta(minutes=1)
    await db_session.commit()

    response = await _put_part(api_client, upload_id, 1, b"late")
    assert response.status_code == 409, response.text
    assert "过期" in response.json()["message"]

    await db_session.refresh(session)
    assert session.state == "EXPIRED"


# ---------------------------------------------------------------------------
# 14) 定时清理过期会话
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expire_stale_upload_sessions_sweeps_only_expired(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """清理任务只碰已过期的活跃会话，且返回处理条数。"""

    from datetime import timedelta

    from app.common.time import utcnow
    from app.models.uploads import UploadSession
    from app.services.upload_maintenance import expire_stale_upload_sessions

    stale = await _create_upload(api_client, project.id, size=8, idempotency_key="k14a")
    fresh = await _create_upload(api_client, project.id, size=8, idempotency_key="k14b")

    stale_row = await db_session.scalar(
        select(UploadSession).where(UploadSession.id == stale["uploadId"])
    )
    assert stale_row is not None
    stale_row.expires_at = utcnow() - timedelta(hours=1)
    await db_session.commit()

    swept = await expire_stale_upload_sessions(db_session)
    assert swept == 1

    stale_row = await db_session.scalar(
        select(UploadSession).where(UploadSession.id == stale["uploadId"])
    )
    fresh_row = await db_session.scalar(
        select(UploadSession).where(UploadSession.id == fresh["uploadId"])
    )
    assert stale_row is not None and stale_row.state == "EXPIRED"
    assert fresh_row is not None and fresh_row.state == "INITIATED"
