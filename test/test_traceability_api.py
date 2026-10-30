"""Traceability tests: input snapshots, 追溯包, append-only guard, audit sink.

Covers docs/01 §11.2 (六类元数据 + 一键导出追溯包), docs/04 §9.2/§5.4,
docs/10 DB-09 (只追加) and docs/12 TC-NFR-04 (审计可查).
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timedelta, timezone
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

from app.auth.dependencies import get_current_user  # noqa: E402
from app.common.time import utcnow  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.files.writer import store_file_bytes  # noqa: E402
from app.logging.audit import AuditAction, AuditEvent, AuditResult, ResourceType  # noqa: E402
from app.main import app  # noqa: E402
from app.models.artifacts import Artifact, ArtifactVersion  # noqa: E402
from app.models.compounds import Candidate  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.tasks import Task  # noqa: E402
from app.models.tools import Tool, ToolProviderType, ToolStatus, ToolVersion  # noqa: E402
from app.models.traceability import (  # noqa: E402
    AuditLog,
    ImmutableRecordError,
    TaskInputSnapshot,
)
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.schemas.tasks import TaskCreate  # noqa: E402
from app.services import traceability  # noqa: E402
from app.services.audit_sink import AuditDbWriter, event_to_row  # noqa: E402
from app.services.traceability import (  # noqa: E402
    INPUT_ROLE_FILE,
    INPUT_ROLE_LIGAND,
    INPUT_ROLE_RECEPTOR,
    INPUT_ROLE_SEQUENCE,
    build_traceability_package,
    record_task_inputs,
    role_for_semantic_type,
)
from app.tasks.service import create_and_schedule_tool_task  # noqa: E402

OWNER = "owner"
VIEWER = "viewer"
OUTSIDER = "outsider"
ADMIN = "admin"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


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


async def _create_user(db: AsyncSession, email: str, *, role: str = UserRole.USER.value) -> User:
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
        ADMIN: await _create_user(db_session, "admin@example.com", role=UserRole.ADMIN.value),
    }


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    organization = Organization(name="Trace Lab", slug="trace-lab")
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
    db_session.add(ProjectMember(project_id=project.id, user_id=users[OWNER].id, role="owner"))
    db_session.add(ProjectMember(project_id=project.id, user_id=users[VIEWER].id, role="viewer"))
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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _manifest(*, input_name: str = "protein", input_type: str = "protein_structure@1") -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "boltz-2",
            "name": "Boltz-2",
            "version": "2.0.1",
            "description": "Structure prediction",
        },
        "artifacts": {
            "inputs": [{"name": input_name, "type": input_type, "required": True}],
            "outputs": [{"name": "report", "type": "run_report@1", "required": False}],
        },
        "parameters_schema": {"type": "object", "properties": {}, "required": []},
        "runtime": {
            "python": "3.10",
            "executor_support": ["ssh_docker_exec"],
            "selection_policy": "test runtime fixture",
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": "registry.internal/cnpharm/boltz-2:2.0.1",
                    "image_digest": "sha256:test",
                },
                "fallback": {
                    "kind": "conda_pack",
                    "uri": "artifacts://model-envs/boltz-2/2.0.1/env.tar.gz",
                    "sha256": "test",
                },
            },
            "weights": {
                "manifest_uri": "artifacts://model-weights/boltz-2/2.0.1/weights.json",
                "manifest_sha256": "test",
            },
            "cache_policy": {
                "key_fields": ["metadata.slug", "metadata.version"],
                "mutable_host_paths_forbidden": True,
            },
        },
        "variants": [
            {
                "name": "dcu",
                "accelerator": "dcu",
                "executor_types": ["cli"],
                "entrypoint": ["python", "run.py"],
            }
        ],
    }


async def _create_tool(db: AsyncSession, owner: User, *, image: str = "registry.internal/x:1") -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name="Boltz-2",
        slug="boltz-2",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="2.0.1",
        config={"type": "ssh_job", "image": image, "tool_package_manifest": _manifest()},
        is_active=True,
        deprecated=False,
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    await db.commit()
    await db.refresh(tool)
    return tool


async def _upload(db: AsyncSession, *, owner: User, project: Project, filename: str, content: bytes):
    record = await store_file_bytes(
        db,
        content=content,
        filename=filename,
        content_type="chemical/x-pdb",
        source_type=FileSourceType.USER_INPUT,
        owner_id=str(owner.id),
        project_id=str(project.id),
    )
    await db.commit()
    await db.refresh(record)
    return record


async def _create_task(db: AsyncSession, *, owner: User, project: Project, tool: Tool, file_id: str):
    return await create_and_schedule_tool_task(
        db=db,
        current_user=owner,
        task_data=TaskCreate(
            tool_id=tool.id,
            project_id=project.id,
            standard_input_uploads={"protein": file_id},
        ),
        direct_runner=SimpleNamespace(schedule_task=lambda *, task_id, tool_version_id: None),
    )


# ---------------------------------------------------------------------------
# role mapping
# ---------------------------------------------------------------------------


def test_role_for_semantic_type_maps_standard_types():
    assert role_for_semantic_type("protein_structure@1") == INPUT_ROLE_RECEPTOR
    assert role_for_semantic_type("ligand_structure@1") == INPUT_ROLE_LIGAND
    assert role_for_semantic_type("binding_pocket@1") == "POCKET"
    assert role_for_semantic_type("molecule_table@1") == INPUT_ROLE_LIGAND
    assert role_for_semantic_type("run_report@1") is None
    assert role_for_semantic_type(None) is None


# ---------------------------------------------------------------------------
# snapshots are written with the task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_creation_freezes_input_snapshot(
    db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    upload = await _upload(
        db_session,
        owner=users[OWNER],
        project=project,
        filename="egfr.pdb",
        content=b"ATOM      1  N   MET A   1\nEND\n",
    )

    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, file_id=upload.id
    )

    rows = (
        await db_session.execute(
            select(TaskInputSnapshot)
            .where(TaskInputSnapshot.task_id == task.id)
            .order_by(TaskInputSnapshot.input_role, TaskInputSnapshot.ordinal)
        )
    ).scalars().all()
    # 两条：用户上传的文件（事实输入）+ 平台据其物化出的 ArtifactVersion（派生载体）。
    assert [(row.input_role, row.entity_type) for row in rows] == [
        (INPUT_ROLE_RECEPTOR, "file"),
        (INPUT_ROLE_RECEPTOR, "artifact_version"),
    ]
    snapshot = rows[0]
    assert snapshot.input_role == INPUT_ROLE_RECEPTOR
    assert snapshot.urn == f"file:{upload.id}"
    assert snapshot.sha256 == upload.sha256
    assert snapshot.file_id == upload.id
    assert snapshot.detail["filename"] == "egfr.pdb"
    assert snapshot.detail["slots"] == ["protein"]
    assert rows[1].detail["derived_from_file"] == upload.id


@pytest.mark.asyncio
async def test_task_creation_keeps_unlabelled_files_as_file_role(
    db_session: AsyncSession, users: dict[str, User], project: Project
):
    """Files passed through legacy ``params.input_files`` still get recorded."""
    tool = await _create_tool(db_session, users[OWNER])
    upload = await _upload(
        db_session, owner=users[OWNER], project=project, filename="raw.pdb", content=b"ATOM\n"
    )

    task = await create_and_schedule_tool_task(
        db=db_session,
        current_user=users[OWNER],
        task_data=TaskCreate(
            tool_id=tool.id,
            project_id=project.id,
            params={"input_files": {"protein": upload.id}},
        ),
        direct_runner=SimpleNamespace(schedule_task=lambda *, task_id, tool_version_id: None),
    )

    rows = (
        await db_session.execute(
            select(TaskInputSnapshot).where(TaskInputSnapshot.task_id == task.id)
        )
    ).scalars().all()
    assert [row.input_role for row in rows] == [INPUT_ROLE_FILE]
    assert rows[0].sha256 == upload.sha256


@pytest.mark.asyncio
async def test_snapshot_records_artifact_binding_and_domain_entity(
    db_session: AsyncSession, users: dict[str, User], project: Project
):
    """Artifact bindings are pinned by version + digest, never by mutable artifact id."""
    owner = users[OWNER]
    tool = await _create_tool(db_session, owner)
    task_id = "task-domain-1"
    task = Task(
        id=task_id,
        user_id=owner.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        name="pocket prediction",
        status="SUCCESS",
        priority="normal",
        progress=1.0,
        extra_data={
            "project_id": str(project.id),
            "domain": {"kind": "structure_preparation", "structure_id": "structure-1"},
        },
    )
    db_session.add(task)

    artifact = Artifact(
        project_id=project.id,
        created_by=owner.id,
        # 资产类型收敛为受控枚举：此夹具历史上用 structure（非受控值），现归一为
        # protein_structure。
        artifact_type="protein_structure",
        semantic_type="protein_structure@1",
        name="EGFR",
    )
    db_session.add(artifact)
    await db_session.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=3,
        filename="egfr.pdb",
        size_bytes=12,
        sha256=hashlib.sha256(b"ATOM\nEND\n").hexdigest(),
        storage_key="artifacts/egfr.pdb",
    )
    db_session.add(version)
    await db_session.flush()

    from app.models.targets import Protein, ProteinStructure, Target

    target = Target(project_id=project.id, created_by=owner.id, name="EGFR")
    db_session.add(target)
    await db_session.flush()
    protein = Protein(
        target_id=target.id, name="EGFR kinase", sequence="MKTAYIAK", seq_length=8
    )
    db_session.add(protein)
    await db_session.flush()
    structure = ProteinStructure(
        id="structure-1",
        protein_id=protein.id,
        source_type="IMPORTED",
        structure_urn="file:abc",
        sha256="deadbeef",
    )
    db_session.add(structure)
    await db_session.flush()

    prepared = SimpleNamespace(
        file_ids=[],
        input_bindings={"protein": version.id},
        standard_input_uploads={},
    )
    rows = await record_task_inputs(
        db_session,
        task=task,
        tool_version=None,
        prepared=prepared,
        extra_data=task.extra_data,
    )
    await db_session.commit()

    roles = {row.input_role for row in rows}
    assert INPUT_ROLE_RECEPTOR in roles
    artifact_row = next(row for row in rows if row.entity_type == "artifact_version")
    assert artifact_row.urn == f"artifact:{version.id}"
    assert artifact_row.sha256 == version.sha256
    assert artifact_row.data_version == 3


# ---------------------------------------------------------------------------
# append-only guard (docs/10 DB-09)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_and_snapshot_rows_reject_update(
    db_session: AsyncSession, users: dict[str, User]
):
    row = AuditLog(actor="owner@example.com", action="LOGIN", result="SUCCESS")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    row.action = "LOGOUT"
    with pytest.raises(ImmutableRecordError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_snapshot_rows_reject_delete(db_session: AsyncSession, users: dict[str, User]):
    row = TaskInputSnapshot(task_id="task-1", input_role=INPUT_ROLE_FILE, ordinal=0)
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    await db_session.delete(row)
    with pytest.raises(ImmutableRecordError):
        await db_session.commit()
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 追溯包
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_traceability_package_contains_all_six_groups(
    db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    upload = await _upload(
        db_session, owner=users[OWNER], project=project, filename="egfr.pdb", content=b"ATOM\nEND\n"
    )
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, file_id=upload.id
    )
    task.status = "SUCCESS"
    task.started_at = utcnow()
    task.finished_at = utcnow()
    task.execution_time_sec = 12.5
    await db_session.commit()

    loaded = (
        await db_session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()

    package = await build_traceability_package(
        db_session,
        task=loaded,
        tool=tool,
        tool_version=tool.current_version,
        submitter=users[OWNER],
    )

    assert package["packageVersion"] == "traceability.v1"
    assert package["taskId"] == task.id
    # 输入快照
    assert package["inputs"][0]["urn"] == f"file:{upload.id}"
    assert package["inputs"][0]["sha256"] == upload.sha256
    # 执行环境
    assert package["environment"]["image"] == "registry.internal/x:1"
    assert package["environment"]["tool"]["version"] == "2.0.1"
    # 运行参数
    assert package["params"]["requested"] == {}
    # 执行过程
    assert package["process"]["logsEndpoint"] == f"/api/v1/tasks/{task.id}/logs"
    # 输出产物
    assert isinstance(package["outputs"], list)
    # 归属关系
    assert package["bizRef"]["projectId"] == str(project.id)
    assert package["submittedBy"]["email"] == "owner@example.com"


@pytest.mark.asyncio
async def test_traceability_package_marks_missing_recovered_fields_as_null(
    db_session: AsyncSession, users: dict[str, User], project: Project
):
    """An incomplete record must look incomplete, not look clean."""
    tool = await _create_tool(db_session, users[OWNER])
    task = Task(
        user_id=users[OWNER].id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        name="orphan task",
        status="FAILURE",
        priority="normal",
        progress=0.0,
        extra_data={"project_id": str(project.id)},
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    # Build the package without passing tool/tool_version: that is what a caller
    # reading a bare Task row can do, and the package must stay honest about it.
    package = await build_traceability_package(db_session, task=task)
    assert package["inputs"] == []
    assert package["outputs"] == []
    assert package["environment"]["image"] is None
    assert package["taskType"] is None


# ---------------------------------------------------------------------------
# API: traceability endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_traceability_endpoint_returns_package(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    upload = await _upload(
        db_session, owner=users[OWNER], project=project, filename="egfr.pdb", content=b"ATOM\n"
    )
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, file_id=upload.id
    )

    response = await api_client.get(
        f"/api/v1/results/{task.id}/traceability", headers=_headers(OWNER)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["taskId"] == task.id
    assert data["inputs"][0]["urn"] == f"file:{upload.id}"


@pytest.mark.asyncio
async def test_traceability_endpoint_rejects_outsider(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    upload = await _upload(
        db_session, owner=users[OWNER], project=project, filename="egfr.pdb", content=b"ATOM\n"
    )
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, file_id=upload.id
    )

    response = await api_client.get(
        f"/api/v1/results/{task.id}/traceability", headers=_headers(OUTSIDER)
    )
    assert response.status_code in (403, 404)


@pytest.mark.asyncio
async def test_export_writes_downloadable_json(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    upload = await _upload(
        db_session, owner=users[OWNER], project=project, filename="egfr.pdb", content=b"ATOM\n"
    )
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, file_id=upload.id
    )

    response = await api_client.post(f"/api/v1/results/{task.id}:export", headers=_headers(OWNER))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["filename"].startswith("traceability-")
    assert data["filename"].endswith(".json")
    assert len(data["sha256"]) == 64
    assert data["download_url"].startswith("/api/v1/files/")


@pytest.mark.asyncio
async def test_result_detail_exposes_frozen_inputs(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    upload = await _upload(
        db_session, owner=users[OWNER], project=project, filename="egfr.pdb", content=b"ATOM\n"
    )
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, file_id=upload.id
    )

    response = await api_client.get(f"/api/v1/results/{task.id}", headers=_headers(VIEWER))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["inputs"][0]["inputRole"] == INPUT_ROLE_RECEPTOR
    assert data["tool_slug"] == "boltz-2"


@pytest.mark.asyncio
async def test_project_results_only_lists_terminal_tasks(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    upload = await _upload(
        db_session, owner=users[OWNER], project=project, filename="egfr.pdb", content=b"ATOM\n"
    )
    running = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, file_id=upload.id
    )
    done = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, file_id=upload.id
    )
    done.status = "SUCCESS"
    done.finished_at = utcnow()
    await db_session.commit()

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/results", headers=_headers(OWNER)
    )
    assert response.status_code == 200
    payload = response.json()
    ids = [item["task_id"] for item in payload["data"]["items"]]
    assert done.id in ids
    assert running.id not in ids


# ---------------------------------------------------------------------------
# audit sink
# ---------------------------------------------------------------------------


def test_event_to_row_snapshots_the_actor_name():
    event = AuditEvent(
        id="audit-1",
        timestamp=utcnow(),
        action=AuditAction.LOGIN,
        result=AuditResult.SUCCESS,
        user_id="user-1",
        user_email="owner@example.com",
        user_role="user",
        resource_type=ResourceType.SESSION,
        resource_id="session-1",
        client_ip="10.0.0.8",
        user_agent="Mozilla/5.0",
        request_id="req-1",
        changes={"before": None, "after": {"status": "active"}},
        reason="登录",
    )

    row = event_to_row(event)
    assert row["actor"] == "owner@example.com"
    assert row["actor_id"] == "user-1"
    assert row["action"] == "LOGIN"
    assert row["resource_type"] == "SESSION"
    assert row["detail"]["reason"] == "登录"
    assert row["detail"]["before"] is None
    assert row["ip"] == "10.0.0.8"
    assert row["request_id"] == "req-1"


def test_event_to_row_falls_back_to_anonymous():
    event = AuditEvent(
        id="audit-2",
        timestamp=utcnow(),
        action=AuditAction.LOGIN_FAILED,
        result=AuditResult.FAILURE,
        user_id=None,
    )
    row = event_to_row(event)
    assert row["actor"] == "anonymous"
    assert row["result"] == "FAILURE"
    assert row["resource_type"] is None


@pytest.mark.asyncio
async def test_audit_writer_persists_events(db_session: AsyncSession, monkeypatch):
    """The queued writer must reach the table through its own session."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session_scope():
        yield db_session

    monkeypatch.setattr(
        "app.database.session.async_session_factory", lambda: session_scope()
    )

    writer = AuditDbWriter()
    writer.start()
    writer(
        AuditEvent(
            id="audit-3",
            timestamp=utcnow(),
            action=AuditAction.TASK_SUBMIT,
            result=AuditResult.SUCCESS,
            user_id="user-1",
            user_email="owner@example.com",
            resource_type=ResourceType.TASK,
            resource_id="task-1",
        )
    )
    await writer._queue.join()  # noqa: SLF001
    await writer.stop()

    rows = (await db_session.execute(select(AuditLog))).scalars().all()
    assert [row.action for row in rows] == ["TASK_SUBMIT"]
    assert writer.written == 1
    assert writer.dropped == 0


