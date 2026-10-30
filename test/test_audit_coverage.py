"""审计覆盖率测试（计划 §3.5）。

目标不是复测各端点业务，而是证明：登录/登出、工具任务提交、管理员用户增删改、
工具管理增删改这些**动作被触发后**，审计链路上确实会产生对应 ``action`` 的事件，
并且该事件能落进 ``audit_logs``（用 ``event_to_row`` 映射后逐行断言）。

做法：把 ``AuditLogger`` 单例的 DB writer 换成内存列表捕获事件，触发端点/服务后
断言捕获到期望 ``AuditAction``，再把事件按生产映射写入 ``audit_logs`` 并查询回读。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

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

import app.models as _models  # noqa: F401,E402  注册全部表
from app.api.v1 import tasks as tasks_api  # noqa: E402
from app.auth.dependencies import get_admin_user, get_current_user  # noqa: E402
from app.auth.password import hash_password  # noqa: E402
from app.config import settings as config_settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.logging.audit import AuditAction, get_audit_logger  # noqa: E402
from app.main import app  # noqa: E402
from app.models.tasks import Task  # noqa: E402
from app.models.tools import Tag, Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.traceability import AuditLog  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.schemas.tasks import TaskCreate  # noqa: E402
from app.services.audit_sink import event_to_row  # noqa: E402
from app.tasks.service import create_and_schedule_tool_task  # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


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


async def _make_user(db: AsyncSession, email: str, role: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("Secret123"),
        display_name=email.split("@")[0],
        role=role,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def users(db_session: AsyncSession) -> dict[str, User]:
    return {
        "admin": await _make_user(db_session, "admin@example.com", UserRole.ADMIN.value),
        "member": await _make_user(db_session, "member@example.com", UserRole.USER.value),
    }


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, users: dict[str, User]):
    async def override_get_db():
        yield db_session

    def _resolve(authorization: str | None) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in users:
            return users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    async def override_get_current_user(authorization: str | None = Header(default=None)):
        return _resolve(authorization)

    async def override_get_admin_user(authorization: str | None = Header(default=None)):
        return _resolve(authorization)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_admin_user] = override_get_admin_user
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def captured_events(monkeypatch: pytest.MonkeyPatch) -> list:
    logger = get_audit_logger()
    events: list = []
    monkeypatch.setattr(logger, "enable_file_logging", False, raising=False)
    monkeypatch.setattr(logger, "enable_db_logging", True, raising=False)
    monkeypatch.setattr(logger, "_db_writer", events.append, raising=False)
    return events


@pytest.fixture
def direct_runner(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    runner = SimpleNamespace(
        scheduled=[],
        schedule_task=lambda task_id, tool_version_id: runner.scheduled.append(
            (task_id, tool_version_id)
        ),
        cancel_task=lambda task_id: True,
    )
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)
    return runner


async def _assert_audit_row(db: AsyncSession, events: list, action: AuditAction) -> None:
    """把捕获事件按生产映射写入 audit_logs，并断言存在对应 action 的行。"""
    matched = [e for e in events if e.action == action]
    assert matched, f"expected an audit event for {action.value}, got {[e.action.value for e in events]}"
    for event in matched:
        db.add(AuditLog(**event_to_row(event)))
    await db.commit()
    result = await db.execute(
        select(AuditLog).where(AuditLog.action == action.value.upper())
    )
    assert result.scalars().first() is not None


# --------------------------------------------------------------------------- #
# auth：登录成功/失败、登出
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_login_failure_and_success_emit_audit(
    api_client: httpx.AsyncClient, db_session: AsyncSession, captured_events: list
):
    failed = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "member", "password": "wrong-secret"},
    )
    assert failed.status_code == 401
    assert any(e.action == AuditAction.LOGIN_FAILED for e in captured_events)

    ok = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "member", "password": "Secret123"},
    )
    assert ok.status_code == 200
    await _assert_audit_row(db_session, captured_events, AuditAction.LOGIN_FAILED)
    await _assert_audit_row(db_session, captured_events, AuditAction.LOGIN)


@pytest.mark.asyncio
async def test_logout_emits_audit(
    api_client: httpx.AsyncClient, db_session: AsyncSession, captured_events: list
):
    response = await api_client.post(
        "/api/v1/auth/logout", headers={"Authorization": "Bearer member"}
    )
    assert response.status_code == 200
    await _assert_audit_row(db_session, captured_events, AuditAction.LOGOUT)


# --------------------------------------------------------------------------- #
# 管理员用户增删改
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_admin_user_crud_emits_audit(
    api_client: httpx.AsyncClient, db_session: AsyncSession, captured_events: list
):
    created = await api_client.post(
        "/api/v1/users/admin",
        json={"username": "newbie", "email": "newbie@example.com", "password": "Secret123", "role": "user"},
        headers={"Authorization": "Bearer admin"},
    )
    assert created.status_code == 201
    new_id = created.json()["data"]["id"]

    updated = await api_client.patch(
        f"/api/v1/users/admin/{new_id}",
        json={"display_name": "Newbie Renamed"},
        headers={"Authorization": "Bearer admin"},
    )
    assert updated.status_code == 200

    deleted = await api_client.delete(
        f"/api/v1/users/admin/{new_id}", headers={"Authorization": "Bearer admin"}
    )
    assert deleted.status_code == 200

    await _assert_audit_row(db_session, captured_events, AuditAction.ADMIN_USER_CREATE)
    await _assert_audit_row(db_session, captured_events, AuditAction.ADMIN_USER_UPDATE)
    await _assert_audit_row(db_session, captured_events, AuditAction.ADMIN_USER_DELETE)


# --------------------------------------------------------------------------- #
# 工具管理增删改（含标签创建）
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def seed_tool(db_session: AsyncSession, users: dict[str, User]) -> Tool:
    tool = Tool(
        owner_id=users["admin"].id,
        name="Audit Tool",
        slug="audit-tool",
        description="tool for audit coverage",
        category="generation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        gpu_required=False,
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


@pytest.mark.asyncio
async def test_tool_admin_mutations_emit_audit(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    captured_events: list,
    seed_tool: Tool,
):
    updated = await api_client.put(
        f"/api/v1/tools/{seed_tool.id}",
        json={"description": "updated by audit test"},
        headers={"Authorization": "Bearer admin"},
    )
    assert updated.status_code == 200, updated.text

    tag = await api_client.post(
        "/api/v1/tools/tags",
        json={"name": "audit-tag"},
        headers={"Authorization": "Bearer admin"},
    )
    assert tag.status_code == 200, tag.text

    deleted = await api_client.delete(
        f"/api/v1/tools/{seed_tool.id}", headers={"Authorization": "Bearer admin"}
    )
    assert deleted.status_code == 200, deleted.text

    await _assert_audit_row(db_session, captured_events, AuditAction.ADMIN_TOOL_UPDATE)
    await _assert_audit_row(db_session, captured_events, AuditAction.ADMIN_TOOL_CREATE)
    await _assert_audit_row(db_session, captured_events, AuditAction.DELETE)


# --------------------------------------------------------------------------- #
# 工具任务提交
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tool_task_submit_emits_audit(
    db_session: AsyncSession,
    users: dict[str, User],
    seed_tool: Tool,
    captured_events: list,
    direct_runner: SimpleNamespace,
):
    task = await create_and_schedule_tool_task(
        db=db_session,
        current_user=users["member"],
        task_data=TaskCreate(name="audit submit", tool_id=seed_tool.id, params={}),
        direct_runner=direct_runner,
    )
    assert isinstance(task, Task)
    assert any(e.action == AuditAction.TASK_SUBMIT for e in captured_events)
    await _assert_audit_row(db_session, captured_events, AuditAction.TASK_SUBMIT)
    # 提交已真实分发（没有被配额/校验拦在中间）。
    assert direct_runner.scheduled


# --------------------------------------------------------------------------- #
# 审计队列满：丢弃计数而绝不阻塞业务
# --------------------------------------------------------------------------- #


def test_audit_sink_counts_drops_when_queue_full() -> None:
    """队列满时必须丢弃并计数，而不是抛异常或阻塞请求路径（计划 §3.4）。"""
    import asyncio

    from app.common.time import utcnow
    from app.logging.audit import AuditEvent, AuditResult
    from app.services.audit_sink import AuditDbWriter

    writer = AuditDbWriter(queue_size=1)
    writer._queue = asyncio.Queue(maxsize=1)  # noqa: SLF001
    writer._queue.put_nowait(  # noqa: SLF001
        AuditEvent(id="a", timestamp=utcnow(), action=AuditAction.READ, result=AuditResult.SUCCESS)
    )

    # 队列已满：后续事件被丢弃并计数，但调用方不感知、不阻塞。
    writer(
        AuditEvent(id="b", timestamp=utcnow(), action=AuditAction.LOGIN, result=AuditResult.SUCCESS)
    )
    writer(
        AuditEvent(id="c", timestamp=utcnow(), action=AuditAction.LOGOUT, result=AuditResult.SUCCESS)
    )

    assert writer.dropped == 2
