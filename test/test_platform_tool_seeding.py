"""启动期平台工具 seeding 测试（app/services/platform_tool_seeding.py）。

覆盖任务要求的 4 个断言点：
1. 库里没有 active admin → 返回 skipped=["no-owner"] 且不抛异常、库无变化；
2. 有 admin → 建出全部缺失工具，再调一次 created 为空、工具数不变（幂等）；
3. 工具已存在但版本落后 → 走 UPDATE 还原，而不是重复 INSERT 新行；
4. SEED_PLATFORM_TOOLS_ON_STARTUP=False → 启动期不执行。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - 注册全部 ORM 模型，保证 create_all 建全表
from app.config import settings
from app.database.base import Base
from app.models.tools import Tool, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.services.platform_tool_seeding import (
    REQUIRED_TOOL_SLUGS,
    seed_platform_tools,
    seed_platform_tools_on_startup,
)


# 显式列出扩展后应种出的全部 slug（防止 REQUIRED_TOOL_SLUGS 自身写错时测试自我印证）。
EXPECTED_TOOL_SLUGS = frozenset(
    {
        "lvpocket-pocket-prediction",
        "molp-pc-property-prediction",
        "msign-affinity-prediction",
        "pocket2mol-pocket-ligand-generation",
        "autodock-vina-docking",
        "boltz2-structure-prediction",
        "boltz2-affinity-prediction",
        "therapainter-peptide-prediction",
        "gromacs-md",
        "gmx-mmpbsa",
    }
)


@pytest_asyncio.fixture
async def seed_db(tmp_path):
    """文件型 SQLite 隔离库（同 test_artifact_gc.py 的做法，避免跨 loop 连接问题）。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session, factory
    await engine.dispose()


async def _add_admin(db) -> User:
    user = User(
        email="seed-admin@example.com",
        password_hash="hashed",
        display_name="seed-admin",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.commit()
    return user


async def _count(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.mark.asyncio
async def test_no_admin_returns_skipped_without_raising(seed_db, monkeypatch):
    db, _factory = seed_db
    monkeypatch.setattr(settings, "AIDD_SYSTEM_USER_ID", None)

    before = await _count(db, Tool)
    assert before == 0

    result = await seed_platform_tools(db)
    await db.commit()

    assert result == {"created": [], "existing": [], "skipped": ["no-owner"]}
    assert await _count(db, Tool) == 0


@pytest.mark.asyncio
async def test_seeds_missing_tools_then_is_idempotent(seed_db, monkeypatch):
    db, _factory = seed_db
    monkeypatch.setattr(settings, "AIDD_SYSTEM_USER_ID", None)
    await _add_admin(db)

    # REQUIRED_TOOL_SLUGS 本身要等于这份显式清单（扩展后应为 10 个）。
    assert set(REQUIRED_TOOL_SLUGS) == EXPECTED_TOOL_SLUGS

    first = await seed_platform_tools(db)
    await db.commit()
    assert set(first["created"]) == EXPECTED_TOOL_SLUGS
    assert first["existing"] == []

    count_after_first = await _count(db, Tool)
    assert count_after_first == len(EXPECTED_TOOL_SLUGS)
    # 必备工具全部以 published 状态落库
    rows = (await db.execute(select(Tool.slug, Tool.status))).all()
    assert {slug for slug, _ in rows} == EXPECTED_TOOL_SLUGS
    assert all(status == "published" for _, status in rows)

    second = await seed_platform_tools(db)
    await db.commit()
    assert second["created"] == []
    assert set(second["existing"]) == EXPECTED_TOOL_SLUGS
    assert await _count(db, Tool) == count_after_first


@pytest.mark.asyncio
async def test_outdated_tool_is_updated_not_duplicated(seed_db, monkeypatch):
    db, _factory = seed_db
    monkeypatch.setattr(settings, "AIDD_SYSTEM_USER_ID", None)
    await _add_admin(db)
    await seed_platform_tools(db)
    await db.commit()

    slug = "msign-affinity-prediction"
    tool = (await db.execute(select(Tool).where(Tool.slug == slug))).scalar_one()
    version_id = tool.current_version_id
    version = (
        await db.execute(select(ToolVersion).where(ToolVersion.id == version_id))
    ).scalar_one()
    # 人为把版本与契约改旧，模拟「已存在但落后」的库
    version.version = "0.9.0"
    version.config = {"type": "legacy"}
    await db.commit()

    count_before = await _count(db, Tool)
    result = await seed_platform_tools(db)
    await db.commit()

    assert result["created"] == []
    assert slug in result["existing"]
    assert await _count(db, Tool) == count_before  # 没有新增行

    await db.refresh(version)
    assert version.version == "1.2.0"
    assert version.config.get("type") == "k8s_job"
    assert "tool_package_manifest" in version.config


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", ["autodock-vina-docking", "gromacs-md", "boltz2-affinity-prediction"])
async def test_outdated_new_tool_is_updated_not_duplicated(seed_db, monkeypatch, slug):
    """新增工具（含 gromacs 多工具迁移中的一条）版本落后时也走原地 UPDATE。"""
    db, _factory = seed_db
    monkeypatch.setattr(settings, "AIDD_SYSTEM_USER_ID", None)
    await _add_admin(db)
    await seed_platform_tools(db)
    await db.commit()

    tool = (await db.execute(select(Tool).where(Tool.slug == slug))).scalar_one()
    version = (
        await db.execute(select(ToolVersion).where(ToolVersion.id == tool.current_version_id))
    ).scalar_one()
    version.version = "0.9.0"
    version.config = {"type": "legacy"}
    await db.commit()

    count_before = await _count(db, Tool)
    result = await seed_platform_tools(db)
    await db.commit()

    assert result["created"] == []
    assert slug in result["existing"]
    assert await _count(db, Tool) == count_before  # 没有新增行

    await db.refresh(version)
    assert version.version == "1.0.0"
    assert version.config.get("type") == "k8s_job"
    assert "tool_package_manifest" in version.config


@pytest.mark.asyncio
async def test_startup_flag_false_skips_execution(seed_db, monkeypatch):
    db, factory = seed_db
    monkeypatch.setattr(settings, "AIDD_SYSTEM_USER_ID", None)
    monkeypatch.setattr(settings, "SEED_PLATFORM_TOOLS_ON_STARTUP", False)
    # 让启动入口若能跑到也会命中这个隔离库；断言不执行即无任何工具落库。
    monkeypatch.setattr("app.database.session.async_session_factory", factory)

    await _add_admin(db)

    result = await seed_platform_tools_on_startup()
    assert result is None
    assert await _count(db, Tool) == 0
