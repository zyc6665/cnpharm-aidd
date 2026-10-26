"""决策记录与研发阶段 API 测试（docs/05 §3.2、§3.3，docs/03 §3.6）。

九个基础用例对应计划 §3 Task 2 Step 1，另加阶段推导与 review 回归用例：
阶段是纯推导，不写库，所以只断言「当前阶段 + 缺口顺序」，不依赖任何状态字段。

review 回归（B1/B2/B4/S1/S2/S12）各有用例守着——这几条一旦回退都是**只追加表里
不可纠正**的数据缺陷，靠人读代码发现不了。
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
from app.models.tasks import Task, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.traceability import AuditLog, ImmutableRecordError  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services.audit_sink import event_to_row  # noqa: E402

OWNER = "owner"
RUNNER = "runner"
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
        RUNNER: await _create_user(db_session, "runner@example.com"),
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
    for key, role in ((OWNER, "owner"), (RUNNER, "runner"), (VIEWER, "viewer")):
        db_session.add(
            ProjectMember(project_id=project.id, user_id=users[key].id, role=role)
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
    # 存在于项目、但不属于该集合的候选物 —— 集合成员归属校验的反例。
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


async def _register_tool(db: AsyncSession, *, slug: str, owner_id: str) -> Tool:
    tool = Tool(
        owner_id=owner_id,
        name=slug,
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(
        tool_id=tool.id, version="1.0.0", config={"type": "python_script"}, is_active=True
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    await db.commit()
    await db.refresh(tool)
    return tool


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
async def test_snapshot_row_without_verdict_is_rejected(
    api_client: httpx.AsyncClient,
    project: Project,
    candidate_set: CandidateSet,
):
    """B1 反向：快照里有、结论里没有的行没有 ``verdict`` 可落，必须拒绝。"""
    payload = _payload(
        candidate_set.id,
        selectedIds=["cand_a"],
        excludedIds=["cand_b"],
        snapshot=[
            {"candidateId": "cand_a", "score": -9.1, "rank": 1},
            {"candidateId": "cand_b", "score": -8.2, "rank": 2},
            {"candidateId": "cand_outside", "score": -7.5, "rank": 3},
        ],
    )

    response = await _post_decision(api_client, project.id, payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_partial_snapshot_backfills_missing_score(
    api_client: httpx.AsyncClient,
    project: Project,
    candidate_set: CandidateSet,
):
    """B1：快照只覆盖部分成员时，缺失的结论补 ``score=None`` 行而不是被静默丢弃。

    只追加表一旦写入就无法纠正，所以「返回的结论 == 提交的结论」必须由行数保证。
    """
    payload = _payload(
        candidate_set.id,
        selectedIds=["cand_a"],
        excludedIds=["cand_b"],
        snapshot=[{"candidateId": "cand_a", "score": -9.1, "rank": 1}],
    )

    response = await _post_decision(api_client, project.id, payload)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data["items"]) == 2
    assert data["selected_ids"] == ["cand_a"]
    assert data["excluded_ids"] == ["cand_b"]

    by_id = {item["candidate_id"]: item for item in data["items"]}
    assert by_id["cand_a"]["snapshot_score"] == -9.1
    assert by_id["cand_a"]["snapshot_attrs"] == {}
    assert by_id["cand_b"]["snapshot_score"] is None
    assert by_id["cand_b"]["snapshot_rank"] is None
    assert by_id["cand_b"]["snapshot_attrs"] == {"score_source": "missing"}


@pytest.mark.asyncio
async def test_runner_cannot_create_decision(
    api_client: httpx.AsyncClient,
    project: Project,
    candidate_set: CandidateSet,
):
    """B2：``runner`` 低于 ``editor``（见 ``domain_compounds.WRITE_ROLES``）。"""
    response = await _post_decision(
        api_client, project.id, _payload(candidate_set.id), user=RUNNER
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_target_decision_rejects_candidate_from_other_project(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    """B4：非 CANDIDATE_SET 时快照里的候选物也必须属于本项目。"""
    other_org = Organization(name="Other Lab", slug="other-lab")
    db_session.add(other_org)
    await db_session.flush()
    other_project = Project(
        organization_id=other_org.id,
        created_by=users[OUTSIDER].id,
        name="Other program",
        status="active",
    )
    db_session.add(other_project)
    await db_session.flush()
    db_session.add(
        Candidate(
            id="cand_foreign",
            project_id=other_project.id,
            created_by=users[OUTSIDER].id,
            candidate_type="PEPTIDE",
            peptide_sequence="AAAA",
        )
    )
    target = Target(project_id=project.id, created_by=users[OWNER].id, name="EGFR")
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(target)

    payload = _payload(
        target.id,
        subjectType="TARGET",
        subjectId=target.id,
        decisionPoint="DP1",
        selectedIds=["cand_foreign"],
        excludedIds=[],
        snapshot=[{"candidateId": "cand_foreign", "score": -9.1, "rank": 1}],
    )

    response = await _post_decision(api_client, project.id, payload)

    assert response.status_code == 422, response.text
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
    # S2：``audit_logs.actor`` 取 ``event.user_email``，不是用户 UUID（docs/04 §3 note 1）。
    # 事件经脱敏器处理后邮箱会被掩码，但绝不会退化成 UUID。
    assert event.user_email
    assert "@" in event.user_email
    assert event.user_email != str(project.created_by)

    # 事件必须能落进 audit_logs（action 入库时统一大写，见 audit_sink.event_to_row）。
    row = event_to_row(event)
    assert row["actor"] == event.user_email
    assert row["actor"] != str(project.created_by)
    db_session.add(AuditLog(**row))
    await db_session.commit()
    rows = (await db_session.execute(select(AuditLog))).scalars().all()
    assert [stored.action for stored in rows] == ["DECISION_CREATE"]
    assert [stored.resource_type for stored in rows] == ["DECISION_RECORD"]


@pytest.mark.asyncio
async def test_audit_failure_does_not_block_decision(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    candidate_set: CandidateSet,
    monkeypatch,
):
    """S1：数据已提交后审计失败不能变成 500（docs/04 §3.2.2 最终一致）。"""
    audit_logger = get_audit_logger()

    def explode(_event):
        raise RuntimeError("audit sink is down")

    monkeypatch.setattr(audit_logger, "enable_file_logging", False)
    monkeypatch.setattr(audit_logger, "enable_db_logging", True)
    monkeypatch.setattr(audit_logger, "_db_writer", explode)

    response = await _post_decision(api_client, project.id, _payload(candidate_set.id))

    assert response.status_code == 200, response.text
    stored = (
        await db_session.execute(select(DecisionRecord))
    ).scalars().all()
    assert len(stored) == 1


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
    # B3：``gaps`` 是四键结构，``link`` 指向 docs/06 的页面路由。
    assert set(data["gaps"][0]) == {"code", "message", "action", "link"}
    assert data["gaps"][0]["link"] == f"/projects/{project.id}/targets"


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
    assert data["gaps"][0]["link"] == "/tasks"


@pytest.mark.asyncio
async def test_stage_reaches_s4_when_only_task_is_queued(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    """排队中的任务也算「已提交」：S4 + 无 ``NO_TASK`` 缺口。

    任务刚提交完还没轮到执行时状态是 ``QUEUED``。如果 ``SUBMITTED_STATUSES``
    不含它，项目会掉回 S3 并报 ``NO_TASK``——等于告诉用户「你还没提交过任务」，
    而任务明明在队列里。
    """
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
    tool = await _register_tool(db_session, slug="queued-only", owner_id=users[OWNER].id)
    db_session.add(
        Task(
            user_id=users[OWNER].id,
            tool_id=tool.id,
            tool_version_id=tool.current_version_id,
            status=TaskStatus.QUEUED.value,
            extra_data={"project_id": project.id},
        )
    )
    await db_session.commit()

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/stage", headers=_headers(VIEWER)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["currentStage"] == "S4"
    assert data["reachedStages"] == ["S0", "S1", "S2", "S3", "S4"]
    assert data["nextStage"] == "S5"
    # 排队中的任务计入 submitted，但还没有结果可看，所以 S5 未达成。
    assert data["counters"]["submitted_tasks"] == 1
    assert data["counters"]["finished_tasks"] == 0
    assert "NO_TASK" not in [gap["code"] for gap in data["gaps"]]


@pytest.mark.asyncio
async def test_stage_reaches_s6_after_first_decision(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    """S12：S5（有成功任务）之上补 S6「至少 1 条决策记录」。"""
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
    tool = await _register_tool(db_session, slug="boltz-2", owner_id=users[OWNER].id)
    db_session.add(
        Task(
            user_id=users[OWNER].id,
            tool_id=tool.id,
            tool_version_id=tool.current_version_id,
            status=TaskStatus.SUCCESS.value,
            extra_data={"project_id": project.id},
        )
    )
    await db_session.commit()

    before = await api_client.get(
        f"/api/v1/projects/{project.id}/stage", headers=_headers(VIEWER)
    )
    assert before.status_code == 200, before.text
    before_data = before.json()["data"]
    assert before_data["currentStage"] == "S5"
    assert before_data["nextStage"] == "S6"
    assert [gap["code"] for gap in before_data["gaps"]] == ["NO_DECISION"]
    assert before_data["gaps"][0]["link"] == f"/projects/{project.id}/decisions"

    db_session.add(
        DecisionRecord(
            project_id=project.id,
            decision_point="DP5",
            subject_type="TARGET",
            subject_id=target.id,
            reason="推进到实验验证",
            basis_task_ids=[],
            basis_metrics={},
            decided_by="owner@example.com",
            decided_at=utcnow(),
        )
    )
    await db_session.commit()

    after = await api_client.get(
        f"/api/v1/projects/{project.id}/stage", headers=_headers(VIEWER)
    )
    assert after.status_code == 200, after.text
    after_data = after.json()["data"]
    assert after_data["currentStage"] == "S6"
    assert after_data["stageName"] == "决策与归档"
    assert after_data["reachedStages"] == ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]
    # S6 是终点：没有「下一阶段」可提示。
    assert after_data["nextStage"] is None
    assert after_data["gaps"] == []
