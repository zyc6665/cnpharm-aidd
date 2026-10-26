"""请求级幂等（``X-Idempotency-Key``）的行为测试（docs/05 §12、docs/18 §6.3 G-10）。

覆盖面
------
1. **同键同体**：第二次请求返回首响快照，且**不产生第二个任务**（这正是幂等存在
   的全部意义）；
2. **同键异体**：409 + ``code=40905``，绝不能把 A 的 ``taskId`` 交给 B；
3. **同键且首次仍在处理中**：409 + ``code=40904`` + ``Retry-After: 2``；
4. **没带头**：完全透传，连两次都正常创建（幂等是增强而不是前置条件，不能在
   190+ 个存量端点上强制要求这个头）；
5. **失败可重试**：首次 5xx 之后同一个键必须还能用（``release_request``）；
6. **过期可复用**：``expires_at`` 到点后同一个键视为新请求；
7. **作用域隔离**：不同用户用同一个键互不影响（scope 里带 user_id）。

测试用的隔离方式与 ``test/test_task_naming.py`` 一致：内存 SQLite + 覆盖
``get_db`` / ``get_current_user``，并把 ``direct_task_runner`` 换成不落地的桩，
避免真的去跑任务。
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1 import tasks as tasks_api  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.common.time import utcnow  # noqa: E402
from app.config import settings as config_settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.idempotency import IdempotencyKey  # noqa: E402
from app.models.tasks import Task  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services.idempotency import (  # noqa: E402
    OUTCOME_CONFLICT_BODY,
    OUTCOME_IN_FLIGHT,
    OUTCOME_REPLAY,
    begin_request,
    build_scope,
    hash_request,
    purge_expired_idempotency_keys,
)

ALICE_TOKEN = "alice-token"
BOB_TOKEN = "bob-token"
TASKS_TEMPLATE = "/api/v1/tasks"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
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
async def alice(db_session: AsyncSession) -> User:
    return await _create_user(db_session, "alice@example.com")


@pytest_asyncio.fixture
async def bob(db_session: AsyncSession) -> User:
    return await _create_user(db_session, "bob@example.com")


@pytest_asyncio.fixture
async def published_tool(db_session: AsyncSession, alice: User) -> Tool:
    tool = Tool(
        owner_id=alice.id,
        name="Molecular Docking",
        slug="molecular-docking",
        description="Tool for idempotency tests",
        category="generation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id, version="1.0.0", config={"type": "python_script"}, is_active=True
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest.fixture
def direct_runner_stub(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """把任务创建固定为 direct 模式并屏蔽真实调度。"""
    runner = SimpleNamespace(
        scheduled=[],
        cancelled=[],
        schedule_task=lambda task_id, tool_version_id: runner.scheduled.append(
            (task_id, tool_version_id)
        ),
        cancel_task=lambda task_id: runner.cancelled.append(task_id) or True,
    )
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)
    return runner


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession, alice: User, bob: User, direct_runner_stub: SimpleNamespace
):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token == ALICE_TOKEN:
            return alice
        if token == BOB_TOKEN:
            return bob
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    # ``raise_app_exceptions=False``：Starlette 的 ``ServerErrorMiddleware`` 在生成
    # 500 响应后仍会把异常重新抛出，默认配置下 httpx 会直接抛给测试，看不到响应。
    # 本文件要断言「首次失败后同一个键还能重试」，必须拿到那个 500 响应。
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


def _headers(token: str = ALICE_TOKEN, *, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["X-Idempotency-Key"] = key
    return headers


def _task_payload(tool_id: str, *, name: str = "Idem Task") -> dict:
    return {"tool_id": tool_id, "name": name, "params": {"foo": "bar"}, "priority": "normal"}


async def _post_task(
    client: httpx.AsyncClient,
    tool_id: str,
    *,
    key: str | None = None,
    token: str = ALICE_TOKEN,
    name: str = "Idem Task",
):
    return await client.post(
        "/api/v1/tasks",
        headers=_headers(token, key=key),
        json=_task_payload(tool_id, name=name),
    )


async def _task_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(Task))
    return int(result.scalar_one())


# ---------------------------------------------------------------------------
# 1) 同键同体 → 重放首响快照
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_key_same_body_replays_first_task_id(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
) -> None:
    """同键同体重放应返回同一个 ``taskId``，且库里只有一个任务。"""

    first = await _post_task(api_client, published_tool.id, key="idem-1")
    assert first.status_code == 200, first.text
    first_id = first.json()["data"]["id"]

    second = await _post_task(api_client, published_tool.id, key="idem-1")
    assert second.status_code == 200, second.text
    assert second.json()["data"]["id"] == first_id
    assert await _task_count(db_session) == 1


@pytest.mark.asyncio
async def test_replay_returns_identical_envelope(
    api_client: httpx.AsyncClient,
    published_tool: Tool,
) -> None:
    """重放返回的是**首响快照**，逐字节等于第一次的响应体。"""

    first = await _post_task(api_client, published_tool.id, key="idem-snapshot")
    second = await _post_task(api_client, published_tool.id, key="idem-snapshot")

    assert second.status_code == first.status_code
    assert second.json() == first.json()


@pytest.mark.asyncio
async def test_replay_persists_response_snapshot_and_resource_id(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
) -> None:
    """落库的行应是 ``COMPLETED``，带首响状态码、快照与 resource_id（便于排查）。"""

    response = await _post_task(api_client, published_tool.id, key="idem-row")
    task_id = response.json()["data"]["id"]

    record = (
        await db_session.execute(
            select(IdempotencyKey).where(IdempotencyKey.key == "idem-row")
        )
    ).scalar_one()
    assert record.state == "COMPLETED"
    assert record.response_status == 200
    assert record.response_body["data"]["id"] == task_id
    assert record.resource_type == "task"
    assert record.resource_id == task_id
    assert record.expires_at > utcnow()


# ---------------------------------------------------------------------------
# 2) 同键异体 → 409 / 40905
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_key_different_body_conflicts_40905(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
) -> None:
    """同键换一个请求体必须 40905，并且不能把首次的 taskId 交出去。"""

    first = await _post_task(api_client, published_tool.id, key="idem-2", name="First")
    assert first.status_code == 200, first.text
    first_id = first.json()["data"]["id"]

    second = await _post_task(api_client, published_tool.id, key="idem-2", name="Second")
    assert second.status_code == 409, second.text
    payload = second.json()
    assert payload["code"] == 40905
    assert "幂等键复用但请求体不同" in payload["message"]
    assert payload["data"] is None
    # 关键：不能泄露首次结果，也不能创建第二个任务。
    assert first_id not in second.text
    assert await _task_count(db_session) == 1


# ---------------------------------------------------------------------------
# 3) 同键且首次仍在处理中 → 409 / 40904 + Retry-After
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_flight_returns_40904_with_retry_after(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    alice: User,
    published_tool: Tool,
) -> None:
    """键已被占且仍是 ``IN_PROGRESS`` → 40904 + ``Retry-After: 2``。"""

    scope = build_scope(user_id=alice.id, method="POST", path_template=TASKS_TEMPLATE)
    payload = _task_payload(published_tool.id)
    body = httpx.Request("POST", "http://testserver/api/v1/tasks", json=payload).content
    request_hash = hash_request(
        method="POST", path="/api/v1/tasks", query="", body=body
    )
    outcome = await begin_request(
        db_session,
        scope=scope,
        key="idem-3",
        request_hash=request_hash,
        user_id=alice.id,
    )
    assert outcome.status == "acquired"

    response = await _post_task(api_client, published_tool.id, key="idem-3")
    assert response.status_code == 409, response.text
    assert response.json()["code"] == 40904
    assert response.headers.get("Retry-After") == "2"
    # 处理中的键不会触发业务逻辑，因此一个任务都不该被创建。
    assert await _task_count(db_session) == 0


# ---------------------------------------------------------------------------
# 4) 没带 X-Idempotency-Key → 完全透传
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_without_header_creates_two_tasks(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
) -> None:
    """没有幂等头时是普通请求：两次都要真正创建任务，行为与改动前一致。"""

    first = await _post_task(api_client, published_tool.id)
    second = await _post_task(api_client, published_tool.id)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["id"] != second.json()["data"]["id"]
    assert await _task_count(db_session) == 2


@pytest.mark.asyncio
async def test_disabled_switch_ignores_header(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``IDEMPOTENCY_ENABLED=false`` 时即使带了头也当作没带。"""

    monkeypatch.setattr(config_settings, "IDEMPOTENCY_ENABLED", False, raising=False)

    first = await _post_task(api_client, published_tool.id, key="idem-off")
    second = await _post_task(api_client, published_tool.id, key="idem-off")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["id"] != second.json()["data"]["id"]
    assert await _task_count(db_session) == 2


