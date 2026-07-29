"""工具收藏 API 测试。"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _tasks_models  # noqa: F401
from app.models import users as _users_models  # noqa: F401
from app.models.statistics import ToolStatistics
from app.models.tools import Tool, ToolFavorite
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def user_and_tool(db_session: AsyncSession) -> tuple[User, Tool]:
    user = User(
        email="favorite@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.flush()

    tool = Tool(
        owner_id=user.id,
        name="Favorite Tool",
        slug="favorite-tool",
        status="published",
    )
    db_session.add(tool)
    await db_session.commit()
    return user, tool


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, user_and_tool: tuple[User, Tool]):
    user, _ = user_and_tool

    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == "Bearer user-token":
            return user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_favorite_lifecycle_updates_tool_statistics(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    user_and_tool: tuple[User, Tool],
) -> None:
    """首次收藏创建统计记录，取消收藏将计数恢复为零。"""
    user, tool = user_and_tool

    favorite_response = await api_client.post(
        f"/api/v1/tools/{tool.id}/favorite",
        headers={"Authorization": "Bearer user-token"},
    )
    assert favorite_response.status_code == 200

    statistics = await db_session.get(ToolStatistics, tool.id)
    assert statistics is not None
    assert statistics.favorite_count == 1

    unfavorite_response = await api_client.delete(
        f"/api/v1/tools/{tool.id}/favorite",
        headers={"Authorization": "Bearer user-token"},
    )
    assert unfavorite_response.status_code == 200

    await db_session.refresh(statistics)
    assert statistics.favorite_count == 0
    favorites = await db_session.execute(
        select(ToolFavorite).where(ToolFavorite.user_id == user.id)
    )
    assert favorites.scalar_one_or_none() is None
