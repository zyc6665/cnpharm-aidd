"""traceId 全链路串联（G-7）。

覆盖 docs/05 §1.1（``X-Request-Id`` 服务端生成并回传、写入日志）、§1.2（统一响应体
的 ``requestId`` / ``timestamp``）、docs/10 §8.3（W3C ``traceparent`` 透传、
``task.env_json.traceId`` 在本仓库的等价物是 ``task.extra_data.traceId``）、
docs/12 TC-NFR-09（可按 traceId 串起全链路）与 DEF-02（缺陷附 ``trace_id``）。

测试分四层：

1. **原语**：ID 形态、``traceparent`` 解析（含垃圾输入不抛错）、``TraceIdFilter``；
2. **响应信封**：helper 在没有请求上下文时 ``requestId=None`` 而不抛错；
3. **HTTP 契约**：回显/生成/非法输入降级/404/429，以及两个并发请求不串 ID；
4. **链路串联与回归**：任务 ``extra_data.traceId``、``GET /tasks/{id}`` 回读、
   审计 ``request_id``、K8s 出站头，以及 SSE 端点不被中间件缓冲。

fixture 形态沿用 ``test/test_traceability_api.py``（内存 SQLite + 覆盖 ``get_db`` /
``get_current_user``，并复用真 ``app.main.app``，否则 AppException 的异常处理器不生效）。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1 import tasks as tasks_api  # noqa: E402
from app.auth.dependencies import get_current_user, get_current_user_optional  # noqa: E402
from app.common.responses import error_response, paginated_response, success_response  # noqa: E402
from app.common.trace import (  # noqa: E402
    MAX_TRACE_ID_LENGTH,
    PLACEHOLDER,
    TRACE_ID_HEADER,
    TraceIdFilter,
    get_trace_id,
    new_trace_id,
    normalize_incoming_trace_id,
    parse_traceparent,
    reset_trace_id,
    set_trace_id,
)
from app.config import settings as config_settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.logging.audit import AuditAction, AuditLogger, ResourceType  # noqa: E402
from app.main import app as main_app  # noqa: E402
from app.middleware.trace import TraceIdMiddleware  # noqa: E402
from app.models.tasks import Task, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402

ALICE = "alice-token"


# ---------------------------------------------------------------------------
# fixtures（照抄 test_traceability_api.py / test_idempotency.py 的形态）
# ---------------------------------------------------------------------------


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


async def _make_user(db: AsyncSession, email: str = "alice@example.com") -> User:
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
async def user(db_session: AsyncSession) -> User:
    return await _make_user(db_session)


@pytest_asyncio.fixture
async def published_tool(db_session: AsyncSession, user: User) -> Tool:
    tool = Tool(
        owner_id=user.id,
        name="Trace Docking",
        slug="trace-docking",
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
    db_session: AsyncSession, user: User, direct_runner_stub: SimpleNamespace
):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token == ALICE:
            return user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    main_app.dependency_overrides[get_db] = override_get_db
    main_app.dependency_overrides[get_current_user] = override_get_current_user
    transport = httpx.ASGITransport(app=main_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    main_app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def no_leaked_trace_context():
    """每条用例都从「无请求上下文」开始，结束后也不留下 contextvar。

    这条 fixture 本身就是 ``finally: reset`` 的守卫：如果被测代码漏了复位，下一条
    用例一开始就会看到残留的 traceId 而在这里失败，而不是在别处表现出难查的串号。
    """
    assert get_trace_id() is None
    yield
    assert get_trace_id() is None


def _headers(token: str = ALICE, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


# ---------------------------------------------------------------------------
# 1) 原语
# ---------------------------------------------------------------------------


def test_new_trace_id_has_documented_prefix_and_is_unique():
    """docs/05 §1.2 的示例是 ``req_01J...``：前缀 + 定长 + 不重复。"""
    first, second = new_trace_id(), new_trace_id()
    assert first.startswith("req_")
    assert len(first) <= MAX_TRACE_ID_LENGTH
    assert first != second
    assert first[4:].isalnum()


def test_trace_context_set_get_reset_roundtrip():
    token = set_trace_id("req_manual")
    assert get_trace_id() == "req_manual"
    reset_trace_id(token)
    assert get_trace_id() is None


def test_parse_traceparent_extracts_trace_id():
    header = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    assert parse_traceparent(header) == "4bf92f3577b34da6a3ce929d0e0e4736"


@pytest.mark.parametrize(
    "garbage",
    [
        None,
        "",
        "   ",
        "not-a-traceparent",
        # 版本不是 00
        "01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        # trace-id 位数不对
        "00-4bf92f3577b34da6a3ce929d0e0e47-00f067aa0ba902b7-01",
        # parent-id 位数不对
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902-01",
        # 大写十六进制（W3C 规范要求小写）
        "00-4BF92F3577B34DA6A3CE929D0E0E4736-00f067aa0ba902b7-01",
        # 规范里的无效保留值
        "00-" + "0" * 32 + "-00f067aa0ba902b7-01",
        # 换行注入
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01\r\nX-Evil: 1",
    ],
)
def test_parse_traceparent_returns_none_for_garbage(garbage):
    """上游发垃圾不能把请求打挂：一律 None，由中间件生成新 ID。"""
    assert parse_traceparent(garbage) is None


def test_normalize_incoming_trace_id_rejects_control_characters():
    assert normalize_incoming_trace_id("req_01JABCDEFG") == "req_01JABCDEFG"
    assert normalize_incoming_trace_id("  req_01JABCDEFG  ") == "req_01JABCDEFG"
    # 换行会撕裂日志行，超长会撞 ``audit_logs.request_id`` 的 String(64)。
    assert normalize_incoming_trace_id("req_x\nINFO fake") is None
    assert normalize_incoming_trace_id("x" * (MAX_TRACE_ID_LENGTH + 1)) is None
    assert normalize_incoming_trace_id("") is None
    assert normalize_incoming_trace_id(None) is None


def test_trace_id_filter_injects_placeholder_without_request_context():
    """docs/10 §8.1 把 ``trace_id`` 列为必填 → 没有上下文时写 ``-`` 而不是缺字段。"""
    import logging

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", (), None)
    assert TraceIdFilter().filter(record) is True
    assert record.trace_id == PLACEHOLDER

    token = set_trace_id("req_from_request")
    try:
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", (), None)
        TraceIdFilter().filter(record)
        assert record.trace_id == "req_from_request"
    finally:
        reset_trace_id(token)


# ---------------------------------------------------------------------------
# 2) 响应信封
# ---------------------------------------------------------------------------


def test_response_helpers_degrade_without_request_context():
    """无请求上下文（单测/脚本里拼信封）时 ``requestId`` 为 None，不抛错。"""
    for payload in (
        success_response(data={"ok": True}),
        paginated_response(items=[], total=0, page=1, page_size=20),
        error_response("boom", code=500),
    ):
        assert payload["requestId"] is None
        assert payload["timestamp"].endswith("Z")


def test_response_helpers_carry_current_trace_id():
    token = set_trace_id("req_in_context")
    try:
        payload = success_response(data={"ok": True})
    finally:
        reset_trace_id(token)
    assert payload["requestId"] == "req_in_context"


# ---------------------------------------------------------------------------
# 3) HTTP 契约
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_without_headers_gets_generated_id(
    api_client: httpx.AsyncClient, published_tool: Tool
) -> None:
    """无入站头 → 生成新 ID，响应头与响应体 ``requestId`` 必须是同一个值。"""
    response = await api_client.get("/api/v1/tasks", headers=_headers())

    assert response.status_code == 200
    trace_id = response.headers[TRACE_ID_HEADER]
    assert trace_id.startswith("req_")
    assert response.json()["requestId"] == trace_id
    assert response.json()["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_incoming_request_id_is_echoed_verbatim(api_client: httpx.AsyncClient) -> None:
    """有入站 ``X-Request-Id`` 时原样回传，**不能**重新生成。"""
    response = await api_client.get(
        "/api/v1/tasks", headers=_headers(**{TRACE_ID_HEADER: "gateway-req-42"})
    )

    assert response.status_code == 200
    assert response.headers[TRACE_ID_HEADER] == "gateway-req-42"
    assert response.json()["requestId"] == "gateway-req-42"


@pytest.mark.asyncio
async def test_valid_traceparent_supplies_trace_id(api_client: httpx.AsyncClient) -> None:
    """只有 ``traceparent`` 时取它的 trace-id（docs/10 §8.3 的 W3C 透传）。"""
    response = await api_client.get(
        "/api/v1/tasks",
        headers=_headers(traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
    )

    assert response.status_code == 200
    assert response.headers[TRACE_ID_HEADER] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert response.json()["requestId"] == "4bf92f3577b34da6a3ce929d0e0e4736"


@pytest.mark.asyncio
async def test_request_id_header_wins_over_traceparent(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/tasks",
        headers=_headers(
            **{
                TRACE_ID_HEADER: "gateway-req-7",
                "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            }
        ),
    )

    assert response.headers[TRACE_ID_HEADER] == "gateway-req-7"


@pytest.mark.asyncio
async def test_invalid_traceparent_does_not_break_the_request(
    api_client: httpx.AsyncClient,
) -> None:
    """非法 ``traceparent`` → 不崩、回落到生成新 ID。"""
    response = await api_client.get(
        "/api/v1/tasks", headers=_headers(traceparent="00-truncated")
    )

    assert response.status_code == 200
    trace_id = response.headers[TRACE_ID_HEADER]
    assert trace_id.startswith("req_")
    assert response.json()["requestId"] == trace_id


@pytest.mark.asyncio
async def test_error_response_carries_request_id(api_client: httpx.AsyncClient) -> None:
    """404 走 ``AppException`` 处理器，失败信封也必须带 ``requestId`` / ``timestamp``。"""
    response = await api_client.get(
        "/api/v1/tasks/no-such-task", headers=_headers(**{TRACE_ID_HEADER: "req_404_case"})
    )

    assert response.status_code == 404
    body = response.json()
    assert body["requestId"] == "req_404_case"
    assert body["timestamp"].endswith("Z")
    assert response.headers[TRACE_ID_HEADER] == "req_404_case"


@pytest.mark.asyncio
async def test_rate_limited_response_carries_request_id(api_client: httpx.AsyncClient) -> None:
    """限流中间件拒掉的 429 也必须带 ``X-Request-Id``。

    这是「trace 中间件在最外层」的**行为级**断言：``rate_limit.py`` 自己构造
    ``JSONResponse``，它不认识 traceId，只能靠外层中间件补头。所以这条用例既验证
    注册顺序（``app.user_middleware[0]`` 是 TraceIdMiddleware），又验证真实 429
    响应上确实有头——只断言列表顺序的话，顺序对了但头没写也照样绿。
    """
    assert main_app.user_middleware[0].cls is TraceIdMiddleware

    limit = int(config_settings.REQUEST_RATE_LIMIT_PER_MINUTE)
    last = None
    for index in range(limit + 2):
        headers = {} if index < limit else {TRACE_ID_HEADER: "req_429_case"}
        last = await api_client.get("/api/v1/tasks", headers={**_headers(), **headers})
        if last.status_code == 429:
            break

    assert last is not None and last.status_code == 429
    assert last.headers["X-RateLimit-Limit"] == str(limit)
    assert last.headers[TRACE_ID_HEADER] == "req_429_case"


@pytest.mark.asyncio
async def test_contextvar_is_reset_after_request_finishes() -> None:
    """请求结束后 contextvar 必须复位。

    为什么要在**调用方自己的 task 里**断言：ASGI 测试里 ``ASGITransport`` 是直接
    ``await`` 应用的，中间件与调用方共享同一个 context —— 漏掉 ``finally: reset``
    时，残留的 traceId 在这里立刻可见。反过来，如果只在另一个 ``asyncio.Task``
    里发请求（``asyncio.gather`` / 客户端连接池），context 是复制出来的，泄漏被
    隔离在子 task 里，测不出来。

    真实后果：中间件实例是进程级单例，uvicorn 复用同一个 task 处理同一连接的多个
    keep-alive 请求时，第二个请求会继承第一个请求的 traceId——日志与审计里就出现
    「两个请求同一个 ID」，正好是本功能要消灭的东西。
    """

    async def _route() -> dict:
        return {"traceId": get_trace_id()}

    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)
    app.add_api_route("/probe", _route, methods=["GET"])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/probe", headers={TRACE_ID_HEADER: "req_reset_probe"})
        assert response.json()["traceId"] == "req_reset_probe"
        # 请求已经结束，调用方这个 task 的 context 里不该再有它。
        assert get_trace_id() is None


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_share_trace_id() -> None:
    """两个并发请求各自拿到自己的 traceId。

    用独立小应用而不是主应用：主应用的 ``get_db`` 覆盖会共享同一个 ``AsyncSession``，
    并发下那是 SQLAlchemy 的用法错误，会把「contextvar 是否串号」这件事淹掉。
    路由里 ``await asyncio.sleep`` 是刻意制造的让出点——没有它，两个请求根本不会
    重叠，这条用例就测不出漏复位。
    """

    async def _slow_route() -> dict:
        await asyncio.sleep(0.02)
        return success_response(data={"traceId": get_trace_id()})

    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)
    app.add_api_route("/slow", _slow_route, methods=["GET"])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        left, right = await asyncio.gather(
            client.get("/slow", headers={TRACE_ID_HEADER: "req_concurrent_a"}),
            client.get("/slow", headers={TRACE_ID_HEADER: "req_concurrent_b"}),
        )

    assert left.json()["requestId"] == "req_concurrent_a"
    assert right.json()["requestId"] == "req_concurrent_b"
    assert left.json()["data"]["traceId"] == "req_concurrent_a"
    assert right.json()["data"]["traceId"] == "req_concurrent_b"


# ---------------------------------------------------------------------------
# 4) 任务链路
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_creation_stores_trace_id_and_detail_reads_it_back(
    api_client: httpx.AsyncClient, published_tool: Tool
) -> None:
    """创建任务时的 traceId 落到 ``extra_data.traceId``，详情页能原样读回。

    docs/10 §8.3 说的是 ``task.env_json.traceId``；本仓库 ``Task`` 没有 ``env_json``
    列，等价物是 ``extra_data``（JSON 列），键名保留 ``traceId``。
    """
    created = await api_client.post(
        "/api/v1/tasks",
        headers=_headers(**{TRACE_ID_HEADER: "req_task_create"}),
        json={"tool_id": published_tool.id, "name": "Trace Task", "params": {"foo": "bar"}},
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["data"]["id"]
    assert created.json()["data"]["traceId"] == "req_task_create"

    detail = await api_client.get(f"/api/v1/tasks/{task_id}", headers=_headers())
    assert detail.status_code == 200
    assert detail.json()["data"]["traceId"] == "req_task_create"
    # 读详情的这一次请求有自己的 traceId，与任务创建时的那次不同。
    assert detail.json()["requestId"] == detail.headers[TRACE_ID_HEADER]
    assert detail.json()["requestId"] != "req_task_create"


@pytest.mark.asyncio
async def test_task_without_trace_id_returns_none(
    db_session: AsyncSession, api_client: httpx.AsyncClient, user: User, published_tool: Tool
) -> None:
    """功能上线前建的老任务没有这个键 → 返回 None，而不是 500 或空串。"""
    task = Task(
        user_id=user.id,
        tool_id=published_tool.id,
        tool_version_id=published_tool.current_version_id,
        status=TaskStatus.SUCCESS.value,
        name="legacy task",
        extra_data={"project_id": None},
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    detail = await api_client.get(f"/api/v1/tasks/{task.id}", headers=_headers())

    assert detail.status_code == 200
    assert detail.json()["data"]["traceId"] is None


def test_audit_logger_fills_request_id_from_trace_context(tmp_path: Path) -> None:
    """docs/12 DEF-02：审计行要能附上 ``trace_id``。

    ``AuditEvent.request_id`` 与 ``audit_logs.request_id`` 列早就存在，只是历史上没有
    调用点填值。填在 ``AuditLogger.log()`` 这个唯一落盘点，所有 ``log_*`` 入口都覆盖到。
    """
    events = []
    audit = AuditLogger(
        log_dir=str(tmp_path / "audit"),
        enable_file_logging=False,
        enable_db_logging=True,
        db_writer=events.append,
    )

    token = set_trace_id("req_audit_1")
    try:
        audit.log_data_access(
            user_id="user-1",
            resource_type=ResourceType.SYSTEM,
            resource_id="audit_logs",
            action=AuditAction.READ,
        )
    finally:
        reset_trace_id(token)

    assert len(events) == 1
    assert events[0].request_id == "req_audit_1"


def test_audit_logger_prefers_explicit_request_id(tmp_path: Path) -> None:
    events = []
    audit = AuditLogger(
        log_dir=str(tmp_path / "audit"),
        enable_file_logging=False,
        enable_db_logging=True,
        db_writer=events.append,
    )

    token = set_trace_id("req_from_context")
    try:
        audit.log_data_access(
            user_id="user-1",
            resource_type=ResourceType.SYSTEM,
            resource_id="audit_logs",
            request_id="req_explicit",
        )
    finally:
        reset_trace_id(token)

    assert events[0].request_id == "req_explicit"
    # 显式参数不能被顺手留在 extra 里（否则审计 detail 会多一个重复字段）。
    assert "request_id" not in events[0].extra


def test_audit_logger_leaves_request_id_empty_outside_request(tmp_path: Path) -> None:
    events = []
    audit = AuditLogger(
        log_dir=str(tmp_path / "audit"),
        enable_file_logging=False,
        enable_db_logging=True,
        db_writer=events.append,
    )

    audit.log_data_access(user_id="user-1", resource_type=ResourceType.SYSTEM, resource_id="x")

    assert events[0].request_id is None


@pytest.mark.asyncio
async def test_kubernetes_outbound_request_carries_trace_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """docs/10 §8.3「跨服务自动注入」：唯一的跨进程业务出站要带 traceId。"""
    from app.execution.adapters.kubernetes import KubernetesCredentials, KubernetesJobExecutionConfig
    from app.execution.transports.kubernetes_http import KubernetesHttpTransport

    captured: dict = {}

    class _FakeResponse:
        is_success = True
        status_code = 200
        text = "{}"

        def json(self) -> dict:
            return {}

    class _FakeClient:
        async def request(self, method, url, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = kwargs["headers"]
            return _FakeResponse()

    transport = KubernetesHttpTransport(client=_FakeClient())
    config = KubernetesJobExecutionConfig(
        cluster_alias="test-cluster",
        namespace="aidd",
        credential_ref="k8s-test",
        service_account="runner",
    )
    credentials = KubernetesCredentials(api_server="https://k8s.internal", token="tok")

    token = set_trace_id("req_k8s_1")
    try:
        await transport._request("GET", "/api/v1/pods", config, credentials)
    finally:
        reset_trace_id(token)

    assert captured["headers"][TRACE_ID_HEADER] == "req_k8s_1"
    assert captured["headers"]["Authorization"] == "Bearer tok"


# ---------------------------------------------------------------------------
# 5) SSE 回归：trace 中间件不能缓冲流
# ---------------------------------------------------------------------------

async def _make_sse_task(db: AsyncSession, user: User, *, status: str) -> Task:
    tool = Tool(
        owner_id=user.id,
        name="SSE Tool",
        slug=f"sse-tool-{status}",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(
        tool_id=tool.id, version="1.0.0", config={"type": "python_script"}, is_active=True
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    task = Task(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        name="SSE trace task",
        status=status,
        progress=10.0,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@pytest.mark.asyncio
async def test_trace_middleware_does_not_buffer_streaming_responses() -> None:
    """首帧必须在流**结束前**送达。

    这是选纯 ASGI 而不是 ``BaseHTTPMiddleware`` 的唯一理由，所以它值得一条独立的
    回归用例：``BaseHTTPMiddleware`` 会把下游 ``send`` 收进 anyio 内存流再转发，
    下游若在发出首帧后长时间阻塞（SSE 正是如此），首帧就一直压在缓冲里，客户端看到
    的是「连上了但一片空白」。本用例的下游发完首帧就挂住，只等 1 秒——缓冲区里
    等不到帧就只能超时失败。

    实测对照（同一段下游，同一段客户端）：纯 ASGI 首帧在 0.0s 送达，
    ``BaseHTTPMiddleware`` 在 1s 超时窗口内一帧都拿不到。
    """
    release = asyncio.Event()
    received: list[dict] = []

    async def streaming_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b": first\n\n", "more_body": True})
        await release.wait()  # 流保持打开：帧必须在 await 之前就到达客户端

    async def receive():
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    async def send(message):
        received.append(message)

    def first_body() -> bytes | None:
        for message in received:
            if message["type"] == "http.response.body":
                return message["body"]
        return None

    middleware = TraceIdMiddleware(streaming_app)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/stream",
        "raw_path": b"/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"x-request-id", b"req_stream")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    }

    task = asyncio.create_task(middleware(scope, receive, send))
    try:
        deadline = asyncio.get_running_loop().time() + 1.0
        while first_body() is None and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        # 流此时仍然开着（release 未 set），却已经拿到了首帧 → 没有被缓冲。
        assert not release.is_set()
        assert first_body() == b": first\n\n"
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        release.set()

    start = next(m for m in received if m["type"] == "http.response.start")
    assert (b"x-request-id", b"req_stream") in start["headers"]


@pytest.mark.asyncio
async def test_sse_endpoint_still_returns_event_stream(
    db_session: AsyncSession, user: User
) -> None:
    """真端点回归：仍返回 ``text/event-stream``、仍有帧、并带上 ``X-Request-Id``。"""
    task = await _make_sse_task(db_session, user, status=TaskStatus.SUCCESS.value)

    async def override_get_db():
        yield db_session

    main_app.dependency_overrides[get_db] = override_get_db
    main_app.dependency_overrides[get_current_user] = lambda: user
    main_app.dependency_overrides[get_current_user_optional] = lambda: user
    try:
        transport = httpx.ASGITransport(app=main_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            async with client.stream(
                "GET",
                f"/api/v1/tasks/{task.id}/events",
                headers={TRACE_ID_HEADER: "req_sse"},
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                assert response.headers["cache-control"] == "no-cache"
                assert response.headers[TRACE_ID_HEADER] == "req_sse"
                body = await response.aread()

        text_body = body.decode("utf-8")
        assert "event: snapshot" in text_body
        assert "event: done" in text_body
    finally:
        main_app.dependency_overrides.clear()
