"""Performance guardrails for durable AIDD agent event delivery."""

from __future__ import annotations

from time import perf_counter

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models.agent import AgentRun
from app.models.conversations import AgentEvent
from app.models.users import User, UserRole, UserStatus
from app.realtime.agent_events import stream_agent_events


@pytest_asyncio.fixture
async def latency_db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, autoflush=False
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_first_persisted_agent_event_is_replayed_within_two_seconds(
    latency_db: AsyncSession,
):
    """首次 SSE 事件必须优先从数据库快速恢复，不能等待轮询周期。"""
    user = User(
        email="latency-owner@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    latency_db.add(user)
    await latency_db.flush()
    run = AgentRun(
        user_id=user.id,
        message="Find pockets",
        intent="pocket_detection",
        input_type="protein_structure",
        status="running",
    )
    latency_db.add(run)
    await latency_db.flush()
    latency_db.add(
        AgentEvent(
            agent_run_id=run.id,
            sequence=1,
            event_type="plan_created",
            payload={"summary": "Plan ready"},
        )
    )
    await latency_db.commit()

    start = perf_counter()
    stream = stream_agent_events(
        latency_db,
        run_id=run.id,
        after_sequence=0,
        heartbeat_interval=15,
        poll_interval=1,
    )
    try:
        first_event = await anext(stream)
    finally:
        await stream.aclose()
    elapsed = perf_counter() - start

    assert "id: 1\n" in first_event
    assert "event: plan_created\n" in first_event
    assert elapsed < 2.0
