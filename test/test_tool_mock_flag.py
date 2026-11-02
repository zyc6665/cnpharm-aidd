"""工具序列化的 mock 标记必须来自工具包清单，而不是页面或常量。

背景：前端曾经把「本结果由 mock 模型包生成」硬编码在提交页上，真实模型包
上线后这条提示变成事实错误。真值只能来自工具包 manifest 的 metadata.mock。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.services.tool_presentation import serialize_tool


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _make_tool(db: AsyncSession, *, slug: str, config: dict) -> Tool:
    user = User(
        email=f"{slug}@example.com",
        password_hash="x",
        display_name=slug,
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()
    tool = Tool(
        owner_id=user.id,
        name=f"工具 {slug}",
        slug=slug,
        description="",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(tool_id=tool.id, version="1.0.0", config=config, is_active=True)
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    await db.commit()
    return (
        (
            await db.execute(
                select(Tool)
                .options(
                    selectinload(Tool.current_version),
                    selectinload(Tool.tags),
                    selectinload(Tool.tool_category),
                    joinedload(Tool.statistics),
                )
                .where(Tool.id == tool.id)
            )
        )
        .scalars()
        .one()
    )


@pytest.mark.asyncio
async def test_real_package_is_not_marked_mock(db: AsyncSession) -> None:
    tool = await _make_tool(
        db, slug="real-tool", config={"type": "k8s_job", "image": "reg/x@sha256:abc"}
    )
    payload = serialize_tool(tool)
    assert payload["mock"] is False


@pytest.mark.asyncio
async def test_package_declaring_mock_is_marked(db: AsyncSession) -> None:
    config = {
        "type": "k8s_job",
        "tool_package_manifest": {
            "api_version": "aidd.sciminer/tool-package",
            "kind": "ToolPackage",
            "metadata": {
                "slug": "mock-tool",
                "name": "演示工具",
                "version": "1.0.0",
                "mock": True,
            },
        },
    }
    tool = await _make_tool(db, slug="mock-tool", config=config)
    payload = serialize_tool(tool)
    assert payload["mock"] is True
