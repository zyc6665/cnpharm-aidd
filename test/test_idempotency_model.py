"""``IdempotencyKey`` 模型层约束测试（docs/04 §5.5）。

只验证**数据库**这一层的承诺：``(scope, key)`` 复合主键真的会挡住第二次插入。
这正是 ``INSERT ... ON CONFLICT (scope, key) DO NOTHING`` 能当抢锁用的前提——如果
唯一性只存在于应用代码里，并发重试就会各插一行。
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.time import utcnow  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.models.idempotency import IdempotencyKey  # noqa: E402


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


def _row(*, scope: str = "u_1:POST:/api/v1/tasks", key: str = "k-1", **overrides):
    now = utcnow()
    values = {
        "scope": scope,
        "key": key,
        "request_hash": "a" * 64,
        "state": "IN_PROGRESS",
        "response_status": None,
        "response_body": None,
        "user_id": "u_1",
        "resource_type": None,
        "resource_id": None,
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(hours=24),
    }
    values.update(overrides)
    return IdempotencyKey(**values)


def test_table_shape_matches_spec() -> None:
    """表名、复合主键与两个二级索引与 docs/04 §5.5 一致。"""
    table = IdempotencyKey.__table__

    assert table.name == "idempotency_keys"
    assert [column.name for column in table.primary_key.columns] == ["scope", "key"]
    assert IdempotencyKey.__mapper__.primary_key[0].name == "scope"

    index_names = {index.name for index in table.indexes}
    assert "ix_idempotency_keys_expires_at" in index_names
    assert "ix_idempotency_keys_user_id" in index_names


def test_required_columns_are_not_nullable() -> None:
    """``request_hash`` / ``state`` / 时间戳必须 NOT NULL，否则「同键异体」判定会漏判。"""
    table = IdempotencyKey.__table__
    for name in ("scope", "key", "request_hash", "state", "created_at", "updated_at", "expires_at"):
        assert table.columns[name].nullable is False, name
    for name in ("response_status", "response_body", "resource_type", "resource_id"):
        assert table.columns[name].nullable is True, name


@pytest.mark.asyncio
async def test_duplicate_scope_and_key_raises_integrity_error(
    db_session: AsyncSession,
) -> None:
    """同 ``(scope, key)`` 的第二次插入必须被数据库拒绝。"""
    db_session.add(_row())
    await db_session.commit()

    # 先清身份映射再 add：``scope``/``key`` 是主键，若第一行还挂在 identity map 里，
    # SQLAlchemy 会把第二次 add 视为同一个对象而静默合并（甚至不发 SQL）。
    db_session.expunge_all()
    db_session.add(_row(request_hash="b" * 64))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_different_key_or_scope_is_allowed(db_session: AsyncSession) -> None:
    """复合主键只在 ``(scope, key)`` 两个字段都相同时才冲突。"""
    db_session.add(_row(key="k-1"))
    db_session.add(_row(key="k-2"))
    db_session.add(_row(scope="u_2:POST:/api/v1/tasks", key="k-1"))
    await db_session.commit()

    assert (await db_session.execute(IdempotencyKey.__table__.select())).all() != []
    from sqlalchemy import func, select

    total = (await db_session.execute(select(func.count()).select_from(IdempotencyKey))).scalar_one()
    assert total == 3


@pytest.mark.asyncio
async def test_inspector_sees_primary_key_columns(db_session: AsyncSession) -> None:
    """迁移建出来的复合主键在 inspector 里也应是两列（防止迁移与模型漂移）。"""
    connection = await db_session.connection()

    def _inspect(sync_connection):
        inspector = inspect(sync_connection)
        return inspector.get_pk_constraint("idempotency_keys")["constrained_columns"]

    columns = await connection.run_sync(_inspect)
    assert columns == ["scope", "key"]
