"""Append-only guards for the decision record tables (docs/04 §9.5, docs/10 DB-09).

决策记录与 ``audit_logs`` 同级别：写进去就不能改。两个用例分别覆盖「改」与
「删」，因为 SQLAlchemy 的两个事件是分开注册的，只测 `UPDATE` 会让
`before_delete` 漏挂也能过。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.time import utcnow  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.models.decisions import DecisionItem, DecisionRecord  # noqa: E402
from app.models.projects import Organization, Project  # noqa: E402
from app.models.traceability import ImmutableRecordError  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402


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


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    """决策记录外键指向真实项目（``PRAGMA foreign_keys=ON`` 下不能凭空写 ID）。"""
    user = User(
        email="owner@example.com",
        password_hash="hashed-password",
        display_name="owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.flush()
    organization = Organization(name="Decision Lab", slug="decision-lab")
    db_session.add(organization)
    await db_session.flush()
    row = Project(
        organization_id=organization.id,
        created_by=user.id,
        name="EGFR program",
        status="active",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


def _record(project_id: str, **overrides) -> DecisionRecord:
    payload = {
        "project_id": project_id,
        "decision_point": "DP3",
        "subject_type": "CANDIDATE_SET",
        "subject_id": "set_1",
        "reason": "亲和力与成药性均达标",
        "basis_task_ids": ["tsk_1"],
        "basis_metrics": {"avgDockingScore": -8.2},
        "decided_by": "owner@example.com",
        "decided_at": utcnow(),
    }
    payload.update(overrides)
    return DecisionRecord(**payload)


@pytest.mark.asyncio
async def test_decision_record_rejects_update(db_session: AsyncSession, project: Project):
    record = _record(project.id)
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)

    record.reason = "改主意了"
    with pytest.raises(ImmutableRecordError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_decision_item_rejects_delete(db_session: AsyncSession, project: Project):
    record = _record(project.id)
    db_session.add(record)
    await db_session.flush()
    item = DecisionItem(
        decision_id=record.id,
        candidate_id="cand_1",
        verdict="SELECTED",
        snapshot_score=-9.1,
        snapshot_rank=1,
        snapshot_attrs={"qed": 0.71},
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    await db_session.delete(item)
    with pytest.raises(ImmutableRecordError):
        await db_session.commit()
    await db_session.rollback()


def test_decision_item_candidate_id_is_required() -> None:
    """``UniqueConstraint(decision_id, candidate_id)`` 不约束 NULL。

    PostgreSQL 上多行 NULL 互不冲突，允许空值等于允许「没有候选物的快照行」——
    ``docs/04`` §9.5 该列是 uuid，所以模型层必须 ``nullable=False``。
    """
    assert DecisionItem.__table__.c.candidate_id.nullable is False


def test_decision_indexes_are_declared_once() -> None:
    """索引只在 ``__table_args__`` 声明，避免 ``create_all`` 与 Alembic 漂移。"""
    column_level = {
        column.name
        for table in (DecisionRecord.__table__, DecisionItem.__table__)
        for column in table.columns
        if column.index
    }
    assert column_level == set()

    names = {index.name for index in DecisionRecord.__table__.indexes}
    assert names == {
        "ix_decision_records_project_point",
        "ix_decision_records_project_decided",
        "ix_decision_records_subject_id",
    }
