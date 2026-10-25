"""决策记录与研发阶段 API 测试（docs/05 §3.2、§3.3，docs/03 §3.6）。

九个用例对应计划 §3 Task 2 Step 1，另加两个阶段推导用例：阶段是纯推导，不写库，
所以只断言「当前阶段 + 缺口顺序」，不依赖任何状态字段。
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import get_current_user  # noqa: E402
from app.common.time import utcnow  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.logging.audit import (  # noqa: E402
    AuditAction,
    ResourceType,
    get_audit_logger,
)
from app.main import app  # noqa: E402
from app.models.compounds import Candidate, CandidateSet, CandidateSetItem  # noqa: E402
from app.models.decisions import DecisionItem, DecisionRecord  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.targets import Pocket, Protein, ProteinStructure, Target  # noqa: E402
from app.models.traceability import AuditLog, ImmutableRecordError  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services.audit_sink import event_to_row  # noqa: E402

OWNER = "owner"
VIEWER = "viewer"
OUTSIDER = "outsider"


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


async def _create_user(db: AsyncSession, email: str) -> User:
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
async def users(db_session: AsyncSession) -> dict[str, User]:
    return {
        OWNER: await _create_user(db_session, "owner@example.com"),
        VIEWER: await _create_user(db_session, "viewer@example.com"),
        OUTSIDER: await _create_user(db_session, "outsider@example.com"),
    }


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    organization = Organization(name="Decision Lab", slug="decision-lab")
    db_session.add(organization)
    await db_session.flush()
    project = Project(
        organization_id=organization.id,
        created_by=users[OWNER].id,
        name="EGFR program",
        status="active",
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(
        ProjectMember(project_id=project.id, user_id=users[OWNER].id, role="owner")
    )
    db_session.add(
        ProjectMember(project_id=project.id, user_id=users[VIEWER].id, role="viewer")
    )
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def candidate_set(
    db_session: AsyncSession, project: Project, users: dict[str, User]
) -> CandidateSet:
    """两个候选物的集合：``snapshot`` 里混入第三个候选物即触发归属校验。"""
    candidate_set = CandidateSet(
        project_id=project.id,
        created_by=users[OWNER].id,
        name="EGFR hits",
        item_count=2,
    )
    db_session.add(candidate_set)
    await db_session.flush()
    for index, cand_id in enumerate(("cand_a", "cand_b"), start=1):
        candidate = Candidate(
            id=cand_id,
            project_id=project.id,
            created_by=users[OWNER].id,
            candidate_type="PEPTIDE",
            peptide_sequence="MEEPQSDVRKC",
            name=f"design-{index}",
            design_score=-9.0 + index,
        )
        db_session.add(candidate)
        await db_session.flush()
        db_session.add(
            CandidateSetItem(
                set_id=candidate_set.id,
                candidate_id=candidate.id,
                ordinal=index,
                snapshot_score=candidate.design_score,
            )
        )
    # 存在于项目、但不属于该集合的候选物 —— 归属校验的反例。
    db_session.add(
        Candidate(
            id="cand_outside",
            project_id=project.id,
            created_by=users[OWNER].id,
            candidate_type="PEPTIDE",
            peptide_sequence="GGGGS",
            name="outside",
        )
    )
    await db_session.commit()
    await db_session.refresh(candidate_set)
    return candidate_set


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, users: dict[str, User]):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in users:
            return users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
    app.dependency_overrides.clear()


def _headers(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user}"}


def _payload(candidate_set_id: str = "set_1", **overrides) -> dict:
    """docs/05 §3.3 的请求体，字段名用 camelCase 以证明别名生效。"""
    payload = {
        "decisionPoint": "DP3",
        "subjectType": "CANDIDATE_SET",
        "subjectId": candidate_set_id,
        "selectedIds": ["cand_a"],
        "excludedIds": ["cand_b"],
        "basisTaskIds": ["tsk_1", "tsk_2"],
        "basisMetrics": {"avgDockingScore": -8.2, "admetPassRate": 0.73},
        "reason": "亲和力与成药性均达标，且骨架多样性好",
        "snapshot": [
            {"candidateId": "cand_a", "score": -9.1, "rank": 1},
            {"candidateId": "cand_b", "score": -8.2, "rank": 2},
        ],
    }
    payload.update(overrides)
    return payload


async def _post_decision(client: httpx.AsyncClient, project_id: str, payload: dict, user: str = OWNER):
    return await client.post(
        f"/api/v1/projects/{project_id}/decisions",
        headers=_headers(user),
        json=payload,
    )


@pytest.mark.asyncio
async def test_owner_creates_candidate_set_decision(
    api_client: httpx.AsyncClient,
    project: Project,
    candidate_set: CandidateSet,
):
    response = await _post_decision(
        api_client, project.id, _payload(candidate_set.id)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["id"]
    assert data["created_at"]
    assert data["decision_point"] == "DP3"
    assert data["subject_type"] == "CANDIDATE_SET"
    assert [item["verdict"] for item in data["items"]] == ["SELECTED", "EXCLUDED"]
    assert data["items"][0]["snapshot_score"] == -9.1
    assert data["items"][0]["snapshot_rank"] == 1


@pytest.mark.asyncio
async def test_snapshot_member_from_other_set_is_rejected(
    api_client: httpx.AsyncClient,
    project: Project,
    candidate_set: CandidateSet,
):
    payload = _payload(
        candidate_set.id,
        selectedIds=["cand_a", "cand_outside"],
        excludedIds=["cand_b"],
        snapshot=[
            {"candidateId": "cand_a", "score": -9.1, "rank": 1},
            {"candidateId": "cand_outside", "score": -7.5, "rank": 2},
            {"candidateId": "cand_b", "score": -8.2, "rank": 3},
        ],
    )

    response = await _post_decision(api_client, project.id, payload)

    assert response.status_code == 422
    assert "不属于" in response.json()["message"]


@pytest.mark.asyncio
async def test_viewer_cannot_create_decision(
    api_client: httpx.AsyncClient,
    project: Project,
    candidate_set: CandidateSet,
):
    response = await _post_decision(
        api_client, project.id, _payload(candidate_set.id), user=VIEWER
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_member_gets_project_not_found(
    api_client: httpx.AsyncClient,
    project: Project,
    candidate_set: CandidateSet,
):
    response = await _post_decision(
        api_client, project.id, _payload(candidate_set.id), user=OUTSIDER
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "研究项目不存在"


@pytest.mark.asyncio
async def test_blank_reason_is_rejected(
    api_client: httpx.AsyncClient,
    project: Project,
    candidate_set: CandidateSet,
):
    response = await _post_decision(
        api_client, project.id, _payload(candidate_set.id, reason="   ")
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_decision_without_any_verdict_is_rejected(
    api_client: httpx.AsyncClient,
    project: Project,
    candidate_set: CandidateSet,
):
    payload = _payload(
        candidate_set.id,
        selectedIds=[],
        excludedIds=[],
        snapshot=[],
    )

    response = await _post_decision(api_client, project.id, payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_decision_writes_audit_log(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    candidate_set: CandidateSet,
    monkeypatch,
):
    """写决策必须同时追加审计事件（docs/04 §9.5 权限段最后一句）。"""
    events: list = []
    audit_logger = get_audit_logger()
    monkeypatch.setattr(audit_logger, "enable_file_logging", False)
    monkeypatch.setattr(audit_logger, "enable_db_logging", True)
    monkeypatch.setattr(audit_logger, "_db_writer", events.append)

    response = await _post_decision(api_client, project.id, _payload(candidate_set.id))
    assert response.status_code == 200, response.text

    decision_events = [event for event in events if event.action is AuditAction.DECISION_CREATE]
    assert len(decision_events) == 1
    event = decision_events[0]
    assert event.resource_type is ResourceType.DECISION_RECORD
    assert event.resource_id == response.json()["data"]["id"]
    assert event.user_id == str(project.created_by)

    # 事件必须能落进 audit_logs（action 入库时统一大写，见 audit_sink.event_to_row）。
    db_session.add(AuditLog(**event_to_row(event)))
    await db_session.commit()
    rows = (await db_session.execute(select(AuditLog))).scalars().all()
    assert [row.action for row in rows] == ["DECISION_CREATE"]
    assert [row.resource_type for row in rows] == ["DECISION_RECORD"]


@pytest.mark.asyncio
async def test_decision_list_is_paginated(
    api_client: httpx.AsyncClient,
    project: Project,
    candidate_set: CandidateSet,
):
    for reason in ("first", "second", "third"):
        response = await _post_decision(
            api_client,
            project.id,
            _payload(candidate_set.id, reason=f"理由：{reason}"),
        )
        assert response.status_code == 200, response.text

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/decisions?page=1&page_size=2",
        headers=_headers(VIEWER),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data["items"]) == 2
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2

    filtered = await api_client.get(
        f"/api/v1/projects/{project.id}/decisions?decision_point=DP4",
        headers=_headers(VIEWER),
    )
    assert filtered.status_code == 200
    assert filtered.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_decision_records_are_immutable(
    db_session: AsyncSession,
    project: Project,
    candidate_set: CandidateSet,
):
    record = DecisionRecord(
        project_id=project.id,
        decision_point="DP3",
        subject_type="CANDIDATE_SET",
        subject_id=candidate_set.id,
        reason="ok",
        basis_task_ids=[],
        basis_metrics={},
        decided_by="owner",
        decided_at=utcnow(),
    )
    db_session.add(record)
    await db_session.flush()
    db_session.add(
        DecisionItem(
            decision_id=record.id,
            candidate_id="cand_a",
            verdict="SELECTED",
            snapshot_score=-9.1,
            snapshot_rank=1,
            snapshot_attrs={},
        )
    )
    await db_session.commit()
    await db_session.refresh(record)
    record_id = record.id

    record.reason = "改主意了"
    with pytest.raises(ImmutableRecordError):
        await db_session.commit()
    await db_session.rollback()

    # rollback 会让 ORM 对象过期，重新取一次才能证明库里仍是原值。
    stored = (
        await db_session.execute(select(DecisionRecord).where(DecisionRecord.id == record_id))
    ).scalar_one()
    assert stored.reason == "ok"


@pytest.mark.asyncio
async def test_stage_starts_at_s0_with_gaps(
    api_client: httpx.AsyncClient,
    project: Project,
):
    response = await api_client.get(
        f"/api/v1/projects/{project.id}/stage", headers=_headers(VIEWER)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["currentStage"] == "S0"
    assert data["stageName"] == "立项与数据归集"
    assert data["reachedStages"] == ["S0"]
    assert data["nextStage"] == "S1"
    assert [gap["code"] for gap in data["gaps"]][0] == "NO_TARGET"
    assert set(data["gaps"][0]) == {"code", "message", "action"}


@pytest.mark.asyncio
async def test_stage_derives_s3_and_reports_missing_task(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    target = Target(project_id=project.id, created_by=users[OWNER].id, name="EGFR")
    db_session.add(target)
    await db_session.flush()
    protein = Protein(target_id=target.id, name="EGFR kinase", sequence="MEEP", seq_length=4)
    db_session.add(protein)
    await db_session.flush()
    structure = ProteinStructure(protein_id=protein.id, source_type="IMPORTED")
    db_session.add(structure)
    await db_session.flush()
    db_session.add(
        Pocket(structure_id=structure.id, rank=1, selected=True, residue_count=8)
    )
    db_session.add(
        Candidate(
            project_id=project.id,
            created_by=users[OWNER].id,
            candidate_type="PEPTIDE",
            peptide_sequence="MEEPQSDVRKC",
        )
    )
    await db_session.commit()

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/stage", headers=_headers(VIEWER)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["currentStage"] == "S3"
    assert data["reachedStages"] == ["S0", "S1", "S2", "S3"]
    assert data["nextStage"] == "S4"
    assert [gap["code"] for gap in data["gaps"]] == ["NO_TASK"]