@pytest.mark.asyncio
async def test_overlong_key_is_rejected(
    api_client: httpx.AsyncClient,
    published_tool: Tool,
) -> None:
    """超过列宽（128）的键无处可存，应在执行前就被拒绝（422）。"""

    response = await _post_task(api_client, published_tool.id, key="k" * 129)
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# 5) 首次失败 → 同一个键还能重试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_request_releases_key_for_retry(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次请求 500 之后，同一个键必须还能用——失败不能把键永久占住。"""

    # 先把 id 取成字符串：失败路径会 ``rollback``（丢弃路由中途写入的半成品），
    # rollback 会让会话里已加载的对象过期，之后再访问 ORM 属性会触发异步隐式加载。
    tool_id = published_tool.id
    calls = {"count": 0}
    real_create = tasks_api.create_and_schedule_tool_task

    async def _boom(**kwargs):
        calls["count"] += 1
        raise RuntimeError("调度器炸了")

    monkeypatch.setattr(tasks_api, "create_and_schedule_tool_task", _boom)

    failed = await _post_task(api_client, tool_id, key="idem-retry")
    assert failed.status_code == 500, failed.text
    assert calls["count"] == 1

    # 失败路径应把行删掉，否则这个键会被占满 24h。
    remaining = (
        await db_session.execute(
            select(func.count()).select_from(IdempotencyKey).where(
                IdempotencyKey.key == "idem-retry"
            )
        )
    ).scalar_one()
    assert remaining == 0

    monkeypatch.setattr(tasks_api, "create_and_schedule_tool_task", real_create)
    retried = await _post_task(api_client, tool_id, key="idem-retry")
    assert retried.status_code == 200, retried.text
    assert await _task_count(db_session) == 1


