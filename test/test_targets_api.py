"""Targets / proteins / structures / pockets API tests (docs/01 M2, docs/05 §5)."""

from __future__ import annotations

import hashlib
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

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

from app.api.v1 import targets as targets_api  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.common.time import utcnow  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.files.writer import store_file_bytes  # noqa: E402
from app.logging.audit import AuditAction, ResourceType, get_audit_logger  # noqa: E402
from app.main import app  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.targets import Pocket, PocketResidue, Protein, ProteinStructure, Target  # noqa: E402
from app.models.tasks import Task  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services import domain_targets  # noqa: E402

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
    organization = Organization(name="Target Lab", slug="target-lab")
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
    content_type: str = "chemical/x-pdb",
):
    record = await store_file_bytes(
        db,
        content=content,
        filename=filename,
        content_type=content_type,
        source_type=FileSourceType.USER_INPUT,
        owner_id=owner_id,
        project_id=project_id,
    )
    await db.commit()
    return record


async def _create_target(client: httpx.AsyncClient, project_id: str, **overrides) -> dict:
    payload = {
        "name": "EGFR kinase domain",
        "uniprot_id": "P00533",
        "gene_name": "EGFR",
        "description": "L858R mutant construct",
    }
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/projects/{project_id}/targets",
        headers=_headers(OWNER),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _create_protein(client: httpx.AsyncClient, target_id: str, **overrides) -> dict:
    payload = {"name": "EGFR L858R", "sequence": "MEEP QSDV RKC"}
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/targets/{target_id}/proteins", headers=_headers(OWNER), json=payload
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _create_structure(
    client: httpx.AsyncClient, db: AsyncSession, protein_id: str, project_id: str, owner_id: str
) -> dict:
    record = await _upload(
        db,
        project_id=project_id,
        owner_id=owner_id,
        filename="1m17.pdb",
        content=b"ATOM      1  N   MET A   1      10.000  10.000  10.000  1.00 20.00           N\n",
    )
    response = await client.post(
        f"/api/v1/proteins/{protein_id}/structures:import",
        headers=_headers(OWNER),
        json={"file_id": record.id, "model_name": "crystal", "source_type": "IMPORTED"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _pocket_payload(rank: int = 1, **overrides) -> dict:
    payload = {
        "rank": rank,
        "score": 0.81,
        "volume": 423.5,
        "center_x": 12.5,
        "center_y": -3.25,
        "center_z": 30.75,
        "box_size_x": 20,
        "box_size_y": 20,
        "box_size_z": 20,
        "tool_name": "lvpocket",
        "tool_version": "1.0.0",
        "residues": [
            {"chain": "A", "residue_seq": 745, "residue_name": "LYS", "is_key": True, "contribution": 0.42},
            {"chain": "A", "residue_seq": 790, "residue_name": "THR", "is_key": False},
        ],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_creates_target_and_project_list_returns_it(
    api_client: httpx.AsyncClient, project: Project
):
    created = await _create_target(api_client, project.id)

    assert created["name"] == "EGFR kinase domain"
    assert created["target_type"] == "PROTEIN"
    assert created["project_id"] == project.id

    listing = await api_client.get(
        f"/api/v1/projects/{project.id}/targets", headers=_headers(VIEWER)
    )
    assert listing.status_code == 200
    body = listing.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_duplicate_target_name_is_rejected(
    api_client: httpx.AsyncClient, project: Project
):
    await _create_target(api_client, project.id)

    response = await api_client.post(
        f"/api/v1/projects/{project.id}/targets",
        headers=_headers(OWNER),
        json={"name": "EGFR kinase domain"},
    )

    assert response.status_code == 422
    assert "同名靶点" in response.json()["message"]


@pytest.mark.asyncio
async def test_viewer_cannot_create_target(api_client: httpx.AsyncClient, project: Project):
    response = await api_client.post(
        f"/api/v1/projects/{project.id}/targets",
        headers=_headers(VIEWER),
        json={"name": "Forbidden target"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_outsider_cannot_read_target(api_client: httpx.AsyncClient, project: Project):
    created = await _create_target(api_client, project.id)

    response = await api_client.get(
        f"/api/v1/targets/{created['id']}", headers=_headers(OUTSIDER)
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_target_update_and_delete_cascade(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users: dict[str, User]
):
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    structure = await _create_structure(
        api_client, db_session, protein["id"], project.id, users[OWNER].id
    )
    pocket_response = await api_client.post(
        f"/api/v1/structures/{structure['id']}/pockets",
        headers=_headers(OWNER),
        json=_pocket_payload(),
    )
    assert pocket_response.status_code == 200, pocket_response.text

    updated = await api_client.put(
        f"/api/v1/targets/{target['id']}",
        headers=_headers(OWNER),
        json={"gene_name": "ERBB1", "description": "updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["gene_name"] == "ERBB1"

    deleted = await api_client.delete(
        f"/api/v1/targets/{target['id']}", headers=_headers(OWNER)
    )
    assert deleted.status_code == 200

    for model, lookup in (
        (Target, "target"),
        (Protein, "protein"),
        (ProteinStructure, "structure"),
        (Pocket, "pocket"),
    ):
        remaining = (await db_session.execute(select(model))).scalars().all()
        assert remaining == [], f"{lookup} should be deleted with its target"
    assert (await db_session.execute(select(PocketResidue))).scalars().all() == []


# ---------------------------------------------------------------------------
# Proteins
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protein_creation_normalizes_sequence_and_counts_length(
    api_client: httpx.AsyncClient, project: Project
):
    target = await _create_target(api_client, project.id)

    protein = await _create_protein(
        api_client, target["id"], name="Multi-line", sequence="MEEP\nQSDV\r\nRKC"
    )

    assert protein["sequence"] == "MEEPQSDVRKC"
    assert protein["seq_length"] == 11
    assert protein["current_version"] == 1


@pytest.mark.asyncio
async def test_protein_creation_from_fasta_file(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    target = await _create_target(api_client, project.id)
    fasta = (
        b">sp|P00533|EGFR_HUMAN Epidermal growth factor receptor\n"
        b"MEEPQSDVRKC\nTTG\n"
    )
    record = await _upload(
        db_session,
        project_id=project.id,
        owner_id=users[OWNER].id,
        filename="egfr.fasta",
        content=fasta,
        content_type="text/plain",
    )

    response = await api_client.post(
        f"/api/v1/targets/{target['id']}/proteins",
        headers=_headers(OWNER),
        json={"name": "from fasta", "file_id": record.id, "source": "IMPORT"},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["sequence"] == "MEEPQSDVRKCTTG"
    assert data["seq_length"] == 14
    assert data["source"] == "IMPORT"


@pytest.mark.asyncio
async def test_protein_sequence_update_bumps_version(
    api_client: httpx.AsyncClient, project: Project
):
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])

    response = await api_client.put(
        f"/api/v1/proteins/{protein['id']}",
        headers=_headers(OWNER),
        json={"sequence": "MKTAYIAKQR"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sequence"] == "MKTAYIAKQR"
    assert data["seq_length"] == 10
    assert data["current_version"] == 2


@pytest.mark.asyncio
async def test_protein_requires_sequence_or_file(api_client: httpx.AsyncClient, project: Project):
    target = await _create_target(api_client, project.id)

    response = await api_client.post(
        f"/api/v1/targets/{target['id']}/proteins",
        headers=_headers(OWNER),
        json={"name": "empty"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structure_import_records_urn_and_checksum(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    content = b"ATOM      1  N   MET A   1      10.000  10.000  10.000  1.00 20.00           N\n"
    record = await _upload(
        db_session,
        project_id=project.id,
        owner_id=users[OWNER].id,
        filename="egfr.pdb",
        content=content,
    )

    response = await api_client.post(
        f"/api/v1/proteins/{protein['id']}/structures:import",
        headers=_headers(OWNER),
        json={"file_id": record.id, "source_type": "IMPORTED", "model_name": "crystal"},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source_type"] == "IMPORTED"
    assert data["sha256"] == hashlib.sha256(content).hexdigest()
    assert data["structure_urn"].startswith(domain_targets.FILE_URN_PREFIX)
    assert data["structure_file_id"]
    assert data["model"] == {"name": "crystal", "version": None}


@pytest.mark.asyncio
async def test_structure_pdb_endpoint_returns_download_entries(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    structure = await _create_structure(
        api_client, db_session, protein["id"], project.id, users[OWNER].id
    )

    response = await api_client.get(
        f"/api/v1/structures/{structure['id']}/pdb", headers=_headers(VIEWER)
    )

    assert response.status_code == 200
    files = response.json()["data"]["files"]
    assert [item["role"] for item in files] == ["structure"]
    assert files[0]["download_url"].startswith("/api/v1/files/")

    exported = await api_client.post(
        f"/api/v1/structures/{structure['id']}:export", headers=_headers(VIEWER)
    )
    assert exported.status_code == 200
    assert exported.json()["data"]["files"][0]["role"] == "structure"


@pytest.mark.asyncio
async def test_structure_export_writes_audit_event(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
    monkeypatch,
):
    """导出结构包必须留痕（V3.0 §6.2 / docs/26 H-9）。"""
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    structure = await _create_structure(
        api_client, db_session, protein["id"], project.id, users[OWNER].id
    )

    events: list = []
    audit_logger = get_audit_logger()
    monkeypatch.setattr(audit_logger, "enable_file_logging", False)
    monkeypatch.setattr(audit_logger, "enable_db_logging", True)
    monkeypatch.setattr(audit_logger, "_db_writer", events.append)

    response = await api_client.post(
        f"/api/v1/structures/{structure['id']}:export", headers=_headers(VIEWER)
    )
    assert response.status_code == 200

    export_events = [event for event in events if event.action is AuditAction.EXPORT]
    assert len(export_events) == 1
    event = export_events[0]
    assert event.resource_type is ResourceType.STRUCTURE
    assert event.resource_id == structure["id"]
    assert event.extra["kind"] == "structure_bundle"
    assert event.extra["file_roles"] == ["structure"]


@pytest.mark.asyncio
async def test_structure_import_rejects_foreign_project_file(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
):
    other_org = Organization(name="Other", slug="other")
    db_session.add(other_org)
    await db_session.flush()
    other_project = Project(
        organization_id=other_org.id, created_by=users[OWNER].id, name="Other", status="active"
    )
    db_session.add(other_project)
    await db_session.commit()

    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    foreign = await _upload(
        db_session,
        project_id=other_project.id,
        owner_id=users[OWNER].id,
        filename="foreign.pdb",
        content=b"ATOM\n",
    )

    response = await api_client.post(
        f"/api/v1/proteins/{protein['id']}/structures:import",
        headers=_headers(OWNER),
        json={"file_id": foreign.id},
    )

    assert response.status_code == 422
    assert "当前项目" in response.json()["message"]


# ---------------------------------------------------------------------------
# Pockets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pocket_creation_lists_residues_and_blocks_duplicate_rank(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    structure = await _create_structure(
        api_client, db_session, protein["id"], project.id, users[OWNER].id
    )

    created = await api_client.post(
        f"/api/v1/structures/{structure['id']}/pockets",
        headers=_headers(OWNER),
        json=_pocket_payload(),
    )
    assert created.status_code == 200, created.text
    pocket = created.json()["data"]
    assert pocket["rank"] == 1
    assert pocket["residue_count"] == 2
    assert pocket["center"] == {"x": 12.5, "y": -3.25, "z": 30.75}
    assert len(pocket["residues"]) == 2

    duplicate = await api_client.post(
        f"/api/v1/structures/{structure['id']}/pockets",
        headers=_headers(OWNER),
        json=_pocket_payload(),
    )
    assert duplicate.status_code == 409

    listing = await api_client.get(
        f"/api/v1/structures/{structure['id']}/pockets", headers=_headers(VIEWER)
    )
    assert listing.status_code == 200
    assert [item["rank"] for item in listing.json()["data"]["items"]] == [1]

    residues = await api_client.get(
        f"/api/v1/pockets/{pocket['id']}/residues",
        headers=_headers(VIEWER),
        params={"key_only": True},
    )
    assert residues.status_code == 200
    items = residues.json()["data"]["items"]
    assert [(item["chain"], item["residue_seq"]) for item in items] == [("A", 745)]
    assert items[0]["is_key"] is True


@pytest.mark.asyncio
async def test_selecting_a_pocket_deselects_the_previous_one(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    structure = await _create_structure(
        api_client, db_session, protein["id"], project.id, users[OWNER].id
    )
    first = (
        await api_client.post(
            f"/api/v1/structures/{structure['id']}/pockets",
            headers=_headers(OWNER),
            json=_pocket_payload(rank=1),
        )
    ).json()["data"]
    second = (
        await api_client.post(
            f"/api/v1/structures/{structure['id']}/pockets",
            headers=_headers(OWNER),
            json=_pocket_payload(rank=2),
        )
    ).json()["data"]

    selected_first = await api_client.post(
        f"/api/v1/pockets/{first['id']}:select",
        headers=_headers(OWNER),
        json={"selected": True},
    )
    assert selected_first.status_code == 200
    assert selected_first.json()["data"]["selected"] is True

    selected_second = await api_client.post(
        f"/api/v1/pockets/{second['id']}:select",
        headers=_headers(OWNER),
        json={"selected": True},
    )
    assert selected_second.status_code == 200
    assert selected_second.json()["data"]["selected"] is True

    pockets = await db_session.execute(select(Pocket).order_by(Pocket.rank))
    selected_flags = [(item.rank, item.selected) for item in pockets.scalars().all()]
    assert selected_flags == [(1, False), (2, True)]


@pytest.mark.asyncio
async def test_pocket_box_without_center_is_rejected(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    structure = await _create_structure(
        api_client, db_session, protein["id"], project.id, users[OWNER].id
    )
    payload = _pocket_payload()
    for key in ("center_x", "center_y", "center_z"):
        payload.pop(key)

    response = await api_client.post(
        f"/api/v1/structures/{structure['id']}/pockets",
        headers=_headers(OWNER),
        json=payload,
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Task submission
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def submitted_tasks(monkeypatch: pytest.MonkeyPatch) -> list[SimpleNamespace]:
    captured: list[SimpleNamespace] = []

    async def fake_create_and_schedule_tool_task(*, db, current_user, task_data, extra_data=None, **_kwargs):
        record = SimpleNamespace(
            id=f"task-{len(captured) + 1}",
            # 真实 dispatch_tool_task 返回前已把任务置为 QUEUED（大写库值），
            # 这里用大写值才能验证提交响应的状态确实被转成了小写契约。
            status="QUEUED",
            priority=task_data.priority,
            project_id=task_data.project_id,
            tool_id=task_data.tool_id,
            params=task_data.params,
            file_ids=task_data.file_ids,
            standard_input_uploads=task_data.standard_input_uploads,
            input_bindings=task_data.input_bindings,
            name=task_data.name,
            extra_data=extra_data,
            created_at=utcnow(),
        )
        captured.append(record)
        return record

    monkeypatch.setattr(
        domain_targets, "create_and_schedule_tool_task", fake_create_and_schedule_tool_task
    )
    return captured


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
async def test_structure_prediction_submits_boltz_task(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
    submitted_tasks: list[SimpleNamespace],
):
    await _register_tool(db_session, slug="boltz-2", owner_id=users[OWNER].id)
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])

    response = await api_client.post(
        f"/api/v1/proteins/{protein['id']}/structures:predict",
        headers=_headers(OWNER),
        json={
            "modelRef": {"name": "boltz-2", "version": "2.0.1"},
            "params": {"useMsa": False, "numRecycles": 3, "seed": 20260101},
            "resourceProfile": {"dcu": 1, "cpu": 8, "memGB": 32},
            "priority": "high",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["task_id"] == "task-1"
    # 与列表接口同一套小写契约：库里的 QUEUED 必须输出成 "queued"。
    assert data["status"] == "queued"
    assert data["priority"] == "high"
    assert len(submitted_tasks) == 1
    submitted = submitted_tasks[0]
    assert submitted.params["sequence"] == "MEEPQSDVRKC"
    assert submitted.params["numRecycles"] == 3
    assert submitted.extra_data["domain"]["kind"] == "structure_prediction"
    assert submitted.extra_data["domain"]["model_ref"] == {"name": "boltz-2", "version": "2.0.1"}


@pytest.mark.asyncio
async def test_structure_prediction_requires_registered_tool(
    api_client: httpx.AsyncClient, project: Project, submitted_tasks: list[SimpleNamespace]
):
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])

    response = await api_client.post(
        f"/api/v1/proteins/{protein['id']}/structures:predict",
        headers=_headers(OWNER),
        json={"params": {}},
    )

    assert response.status_code == 409
    assert "boltz-2" in response.json()["message"]
    assert submitted_tasks == []


@pytest.mark.asyncio
async def test_pocket_prediction_uses_registered_lvpocket_tool(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
    submitted_tasks: list[SimpleNamespace],
):
    await _register_tool(
        db_session, slug="lvpocket-pocket-prediction", owner_id=users[OWNER].id
    )
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    structure = await _create_structure(
        api_client, db_session, protein["id"], project.id, users[OWNER].id
    )

    response = await api_client.post(
        f"/api/v1/structures/{structure['id']}/pockets:predict",
        headers=_headers(OWNER),
        json={"params": {"top_k": 5}},
    )

    assert response.status_code == 200, response.text
    assert len(submitted_tasks) == 1
    submitted = submitted_tasks[0]
    assert submitted.params["top_k"] == 5
    # 口袋预测的输入不是「挂几个文件」，而是按工具形态二选一：
    # 这里注册的是没有 tool_package_manifest 的工具，所以走标准输入上传槽。
    assert submitted.file_ids == []
    assert submitted.standard_input_uploads == {"protein": structure["structure_file_id"]}
    assert submitted.extra_data["domain"]["kind"] == "pocket_prediction"


# ---------------------------------------------------------------------------
# Service-level counters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_domain_counts_track_targets_structures_and_pockets(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    structure = await _create_structure(
        api_client, db_session, protein["id"], project.id, users[OWNER].id
    )
    for rank in (1, 2):
        await api_client.post(
            f"/api/v1/structures/{structure['id']}/pockets",
            headers=_headers(OWNER),
            json=_pocket_payload(rank=rank),
        )

    counts = await domain_targets.project_domain_counts(db_session, project_id=project.id)

    assert counts == {"targets": 1, "structures": 1, "pockets": 2}


@pytest.mark.asyncio
async def test_deleting_project_removes_domain_rows(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])
    structure = await _create_structure(
        api_client, db_session, protein["id"], project.id, users[OWNER].id
    )
    await api_client.post(
        f"/api/v1/structures/{structure['id']}/pockets",
        headers=_headers(OWNER),
        json=_pocket_payload(),
    )

    response = await api_client.delete(
        f"/api/v1/projects/{project.id}", headers=_headers(OWNER)
    )

    assert response.status_code == 200, response.text
    for model in (Target, Protein, ProteinStructure, Pocket, PocketResidue):
        remaining = (await db_session.execute(select(model))).scalars().all()
        assert remaining == [], f"{model.__tablename__} should be cleared with the project"


@pytest.mark.asyncio
async def test_task_queue_position_counts_pending_and_queued_only(
    db_session: AsyncSession,
    project: Project,
    users: dict[str, User],
):
    """提交响应里的 queue_position 要覆盖 PENDING 与 QUEUED。

    调度返回前任务已被置为 QUEUED（大写枚举值），旧实现只认 ``"pending"``：
    判定永远为真、直接返回 None，前端拿到的 queue_position 恒为空。
    """
    tool = await _register_tool(db_session, slug="queue-position", owner_id=users[OWNER].id)
    base = utcnow() - timedelta(minutes=10)

    async def _make(status: str, priority: str, offset_seconds: int) -> Task:
        task = Task(
            user_id=users[OWNER].id,
            project_id=project.id,
            tool_id=tool.id,
            tool_version_id=tool.current_version_id,
            status=status,
            priority=priority,
            created_at=base + timedelta(seconds=offset_seconds),
        )
        db_session.add(task)
        await db_session.flush()
        return task

    first_pending = await _make("PENDING", "normal", 0)
    target_queued = await _make("QUEUED", "normal", 10)
    await _make("PENDING", "normal", 20)
    running = await _make("RUNNING", "normal", 30)
    high_priority = await _make("PENDING", "high", 5)
    await db_session.commit()

    # 同优先级、created_at 不晚于自己的 PENDING/QUEUED 共 2 条（含自己）。
    assert await domain_targets.task_queue_position(db_session, task=target_queued) == 2
    assert await domain_targets.task_queue_position(db_session, task=first_pending) == 1
    # 非排队态不给位置。
    assert await domain_targets.task_queue_position(db_session, task=running) is None
    # 优先级不同不互相占位。
    assert await domain_targets.task_queue_position(db_session, task=high_priority) == 1
