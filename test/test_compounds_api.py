"""Compound / candidate / candidate set API tests (docs/01 M1, M3; docs/05 §4, §5).

用例分组与验收条款对应：

* 化合物导入与去重 —— M1-FR-03、M1-BR-1、M1-BR-2（异常清单不阻断整批）
* 指纹与相似性检索 —— docs/04 §5.7
* 候选物 —— M3-FR-01/02/08
* 候选集与乐观锁 —— docs/04 §5.6、M6-BR-3
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
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.files.writer import store_file_bytes  # noqa: E402
from app.main import app  # noqa: E402
from app.models.compounds import (  # noqa: E402
    Candidate,
    CandidateSet,
    CandidateSetItem,
    Compound,
    MoleculeFingerprint,
)
from app.models.files import FileSourceType  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402

OWNER = "owner"
VIEWER = "viewer"
OUTSIDER = "outsider"
ADMIN = "admin"

#: 三条小分子与一条重复（同一 InChIKey 的另一写法）。
SMILES_CSV = "name,smiles\nethanol,CCO\nethane,CC\npropane,CCC\nethanol-dup,OCC\n"
SMILES_LIST = "CCO ethanol\nCC ethane\nnot-a-smiles broken\n"


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


async def _create_user(
    db: AsyncSession, email: str, *, role: str = UserRole.USER.value
) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        display_name=email.split("@")[0],
        role=role,
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
        ADMIN: await _create_user(
            db_session, "admin@example.com", role=UserRole.ADMIN.value
        ),
    }


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    organization = Organization(name="Molecule Lab", slug="molecule-lab")
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


async def _upload(
    db: AsyncSession,
    *,
    project_id: str,
    owner_id: str,
    filename: str,
    content: bytes,
):
    record = await store_file_bytes(
        db,
        content=content,
        filename=filename,
        content_type="text/csv",
        source_type=FileSourceType.USER_INPUT,
        owner_id=owner_id,
        project_id=project_id,
    )
    await db.commit()
    return record


async def _import_csv(
    client: httpx.AsyncClient,
    db: AsyncSession,
    *,
    project_id: str,
    owner_id: str,
    filename: str = "molecules.csv",
    content: bytes = SMILES_CSV.encode("utf-8"),
    **overrides,
) -> dict:
    record = await _upload(
        db, project_id=project_id, owner_id=owner_id, filename=filename, content=content
    )
    payload = {"file_id": record.id}
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/projects/{project_id}/compounds:import",
        headers=_headers(OWNER),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _create_candidate(
    client: httpx.AsyncClient, project_id: str, *, user: str = OWNER, **overrides
) -> dict:
    payload = {"smiles": "CCO", "name": "ethanol"}
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/projects/{project_id}/candidates",
        headers=_headers(user),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _create_set(client: httpx.AsyncClient, project_id: str, **overrides) -> dict:
    payload = {"name": "设计候选集 A"}
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/projects/{project_id}/candidate-sets",
        headers=_headers(OWNER),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _make_project(db: AsyncSession, *, name: str, owner: User) -> Project:
    """建一个项目并把 ``owner`` 设为项目 owner（用于跨项目可见性用例）。"""
    organization = Organization(name=f"{name} org", slug=f"{name}-org")
    db.add(organization)
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name=name,
        status="active",
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    await db.commit()
    await db.refresh(project)
    return project


# ---------------------------------------------------------------------------
# Compound import (M1-FR-03, M1-BR-1, M1-BR-2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_csv_dedupes_by_inchikey(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
):
    """同一 InChIKey 的两种 SMILES 写法只落一条化合物（M1-BR-1）。"""
    data = await _import_csv(
        api_client, db_session, project_id=project.id, owner_id=users[OWNER].id
    )
    summary = data["summary"]
    assert summary["total"] == 4
    assert summary["created_compounds"] == 3
    assert summary["duplicate"] == 1
    assert summary["failed"] == 0

    result = await db_session.execute(select(Compound))
    assert len(result.scalars().all()) == 3


@pytest.mark.asyncio
async def test_import_reports_bad_rows_without_aborting(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
):
    """解析失败进异常清单且不阻断整批（M1-BR-2）。"""
    data = await _import_csv(
        api_client,
        db_session,
        project_id=project.id,
        owner_id=users[OWNER].id,
        filename="molecules.smi",
        content=SMILES_LIST.encode("utf-8"),
    )
    summary = data["summary"]
    assert summary["total"] == 3
    assert summary["success"] == 2
    assert summary["failed"] == 1
    assert data["errors"][0]["row"] == 3
    assert "SMILES 无法解析" in data["errors"][0]["message"]


@pytest.mark.asyncio
async def test_import_accepts_sdf_records(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
):
    """SDF 按记录块解析（M1-FR-03 支持 .sdf）。"""
    sdf = (
        "ethanol\n     RDKit          3D\n\n"
        "  3  2  0  0  0  0  0  0  0  0999 V2000\n"
        "   -1.2000    0.3000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "    0.0000   -0.6000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "    1.2000    0.3000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "  1  2  1  0\n  2  3  1  0\nM  END\n$$$$\n"
    )
    data = await _import_csv(
        api_client,
        db_session,
        project_id=project.id,
        owner_id=users[OWNER].id,
        filename="library.sdf",
        content=sdf.encode("utf-8"),
    )
    assert data["summary"]["total"] == 1
    assert data["summary"]["success"] == 1


@pytest.mark.asyncio
async def test_import_rejects_missing_smiles_column(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
):
    record = await _upload(
        db_session,
        project_id=project.id,
        owner_id=users[OWNER].id,
        filename="bad.csv",
        content=b"name,formula\nethanol,C2H6O\n",
    )
    response = await api_client.post(
        f"/api/v1/projects/{project.id}/compounds:import",
        headers=_headers(OWNER),
        json={"file_id": record.id},
    )
    assert response.status_code == 422
    assert "SMILES" in response.json()["message"]


@pytest.mark.asyncio
async def test_viewer_cannot_import_compounds(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
):
    record = await _upload(
        db_session,
        project_id=project.id,
        owner_id=users[OWNER].id,
        filename="molecules.csv",
        content=SMILES_CSV.encode("utf-8"),
    )
    response = await api_client.post(
        f"/api/v1/projects/{project.id}/compounds:import",
        headers=_headers(VIEWER),
        json={"file_id": record.id},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_outsider_cannot_list_compounds(
    api_client: httpx.AsyncClient, project: Project
):
    response = await api_client.get(
        f"/api/v1/projects/{project.id}/compounds", headers=_headers(OUTSIDER)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Compounds (docs/04 §7.1, §5.7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_compound_computes_descriptors(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
):
    response = await api_client.post(
        f"/api/v1/projects/{project.id}/compounds",
        headers=_headers(OWNER),
        json={"smiles": "CCO", "name": "ethanol"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["inchikey"] == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    assert data["mol_formula"] == "C2H6O"
    assert data["mol_weight"] == pytest.approx(46.069)
    assert data["props"]["QED"] > 0


@pytest.mark.asyncio
async def test_create_compound_reuses_existing_row(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
):
    first = await api_client.post(
        f"/api/v1/projects/{project.id}/compounds",
        headers=_headers(OWNER),
        json={"smiles": "CCO"},
    )
    second = await api_client.post(
        f"/api/v1/projects/{project.id}/compounds",
        headers=_headers(OWNER),
        json={"smiles": "OCC"},
    )
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert "已存在" in second.json()["message"]


@pytest.mark.asyncio
async def test_compound_list_only_shows_referenced_molecules(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
):
    """项目化合物视图只列被本项目候选物引用的分子（docs/06 P-12）。"""
    await _create_candidate(api_client, project.id, smiles="CCO")
    response = await api_client.get(
        f"/api/v1/projects/{project.id}/compounds", headers=_headers(OWNER)
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["inchikey"] == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


@pytest.mark.asyncio
async def test_similarity_search_ranks_self_first(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
):
    for smiles in ("CCO", "CCN", "c1ccccc1"):
        await _create_candidate(api_client, project.id, smiles=smiles)
    response = await api_client.post(
        "/api/v1/compounds:search",
        headers=_headers(OWNER),
        params={"limit": 5},
        json={"smiles": "CCO"},
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert items[0]["similarity"] == 1.0
    assert items[0]["compound"]["inchikey"] == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    assert items[0]["similarity"] >= items[-1]["similarity"]


@pytest.mark.asyncio
async def test_similarity_search_only_returns_own_project_compounds(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
):
    """普通用户只能搜到自己项目引用的化合物，搜不到其他项目的（P1-1 跨租户泄露修复）。"""
    await _create_candidate(api_client, project.id, smiles="CCO")

    other_project = await _make_project(
        db_session, name="outsider-program", owner=users[OUTSIDER]
    )
    await _create_candidate(api_client, other_project.id, smiles="CCN", user=OUTSIDER)

    response = await api_client.post(
        "/api/v1/compounds:search",
        headers=_headers(OWNER),
        params={"limit": 20},
        json={"smiles": "CCO"},
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["compound"]["inchikey"] == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


@pytest.mark.asyncio
async def test_similarity_search_returns_empty_without_references(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
):
    """无任何项目引用的用户检索返回空列表（而不是全表放行）。"""
    await _create_candidate(api_client, project.id, smiles="CCO")

    response = await api_client.post(
        "/api/v1/compounds:search",
        headers=_headers(OUTSIDER),
        params={"limit": 20},
        json={"smiles": "CCO"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_similarity_search_admin_sees_all_compounds(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
):
    """管理员按平台主数据口径可搜到全量化合物。"""
    await _create_candidate(api_client, project.id, smiles="CCO")

    other_project = await _make_project(
        db_session, name="outsider-program", owner=users[OUTSIDER]
    )
    await _create_candidate(api_client, other_project.id, smiles="CCN", user=OUTSIDER)

    response = await api_client.post(
        "/api/v1/compounds:search",
        headers=_headers(ADMIN),
        params={"limit": 20},
        json={"smiles": "CCO"},
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert len(items) == 2
    inchikeys = {item["compound"]["inchikey"] for item in items}
    assert "LFQSCWFLJHTTHZ-UHFFFAOYSA-N" in inchikeys


# ---------------------------------------------------------------------------
# Candidates (M3-FR-01, M3-FR-02, M3-FR-08)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_small_molecule_candidate(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
):
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    assert candidate["candidate_type"] == "SMALL_MOLECULE"
    assert candidate["compound"]["inchikey"] == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    assert candidate["compound"]["props"]["logP"] is not None


@pytest.mark.asyncio
async def test_create_peptide_candidate(api_client: httpx.AsyncClient, project: Project):
    candidate = await _create_candidate(
        api_client,
        project.id,
        candidate_type="PEPTIDE",
        smiles=None,
        peptide_sequence="ACDEFGHIK",
        name="peptide-1",
    )
    assert candidate["candidate_type"] == "PEPTIDE"
    assert candidate["compound_id"] is None
    assert candidate["peptide_sequence"] == "ACDEFGHIK"


@pytest.mark.asyncio
async def test_peptide_candidate_requires_sequence(
    api_client: httpx.AsyncClient, project: Project
):
    response = await api_client.post(
        f"/api/v1/projects/{project.id}/candidates",
        headers=_headers(OWNER),
        json={"candidate_type": "PEPTIDE", "peptide_sequence": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_candidates_returns_property_matrix(
    api_client: httpx.AsyncClient, project: Project
):
    ids = []
    for smiles in ("CCO", "CCN", "c1ccccc1"):
        candidate = await _create_candidate(api_client, project.id, smiles=smiles)
        ids.append(candidate["id"])

    response = await api_client.post(
        "/api/v1/candidates:compare",
        headers=_headers(OWNER),
        params={"project_id": project.id},
        json={"candidateIds": ids},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["count"] == 3
    assert [row["id"] for row in data["items"]] == ids
    for row in data["items"]:
        for key in ("mol_weight", "logP", "QED", "TPSA"):
            assert key in row


@pytest.mark.asyncio
async def test_compare_rejects_more_than_six(api_client: httpx.AsyncClient, project: Project):
    response = await api_client.post(
        "/api/v1/candidates:compare",
        headers=_headers(OWNER),
        params={"project_id": project.id},
        json={"candidateIds": [f"c{i}" for i in range(7)]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_candidate_fingerprint_is_cached(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
):
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    first = await api_client.post(
        f"/api/v1/candidates/{candidate['id']}/fingerprint", headers=_headers(OWNER)
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["ecfp4_bytes"] == 256
    assert first.json()["data"]["maccs_bytes"] == 21

    result = await db_session.execute(select(MoleculeFingerprint))
    rows = result.scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_peptide_candidate_has_no_fingerprint(
    api_client: httpx.AsyncClient, project: Project
):
    candidate = await _create_candidate(
        api_client,
        project.id,
        candidate_type="PEPTIDE",
        smiles=None,
        peptide_sequence="ACDEF",
    )
    response = await api_client.post(
        f"/api/v1/candidates/{candidate['id']}/fingerprint", headers=_headers(OWNER)
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_candidate_quota_is_enforced(
    api_client: httpx.AsyncClient, project: Project, monkeypatch
):
    from app.services import domain_compounds

    monkeypatch.setattr(domain_compounds.settings, "MAX_PROJECT_CANDIDATES", 1, raising=False)
    await _create_candidate(api_client, project.id, smiles="CCO")
    response = await api_client.post(
        f"/api/v1/projects/{project.id}/candidates",
        headers=_headers(OWNER),
        json={"smiles": "CCN"},
    )
    assert response.status_code == 429


# ---------------------------------------------------------------------------
# Candidate sets (docs/04 §7.3, §5.6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_set_items_is_idempotent(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
):
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    candidate_set = await _create_set(api_client, project.id)

    first = await api_client.post(
        f"/api/v1/candidate-sets/{candidate_set['id']}/items",
        headers=_headers(OWNER),
        json={"candidate_ids": [candidate["id"]]},
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["inserted"] == 1
    assert first.json()["data"]["candidate_set"]["item_count"] == 1

    second = await api_client.post(
        f"/api/v1/candidate-sets/{candidate_set['id']}/items",
        headers=_headers(OWNER),
        json={"candidate_ids": [candidate["id"]]},
    )
    assert second.json()["data"]["inserted"] == 0
    assert second.json()["data"]["skipped"] == 1

    result = await db_session.execute(select(CandidateSetItem))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_set_items_keep_insertion_order_and_snapshot(
    api_client: httpx.AsyncClient, project: Project
):
    first = await _create_candidate(api_client, project.id, smiles="CCO", design_score=0.9)
    second = await _create_candidate(api_client, project.id, smiles="CCN", design_score=0.5)
    candidate_set = await _create_set(api_client, project.id)
    await api_client.post(
        f"/api/v1/candidate-sets/{candidate_set['id']}/items",
        headers=_headers(OWNER),
        json={"candidate_ids": [second["id"], first["id"]]},
    )
    response = await api_client.get(
        f"/api/v1/candidate-sets/{candidate_set['id']}/items", headers=_headers(OWNER)
    )
    items = response.json()["data"]["items"]
    assert [item["candidate_id"] for item in items] == [second["id"], first["id"]]
    assert items[0]["snapshot_score"] == pytest.approx(0.5)
    assert items[1]["snapshot_score"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_update_set_requires_matching_version(
    api_client: httpx.AsyncClient, project: Project
):
    candidate_set = await _create_set(api_client, project.id)
    assert candidate_set["version"] == 1

    ok = await api_client.put(
        f"/api/v1/candidate-sets/{candidate_set['id']}",
        headers=_headers(OWNER),
        json={"name": "重命名", "version": 1},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["version"] == 2

    stale = await api_client.put(
        f"/api/v1/candidate-sets/{candidate_set['id']}",
        headers=_headers(OWNER),
        json={"name": "再次重命名", "version": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["currentVersion"] == 2


@pytest.mark.asyncio
async def test_candidate_set_item_removal_decrements_count(
    api_client: httpx.AsyncClient, project: Project
):
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    candidate_set = await _create_set(api_client, project.id)
    await api_client.post(
        f"/api/v1/candidate-sets/{candidate_set['id']}/items",
        headers=_headers(OWNER),
        json={"candidate_ids": [candidate["id"]]},
    )
    listing = await api_client.get(
        f"/api/v1/candidate-sets/{candidate_set['id']}/items", headers=_headers(OWNER)
    )
    item_id = listing.json()["data"]["items"][0]["id"]

    response = await api_client.delete(
        f"/api/v1/candidate-sets/{candidate_set['id']}/items/{item_id}",
        headers=_headers(OWNER),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["candidate_set"]["item_count"] == 0


@pytest.mark.asyncio
async def test_export_set_returns_csv(
    api_client: httpx.AsyncClient, project: Project
):
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    candidate_set = await _create_set(api_client, project.id)
    await api_client.post(
        f"/api/v1/candidate-sets/{candidate_set['id']}/items",
        headers=_headers(OWNER),
        json={"candidate_ids": [candidate["id"]]},
    )
    response = await api_client.post(
        f"/api/v1/candidate-sets/{candidate_set['id']}:export", headers=_headers(OWNER)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["row_count"] == 1
    assert data["format"] == "csv"
    content = data["content"]
    if content is None:
        # 落盘成功时给下载链接而不是内容
        assert data["download_url"]
    else:
        header = content.splitlines()[0]
        assert "inchikey" in header
        assert "LFQSCWFLJHTTHZ-UHFFFAOYSA-N" in content


@pytest.mark.asyncio
async def test_delete_set_is_soft(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
):
    candidate_set = await _create_set(api_client, project.id)
    response = await api_client.delete(
        f"/api/v1/candidate-sets/{candidate_set['id']}", headers=_headers(OWNER)
    )
    assert response.status_code == 200
    assert response.json()["data"]["is_archived"] is True

    listing = await api_client.get(
        f"/api/v1/projects/{project.id}/candidate-sets", headers=_headers(OWNER)
    )
    assert listing.json()["data"]["items"] == []

    result = await db_session.execute(select(CandidateSet))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_project_overview_counts_include_candidates(
    api_client: httpx.AsyncClient, project: Project
):
    await _create_candidate(api_client, project.id, smiles="CCO")
    await _create_set(api_client, project.id)
    response = await api_client.get(
        f"/api/v1/projects/{project.id}/overview", headers=_headers(OWNER)
    )
    counts = response.json()["data"]["counts"]
    assert counts["candidates"] == 1
    assert counts["candidate_sets"] == 1


@pytest.mark.asyncio
async def test_delete_project_cascades_compound_rows(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
):
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    candidate_set = await _create_set(api_client, project.id)
    await api_client.post(
        f"/api/v1/candidate-sets/{candidate_set['id']}/items",
        headers=_headers(OWNER),
        json={"candidate_ids": [candidate["id"]]},
    )

    response = await api_client.delete(
        f"/api/v1/projects/{project.id}", headers=_headers(OWNER)
    )
    assert response.status_code == 200, response.text

    for model in (Candidate, CandidateSet, CandidateSetItem):
        result = await db_session.execute(select(model))
        assert result.scalars().all() == []
    # 化合物是全局主数据，不随项目删除（docs/04 §7.1）
    compounds = await db_session.execute(select(Compound))
    assert len(compounds.scalars().all()) == 1
