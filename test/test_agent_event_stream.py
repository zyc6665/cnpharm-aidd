"""Recoverable SSE stream tests for durable agent events."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.agent import AgentRun
from app.models.conversations import AgentEvent
from app.models.projects import Organization, Project, ProjectMember
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def stream_db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def stream_context(stream_db: AsyncSession) -> dict[str, object]:
    owner = User(
        email="stream-owner@example.com",
        password_hash="hashed-password",
        display_name="stream-owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    outsider = User(
        email="stream-outsider@example.com",
        password_hash="hashed-password",
        display_name="stream-outsider",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    organization = Organization(name="Stream Lab", slug="stream-lab")
    stream_db.add_all([owner, outsider, organization])
    await stream_db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name="Pocket study",
        goal="Find ligandable pockets",
        status="active",
    )
    stream_db.add(project)
    await stream_db.flush()
    stream_db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    run = AgentRun(
        project_id=project.id,
        user_id=owner.id,
        message="Find pockets",
        intent="pocket_detection",
        input_type="protein_structure",
        status="completed",
    )
    stream_db.add(run)
    await stream_db.flush()
    stream_db.add_all(
        [
            AgentEvent(
                agent_run_id=run.id,
                sequence=sequence,
                event_type="execution_progress",
                payload={"progress": sequence * 10},
            )
            for sequence in (1, 2, 3)
        ]
    )
    await stream_db.commit()
    return {"owner": owner, "outsider": outsider, "run": run}


@pytest_asyncio.fixture
async def stream_client(stream_db: AsyncSession, stream_context: dict[str, object]):
    async def override_get_db():
        yield stream_db

    async def override_get_current_user(authorization: str | None = Header(default=None)) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        user = stream_context.get(token)
        if isinstance(user, User):
            return user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sse_resumes_from_last_event_id_without_creating_events(
    stream_client: httpx.AsyncClient,
    stream_db: AsyncSession,
    stream_context: dict[str, object],
):
    run = stream_context["run"]
    assert isinstance(run, AgentRun)
    event_count_before = await stream_db.scalar(select(func.count(AgentEvent.id)))

    for _ in range(2):
        response = await stream_client.get(
            f"/api/v1/agent-runs/{run.id}/stream",
            headers={"Authorization": "Bearer owner", "Last-Event-ID": "1"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "id: 1\n" not in response.text
        assert f'data: {{"run_id":"{run.id}","payload":{{"progress":20}}}}' in response.text
        assert "id: 2\nevent: execution_progress\n" in response.text
        assert "id: 3\nevent: execution_progress\n" in response.text

    assert await stream_db.scalar(select(func.count(AgentEvent.id))) == event_count_before


@pytest.mark.asyncio
async def test_sse_accepts_after_sequence_and_hides_run_from_non_member(
    stream_client: httpx.AsyncClient,
    stream_context: dict[str, object],
):
    run = stream_context["run"]
    assert isinstance(run, AgentRun)

    resumed = await stream_client.get(
        f"/api/v1/agent-runs/{run.id}/stream?after_sequence=2",
        headers={"Authorization": "Bearer owner"},
    )
    assert resumed.status_code == 200
    assert "id: 2\n" not in resumed.text
    assert "id: 3\n" in resumed.text

    hidden = await stream_client.get(
        f"/api/v1/agent-runs/{run.id}/stream",
        headers={"Authorization": "Bearer outsider"},
    )
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_live_stream_emits_comment_heartbeat_without_background_tasks(
    stream_db: AsyncSession,
    stream_context: dict[str, object],
):
    from app.realtime.agent_events import stream_agent_events

    run = stream_context["run"]
    assert isinstance(run, AgentRun)
    run.status = "running"
    await stream_db.commit()

    stream = stream_agent_events(
        stream_db,
        run_id=run.id,
        after_sequence=3,
        heartbeat_interval=0.01,
        poll_interval=0.005,
    )
    try:
        assert await anext(stream) == ": heartbeat\n\n"
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_stream_closes_injected_wakeup_on_cancellation(
    stream_db: AsyncSession,
    stream_context: dict[str, object],
):
    from app.realtime.agent_events import stream_agent_events

    class RecordingWakeup:
        def __init__(self) -> None:
            self.closed = False

        async def wait(self, timeout: float) -> None:
            await asyncio.sleep(timeout)

        async def close(self) -> None:
            self.closed = True

    run = stream_context["run"]
    assert isinstance(run, AgentRun)
    run.status = "running"
    await stream_db.commit()
    wakeup = RecordingWakeup()
    stream = stream_agent_events(
        stream_db,
        run_id=run.id,
        after_sequence=3,
        heartbeat_interval=0.01,
        poll_interval=0.005,
        wakeup=wakeup,
    )

    assert await anext(stream) == ": heartbeat\n\n"
    await stream.aclose()

    assert wakeup.closed is True


@pytest.mark.asyncio
async def test_redis_connection_failure_falls_back_to_polling(monkeypatch: pytest.MonkeyPatch):
    from app.realtime import agent_events

    async def fail_to_connect(run_id: str):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(agent_events.settings, "CACHE_BACKEND", "redis")
    monkeypatch.setattr(agent_events, "_connect_redis_wakeup", fail_to_connect)

    wakeup = await agent_events.create_agent_event_wakeup("run-1")
    assert isinstance(wakeup, agent_events.PollingAgentEventWakeup)
    await wakeup.close()


@pytest.mark.asyncio
async def test_publish_wakeup_does_not_create_durable_event(
    monkeypatch: pytest.MonkeyPatch,
    stream_db: AsyncSession,
):
    from app.realtime import agent_events

    published: list[tuple[str, str]] = []

    class FakeRedis:
        async def publish(self, channel: str, message: str) -> None:
            published.append((channel, message))

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(agent_events.settings, "CACHE_BACKEND", "redis")
    monkeypatch.setattr(agent_events, "_new_redis_client", lambda: FakeRedis())
    before = await stream_db.scalar(select(func.count(AgentEvent.id)))

    assert await agent_events.publish_agent_event_wakeup("run-1") is True
    assert published == [("scitool:agent-events:run-1", "event")]
    assert await stream_db.scalar(select(func.count(AgentEvent.id))) == before