# ---------------------------------------------------------------------------
# 6) 过期 → 视为不存在
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_key_can_be_reused(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
) -> None:
    """``expires_at`` 已过的行不再拦请求：同一个键可以发新请求。"""

    first = await _post_task(api_client, published_tool.id, key="idem-expired")
    first_id = first.json()["data"]["id"]

    record = (
        await db_session.execute(
            select(IdempotencyKey).where(IdempotencyKey.key == "idem-expired")
        )
    ).scalar_one()
    record.expires_at = utcnow() - timedelta(hours=1)
    await db_session.commit()

    second = await _post_task(
        api_client, published_tool.id, key="idem-expired", name="After expiry"
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["id"] != first_id
    assert second.json()["data"]["name"] == "After expiry"
    assert await _task_count(db_session) == 2


# ---------------------------------------------------------------------------
# 7) 清理任务只删过期行
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_removes_only_expired_rows(
    db_session: AsyncSession,
) -> None:
    """``purge_expired_idempotency_keys`` 只删过期行，未过期的重放快照必须留下。"""

    now = utcnow()
    for index, delta_hours in enumerate((-2, -1, 1, 2)):
        db_session.add(
            IdempotencyKey(
                scope="u:POST:/api/v1/tasks",
                key=f"purge-{index}",
                request_hash="a" * 64,
                state="COMPLETED",
                response_status=200,
                response_body={"code": 200},
                user_id="u",
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(hours=delta_hours),
            )
        )
    await db_session.commit()

    deleted = await purge_expired_idempotency_keys(db_session, batch_size=50)
    assert deleted == 2

    remaining = (
        await db_session.execute(select(IdempotencyKey.key).order_by(IdempotencyKey.key))
    ).scalars().all()
    assert remaining == ["purge-2", "purge-3"]


# ---------------------------------------------------------------------------
# 8) 作用域隔离
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_different_users_do_not_share_keys(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    published_tool: Tool,
) -> None:
    """同一个键在两个用户下互不命中（scope 里带 user_id）。"""

    alice_response = await _post_task(
        api_client, published_tool.id, key="shared-key", token=ALICE_TOKEN
    )
    bob_response = await _post_task(
        api_client, published_tool.id, key="shared-key", token=BOB_TOKEN
    )

    assert alice_response.status_code == 200, alice_response.text
    assert bob_response.status_code == 200, bob_response.text
    assert alice_response.json()["data"]["id"] != bob_response.json()["data"]["id"]
    assert await _task_count(db_session) == 2


# ---------------------------------------------------------------------------
# 9) 服务层纯函数与判定（单元）
# ---------------------------------------------------------------------------


def test_build_scope_shape() -> None:
    """scope 是 ``{user_id}:{METHOD}:{path_template}``，方法统一大写。"""
    assert (
        build_scope(user_id="u_123", method="post", path_template="/api/v1/tasks")
        == "u_123:POST:/api/v1/tasks"
    )
    assert build_scope(user_id="u_1", method="POST", path_template="/a") != build_scope(
        user_id="u_2", method="POST", path_template="/a"
    )


def test_hash_request_includes_query_method_path_and_body() -> None:
    """四段都进哈希：任一不同都必须是不同的指纹。"""
    base = hash_request(method="POST", path="/api/v1/tasks", query="", body=b'{"a":1}')
    assert base == hash_request(
        method="post", path="/api/v1/tasks", query="", body=b'{"a":1}'
    )
    assert base != hash_request(
        method="POST", path="/api/v1/tasks", query="x=1", body=b'{"a":1}'
    )
    assert base != hash_request(
        method="POST", path="/api/v1/tasks/other", query="", body=b'{"a":1}'
    )
    assert base != hash_request(
        method="POST", path="/api/v1/tasks", query="", body=b'{"a":2}'
    )
    assert base != hash_request(
        method="PUT", path="/api/v1/tasks", query="", body=b'{"a":1}'
    )
    assert len(base) == 64


def test_hash_request_treats_empty_body_uniformly() -> None:
    """``body=None`` 与 ``b""`` 等价，避免「无体」请求算出两个指纹。"""
    assert hash_request(
        method="GET", path="/x", query="", body=b""
    ) == hash_request(method="GET", path="/x", query="", body=None)


@pytest.mark.asyncio
async def test_begin_request_reports_conflict_and_replay(
    db_session: AsyncSession,
) -> None:
    """服务层三条判定的直接断言（不经过 HTTP 层）。"""
    scope = build_scope(user_id="u_1", method="POST", path_template="/api/v1/tasks")

    first = await begin_request(
        db_session, scope=scope, key="k", request_hash="a" * 64, user_id="u_1"
    )
    assert first.status == "acquired"
    assert first.record is not None and first.record.state == "IN_PROGRESS"

    again = await begin_request(
        db_session, scope=scope, key="k", request_hash="a" * 64, user_id="u_1"
    )
    assert again.status == OUTCOME_IN_FLIGHT

    different = await begin_request(
        db_session, scope=scope, key="k", request_hash="b" * 64, user_id="u_1"
    )
    assert different.status == OUTCOME_CONFLICT_BODY

    from app.services.idempotency import complete_request

    await complete_request(
        db_session, scope=scope, key="k", status_code=201, body={"code": 200}
    )
    replay = await begin_request(
        db_session, scope=scope, key="k", request_hash="a" * 64, user_id="u_1"
    )
    assert replay.status == OUTCOME_REPLAY
    assert replay.response == (201, {"code": 200})
