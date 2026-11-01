"""任务事件 SSE 端点测试（docs/05 §1.5、§9；docs/10 API-08）。"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.database.base import Base
from app.database.session import get_db
from app.main import app as main_app
from app.models.tasks import Task, TaskLog, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User
from app.services.task_event_hub import TaskEventHub
from app.services.task_event_stream import (
    EVENT_DONE,
    EVENT_HEARTBEAT,
    EVENT_PROGRESS,
    EVENT_SNAPSHOT,
    EVENT_STATUS,
    TaskEventState,
    describe_delta,
    format_sse,
    load_state,
    stream_task_events,
)




# ---------------------------------------------------------------- fixtures


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def _make_user(db: AsyncSession, *, email: str = "owner@example.com", role: str = "user") -> User:
    user = User(
        email=email,
        password_hash="hashed",
        display_name=email.split("@")[0],
        role=role,
        status="active",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_task(db: AsyncSession, user: User, *, status: str = TaskStatus.RUNNING.value) -> Task:
    tool = Tool(
        owner_id=user.id,
        name="SSE 测试工具",
        slug=f"sse-tool-{status.lower()}",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(tool_id=tool.id, version="1.0.0", config={"type": "python_script"}, is_active=True)
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id

    task = Task(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        name="SSE 测试任务",
        status=status,
        progress=10.0,
        progress_message="准备中",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


# ---------------------------------------------------------------- 帧格式


def test_format_sse_emits_id_event_and_data() -> None:
    frame = format_sse(EVENT_PROGRESS, {"taskId": "t-1", "progress": 42}, event_id="7")

    assert frame.startswith("id: 7\n")
    assert "event: progress\n" in frame
    assert frame.endswith("\n\n")
    payload = [line[6:] for line in frame.splitlines() if line.startswith("data: ")]
    assert json.loads("".join(payload)) == {"taskId": "t-1", "progress": 42}


def test_format_sse_escapes_newlines_inside_json_data() -> None:
    """多行文本必须转义在 JSON 里，否则会把一帧拆成两个 data 行。"""
    frame = format_sse(EVENT_STATUS, {"taskId": "t-1", "progressMessage": "第一行\n第二行"}, event_id="3")

    data_lines = [line for line in frame.splitlines() if line.startswith("data: ")]
    assert len(data_lines) == 1
    assert json.loads(data_lines[0][6:])["progressMessage"] == "第一行\n第二行"
    assert "第一行\n第二行" not in frame


def test_format_heartbeat_is_a_comment_frame() -> None:
    from app.services.task_event_stream import format_heartbeat

    assert format_heartbeat() == ": ping\n\n"
    assert EVENT_HEARTBEAT == "heartbeat"


# ---------------------------------------------------------------- 差分判定


def _state(status: str, progress: float = 0.0, message: str | None = None) -> TaskEventState:
    return TaskEventState(status=status, progress=progress, progress_message=message, error_message=None, updated_at=None)


def test_describe_delta_reports_snapshot_then_status_then_progress() -> None:
    running = _state(TaskStatus.RUNNING.value, 10.0, "准备中")
    assert describe_delta(None, running) == EVENT_SNAPSHOT
    assert describe_delta(running, running) is None

    succeeded = _state(TaskStatus.SUCCESS.value, 100.0, "完成")
    assert describe_delta(running, succeeded) == EVENT_STATUS

    advanced = _state(TaskStatus.RUNNING.value, 55.0, "对接中")
    assert describe_delta(running, advanced) == EVENT_PROGRESS

    same_progress_new_message = _state(TaskStatus.RUNNING.value, 55.0, "打分中")
    assert describe_delta(advanced, same_progress_new_message) == EVENT_PROGRESS


def test_terminal_state_property_covers_all_terminal_statuses() -> None:
    for status in (TaskStatus.SUCCESS.value, TaskStatus.FAILURE.value, TaskStatus.CANCELED.value):
        assert _state(status).terminal is True
    for status in (TaskStatus.PENDING.value, TaskStatus.RUNNING.value):
        assert _state(status).terminal is False


# ---------------------------------------------------------------- 生成器


async def _collect(
    generator: AsyncIterator[str],
    *,
    limit: int,
    timeout: float = 5.0,
) -> list[str]:
    frames: list[str] = []
    async def _run() -> None:
        async for frame in generator:
            frames.append(frame)
            if len(frames) >= limit:
                return
    await asyncio.wait_for(_run(), timeout=timeout)
    return frames


@pytest.mark.asyncio
async def test_stream_emits_snapshot_then_done_for_terminal_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    hub = TaskEventHub()
    terminal = _state(TaskStatus.SUCCESS.value, 100.0, "完成")

    generator = stream_task_events(
        session_factory=session_factory,
        task_id="task-terminal",
        initial=terminal,
        hub=hub,
    )
    frames = await _collect(generator, limit=2)
    await generator.aclose()

    assert "event: snapshot" in frames[0]
    assert "event: done" in frames[1]
    assert hub.subscriber_count("task-terminal") == 0


@pytest.mark.asyncio
async def test_stream_picks_up_status_change_from_worker_notification(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    task = await _make_task(db_session, user, status=TaskStatus.RUNNING.value)
    hub = TaskEventHub()
    initial = await load_state(db_session, task.id)
    assert initial is not None

    generator = stream_task_events(
        session_factory=session_factory,
        task_id=task.id,
        initial=initial,
        poll_interval_seconds=0.05,
        heartbeat_seconds=30,
        hub=hub,
        include_logs=False,
    )

    first = await asyncio.wait_for(generator.__anext__(), timeout=5)
    assert EVENT_SNAPSHOT in first

    # 模拟 worker 完成落库后广播
    async with session_factory() as session:
        stored = await session.get(Task, task.id)
        stored.status = TaskStatus.SUCCESS.value
        stored.progress = 100.0
        stored.progress_message = "完成"
        await session.commit()
    hub.publish(task.id, {"type": "status"})

    second = await asyncio.wait_for(generator.__anext__(), timeout=5)
    assert "event: status" in second
    assert '"status": "success"' in second.replace("\n", " ")

    third = await asyncio.wait_for(generator.__anext__(), timeout=5)
    assert EVENT_DONE in third
    await generator.aclose()


@pytest.mark.asyncio
async def test_stream_converges_without_any_notification(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """跨进程场景：worker 在别的进程改了库，本进程收不到广播也必须收敛。"""
    user = await _make_user(db_session)
    task = await _make_task(db_session, user, status=TaskStatus.RUNNING.value)
    initial = await load_state(db_session, task.id)
    assert initial is not None

    generator = stream_task_events(
        session_factory=session_factory,
        task_id=task.id,
        initial=initial,
        poll_interval_seconds=0.05,
        heartbeat_seconds=30,
        hub=TaskEventHub(),
        include_logs=False,
    )
    await asyncio.wait_for(generator.__anext__(), timeout=5)

    async with session_factory() as session:
        stored = await session.get(Task, task.id)
        stored.progress = 66.0
        stored.progress_message = "MD 采样中"
        await session.commit()

    frame = await asyncio.wait_for(generator.__anext__(), timeout=5)
    assert EVENT_PROGRESS in frame
    assert '"progress": 66.0' in frame.replace("\n", " ")
    await generator.aclose()


@pytest.mark.asyncio
async def test_stream_emits_new_log_entries(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    task = await _make_task(db_session, user, status=TaskStatus.RUNNING.value)
    initial = await load_state(db_session, task.id)
    assert initial is not None

    generator = stream_task_events(
        session_factory=session_factory,
        task_id=task.id,
        initial=initial,
        poll_interval_seconds=0.05,
        heartbeat_seconds=30,
        hub=TaskEventHub(),
        include_logs=True,
    )
    await asyncio.wait_for(generator.__anext__(), timeout=5)

    async with session_factory() as session:
        session.add(TaskLog(task_id=task.id, level="INFO", message="第一帧开始"))
        await session.commit()

    frame = await asyncio.wait_for(generator.__anext__(), timeout=5)
    assert "event: log" in frame
    assert "第一帧开始" in frame
    await generator.aclose()


@pytest.mark.asyncio
async def test_stream_emits_heartbeat_when_idle(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    task = await _make_task(db_session, user, status=TaskStatus.RUNNING.value)
    initial = await load_state(db_session, task.id)
    assert initial is not None

    generator = stream_task_events(
        session_factory=session_factory,
        task_id=task.id,
        initial=initial,
        poll_interval_seconds=0.05,
        heartbeat_seconds=0.1,
        hub=TaskEventHub(),
        include_logs=False,
    )
    frames = await _collect(generator, limit=2, timeout=5)
    assert EVENT_SNAPSHOT in frames[0]
    assert frames[1] == ": ping\n\n"
    await generator.aclose()


@pytest.mark.asyncio
async def test_stream_stops_at_max_duration(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """数小时级任务不能一直占着连接，到时限后关流由前端重连续订。"""
    user = await _make_user(db_session)
    task = await _make_task(db_session, user, status=TaskStatus.RUNNING.value)
    initial = await load_state(db_session, task.id)
    assert initial is not None

    generator = stream_task_events(
        session_factory=session_factory,
        task_id=task.id,
        initial=initial,
        poll_interval_seconds=0.05,
        heartbeat_seconds=30,
        max_duration_seconds=0.1,
        hub=TaskEventHub(),
        include_logs=False,
    )
    frames = await _collect(generator, limit=2, timeout=5)
    assert frames[1] == ": ping\n\n"
    with pytest.raises(StopAsyncIteration):
        await generator.__anext__()


@pytest.mark.asyncio
async def test_stream_reports_missing_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    generator = stream_task_events(
        session_factory=session_factory,
        task_id="missing-task",
        initial=_state(TaskStatus.RUNNING.value, 5.0),
        poll_interval_seconds=0.05,
        heartbeat_seconds=30,
        hub=TaskEventHub(),
        include_logs=False,
    )
    await asyncio.wait_for(generator.__anext__(), timeout=5)
    frame = await asyncio.wait_for(generator.__anext__(), timeout=5)
    assert "任务已不存在" in frame


# ---------------------------------------------------------------- 事件中枢


def test_hub_drops_events_when_subscriber_queue_is_full() -> None:
    hub = TaskEventHub(queue_size=1)
    queue = hub.subscribe("task-1")

    assert hub.publish("task-1", {"type": "a"}) == 1
    assert hub.publish("task-1", {"type": "b"}) == 0
    assert queue.qsize() == 1
    assert hub.total_subscribers() == 1

    hub.unsubscribe("task-1", queue)
    assert hub.total_subscribers() == 0
    assert hub.publish("task-1", {"type": "c"}) == 0


# ---------------------------------------------------------------- HTTP 端点


def _build_app(session_factory: async_sessionmaker[AsyncSession], user: User | None) -> FastAPI:
    """复用真实 app，否则 AppException 的异常处理器不会生效（测试会看到裸异常）。"""
    app = main_app

    async def _get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    return app


@pytest.mark.asyncio
async def test_sse_endpoint_returns_event_stream_headers(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    task = await _make_task(db_session, user, status=TaskStatus.SUCCESS.value)
    app = _build_app(session_factory, user)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream("GET", f"/api/v1/tasks/{task.id}/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["cache-control"] == "no-cache"
            assert response.headers["x-accel-buffering"] == "no"
            body = await response.aread()

    text = body.decode("utf-8")
    assert "event: snapshot" in text
    assert "event: done" in text


@pytest.mark.asyncio
async def test_sse_endpoint_requires_authentication(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    task = await _make_task(db_session, user, status=TaskStatus.SUCCESS.value)
    app = _build_app(session_factory, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/tasks/{task.id}/events")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sse_endpoint_hides_other_users_tasks(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    owner = await _make_user(db_session, email="owner@example.com")
    intruder = await _make_user(db_session, email="intruder@example.com")
    task = await _make_task(db_session, owner, status=TaskStatus.SUCCESS.value)
    app = _build_app(session_factory, intruder)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/tasks/{task.id}/events")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sse_endpoint_missing_task_returns_forbidden(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    app = _build_app(session_factory, user)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/tasks/no-such-task/events")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sse_endpoint_ignores_query_token(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """P2：SSE 不再接受 ``?token=`` 查询参数（只能 Cookie/Bearer 认证）。

    即便传入一个完全合法的 access token，缺少 Cookie/Bearer 也必须是 401，
    避免长寿命凭证泄漏到 URL / 访问日志 / Referer。
    """
    from app.auth.jwt_handler import jwt_handler

    user = await _make_user(db_session)
    task = await _make_task(db_session, user, status=TaskStatus.SUCCESS.value)
    app = _build_app(session_factory, None)
    token = jwt_handler.create_access_token(user.id, user.email, user.role)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/tasks/{task.id}/events?token={token}")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sse_endpoint_rejects_invalid_query_token(
    session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    task = await _make_task(db_session, user, status=TaskStatus.SUCCESS.value)
    app = _build_app(session_factory, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/v1/tasks/{task.id}/events?token=not-a-token")

    assert response.status_code == 401