def test_audit_writer_drops_instead_of_blocking():
    """A full queue must not raise into the request path (docs/04 §3.2.2)."""
    writer = AuditDbWriter(queue_size=1)
    writer._queue = __import__("asyncio").Queue(maxsize=1)  # noqa: SLF001
    writer._queue.put_nowait(  # noqa: SLF001
        AuditEvent(id="a", timestamp=utcnow(), action=AuditAction.READ, result=AuditResult.SUCCESS)
    )
    writer(
        AuditEvent(id="b", timestamp=utcnow(), action=AuditAction.READ, result=AuditResult.SUCCESS)
    )
    assert writer.dropped == 1


# ---------------------------------------------------------------------------
# admin audit API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_audit_logs_require_admin(api_client: httpx.AsyncClient):
    response = await api_client.get("/api/v1/admin/audit-logs", headers=_headers(OWNER))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_audit_logs_support_filters(
    api_client: httpx.AsyncClient, db_session: AsyncSession
):
    db_session.add_all(
        [
            AuditLog(
                actor="owner@example.com",
                action="LOGIN",
                result="SUCCESS",
                resource_type="SESSION",
            ),
            AuditLog(
                actor="owner@example.com",
                action="TASK_SUBMIT",
                result="SUCCESS",
                resource_type="TASK",
                resource_id="task-9",
            ),
            AuditLog(
                actor="other@example.com",
                action="LOGIN_FAILED",
                result="FAILURE",
                resource_type="SESSION",
            ),
        ]
    )
    await db_session.commit()

    response = await api_client.get(
        "/api/v1/admin/audit-logs?action=LOGIN", headers=_headers(ADMIN)
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 1
    assert payload["items"][0]["action"] == "LOGIN"

    response = await api_client.get(
        "/api/v1/admin/audit-logs?result=failure", headers=_headers(ADMIN)
    )
    assert response.json()["data"]["total"] == 1

    response = await api_client.get(
        "/api/v1/admin/audit-logs?resource_id=task-9", headers=_headers(ADMIN)
    )
    assert response.json()["data"]["items"][0]["action"] == "TASK_SUBMIT"


@pytest.mark.asyncio
async def test_admin_audit_logs_reject_unknown_action(api_client: httpx.AsyncClient):
    response = await api_client.get(
        "/api/v1/admin/audit-logs?action=NOT_A_REAL_ACTION", headers=_headers(ADMIN)
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_audit_facets_reflect_stored_values(
    api_client: httpx.AsyncClient, db_session: AsyncSession
):
    db_session.add(
        AuditLog(actor="owner@example.com", action="LOGIN", result="SUCCESS", resource_type="SESSION")
    )
    await db_session.commit()

    response = await api_client.get("/api/v1/admin/audit-logs/facets", headers=_headers(ADMIN))
    assert response.status_code == 200
    data = response.json()["data"]
    assert "owner@example.com" in data["actors"]
    assert "LOGIN" in data["actions"]
    assert "SESSION" in data["resourceTypes"]


@pytest.mark.asyncio
async def test_admin_audit_logs_serialize_timestamps_as_utc(
    api_client: httpx.AsyncClient, db_session: AsyncSession
):
    """时间戳必须带 ``Z``，否则前端按本地时区解释 naive UTC 会整体偏 8 小时。"""
    db_session.add(
        AuditLog(
            actor="owner@example.com",
            action="LOGIN",
            result="SUCCESS",
            resource_type="SESSION",
            created_at=datetime(2026, 10, 25, 13, 0, 0),
        )
    )
    await db_session.commit()

    response = await api_client.get("/api/v1/admin/audit-logs", headers=_headers(ADMIN))
    assert response.status_code == 200
    created_at = response.json()["data"]["items"][0]["created_at"]
    assert created_at == "2026-10-25T13:00:00Z"


@pytest.mark.asyncio
async def test_admin_audit_logs_normalize_timezone_aware_filters(
    api_client: httpx.AsyncClient, db_session: AsyncSession
):
    """带时区的筛选入参要归一到 naive UTC，否则筛选窗口在东八区会偏移 8 小时。

    记录时间 2026-10-25 13:00 UTC 等价于 21:00 +08:00：用后者做下界仍应命中。
    """
    db_session.add(
        AuditLog(
            actor="owner@example.com",
            action="LOGIN",
            result="SUCCESS",
            resource_type="SESSION",
            created_at=datetime(2026, 10, 25, 13, 0, 0),
        )
    )
    await db_session.commit()

    response = await api_client.get(
        "/api/v1/admin/audit-logs?start_time=2026-10-25T20:59:00%2B08:00",
        headers=_headers(ADMIN),
    )
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 1

    # 同一时刻的上界若不做归一化，会被当成 20:59 UTC 而漏掉这条记录。
    response = await api_client.get(
        "/api/v1/admin/audit-logs?end_time=2026-10-25T21:00:00%2B08:00",
        headers=_headers(ADMIN),
    )
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 1


def test_to_naive_utc_normalizes_aware_values():
    from app.api.v1 import admin_audit

    assert admin_audit._to_naive_utc(None) is None
    naive = datetime(2026, 10, 25, 13, 0, 0)
    assert admin_audit._to_naive_utc(naive) is naive

    aware = datetime(2026, 10, 25, 21, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    normalized = admin_audit._to_naive_utc(aware)
    assert normalized == naive
    assert normalized.tzinfo is None


def test_traceability_module_exports_expected_helpers():
    assert traceability.INPUT_ROLE_SEQUENCE == "SEQUENCE"
    assert callable(traceability.sequence_sha256)


def test_sequence_hash_is_stable():
    assert traceability.sequence_sha256("MKTAYIAK") == hashlib.sha256(b"MKTAYIAK").hexdigest()
    assert traceability.sequence_sha256("") is None
    assert traceability.sequence_sha256(None) is None


# ---------------------------------------------------------------------------
# 结果中心：domain 投影与候选物过滤下推（D7/D8）
# ---------------------------------------------------------------------------


async def _direct_task(
    db: AsyncSession,
    *,
    owner: User,
    project: Project,
    tool: Tool,
    domain: dict,
    created_at: datetime | None = None,
) -> Task:
    task = Task(
        user_id=owner.id,
        project_id=project.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        name="result task",
        status="SUCCESS",
        priority="normal",
        progress=1.0,
        extra_data={"project_id": str(project.id), "domain": domain},
    )
    if created_at is not None:
        task.created_at = created_at
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@pytest.mark.asyncio
async def test_project_results_domain_is_kind_string(
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
    api_client,
):
    """D7：列表页 domain 应输出 kind 字符串，不能把 dict 直接给前端。"""
    tool = await _create_tool(db_session, users[OWNER])
    await _direct_task(
        db_session,
        owner=users[OWNER],
        project=project,
        tool=tool,
        domain={"kind": "docking", "model_ref": {"name": "vina"}},
    )

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/results", headers=_headers(OWNER)
    )

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["domain"] == "docking"
    assert item["mock"] is False


@pytest.mark.asyncio
async def test_candidate_results_filter_and_total_pushed_down_to_sql(
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
    api_client,
):
    """D8：candidate_id 过滤与 total 必须在 SQL 层完成，不能只过滤当前页。"""
    tool = await _create_tool(db_session, users[OWNER])
    candidate = Candidate(
        project_id=project.id,
        created_by=users[OWNER].id,
        candidate_type="PEPTIDE",
        peptide_sequence="ACDEFG",
        name="candidate-1",
    )
    db_session.add(candidate)
    await db_session.commit()
    await db_session.refresh(candidate)

    base = utcnow()
    matching_old = await _direct_task(
        db_session,
        owner=users[OWNER],
        project=project,
        tool=tool,
        domain={"kind": "docking", "candidate_id": str(candidate.id)},
        created_at=base - timedelta(seconds=30),
    )
    await _direct_task(
        db_session,
        owner=users[OWNER],
        project=project,
        tool=tool,
        domain={"kind": "docking", "candidate_id": "other-candidate"},
        created_at=base - timedelta(seconds=20),
    )
    matching_new = await _direct_task(
        db_session,
        owner=users[OWNER],
        project=project,
        tool=tool,
        domain={"kind": "docking", "candidate_id": str(candidate.id)},
        created_at=base - timedelta(seconds=10),
    )

    first = await api_client.get(
        f"/api/v1/candidates/{candidate.id}/results",
        params={"page": 1, "page_size": 1},
        headers=_headers(OWNER),
    )
    second = await api_client.get(
        f"/api/v1/candidates/{candidate.id}/results",
        params={"page": 2, "page_size": 1},
        headers=_headers(OWNER),
    )

    assert first.status_code == 200
    first_payload = first.json()["data"]
    assert first_payload["total"] == 2
    assert [item["task_id"] for item in first_payload["items"]] == [matching_new.id]

    assert second.status_code == 200
    second_payload = second.json()["data"]
    assert second_payload["total"] == 2
    assert [item["task_id"] for item in second_payload["items"]] == [matching_old.id]
