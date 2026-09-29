import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.auth.dependencies import get_admin_user, get_current_user
from app.config import settings as config_settings
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import File, Task, TaskInput, TaskLog, TaskOutput, Tool, ToolStatistics, ToolVersion, User
from app.worker import tasks as worker_tasks
from app.tasks.queue_manager import TaskQueueManager


@pytest_asyncio.fixture
async def test_client(tmp_path: Path):
    db_path = tmp_path / "task-visualization.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    current_user = User(
        id=str(uuid.uuid4()),
        email="viewer@test.local",
        password_hash="bcrypt-placeholder",
        display_name="viewer",
        role="user",
        status="active",
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def override_get_current_user():
        return current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, session_factory, current_user

    app.dependency_overrides.clear()
    await engine.dispose()


async def seed_visualization_task(
    session_factory: async_sessionmaker[AsyncSession],
    current_user: User,
) -> dict[str, str]:
    tool_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    input_file_id = str(uuid.uuid4())
    output_file_id = str(uuid.uuid4())

    async with session_factory() as session:
        session.add(current_user)

        tool = Tool(
            id=tool_id,
            owner_id=current_user.id,
            name="Pocket2Mol",
            slug="pocket2mol",
            description="Generate ligands from pockets",
            status="published",
            is_public=True,
            provider_type="platform",
            review_status="not_required",
        )
        version = ToolVersion(
            id=version_id,
            tool_id=tool_id,
            version="1.0.0",
            config={
                "type": "python_script",
                "endpoint": "https://internal.example/run",
                "headers": {"Authorization": "Bearer secret"},
                "script_content": "private script",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {
                    "type": "object",
                    "viewer_hint": "molecule",
                },
            },
            is_active=True,
            deprecated=False,
        )
        tool.current_version_id = version_id

        input_file = File(
            id=input_file_id,
            owner_id=current_user.id,
            filename="pocket.pdb",
            content_type="chemical/x-pdb",
            size_bytes=128,
            sha256="a" * 64,
            storage_path="/tmp/pocket.pdb",
            source_type="upload",
            file_meta={"original_name": "pocket_input.pdb"},
        )
        output_file = File(
            id=output_file_id,
            owner_id=current_user.id,
            filename="ligand.sdf",
            content_type="chemical/x-mdl-sdfile",
            size_bytes=256,
            sha256="b" * 64,
            storage_path="/tmp/ligand.sdf",
            source_type="tool_output",
            file_meta={"original_name": "generated_ligand.sdf"},
        )

        task = Task(
            id=task_id,
            user_id=current_user.id,
            tool_id=tool_id,
            tool_version_id=version_id,
            status="SUCCESS",
            progress=1.0,
        )
        task_input = TaskInput(
            task_id=task_id,
            params={"pocket_id": "A1"},
            file_ids=[input_file_id],
        )
        task_output = TaskOutput(
            task_id=task_id,
            result={"score": 0.87, "output_file_ids": [output_file_id]},
            file_ids=[output_file_id],
            output_type="visualization",
        )
        task_log = TaskLog(
            task_id=task_id,
            level="INFO",
            message="任务执行成功",
            log_data={"step": "completed"},
        )

        session.add_all([tool, version, input_file, output_file, task, task_input, task_output, task_log])
        await session.commit()

    return {
        "task_id": task_id,
        "tool_id": tool_id,
        "input_file_id": input_file_id,
        "output_file_id": output_file_id,
    }


@pytest.mark.asyncio
async def test_task_detail_returns_visualization_ready_payload(test_client):
    client, session_factory, current_user = test_client
    seeded = await seed_visualization_task(session_factory, current_user)

    response = await client.get(f"/api/v1/tasks/{seeded['task_id']}")

    assert response.status_code == 200
    payload = response.json()["data"]

    assert payload["inputs"]["params"] == {"pocket_id": "A1"}
    assert payload["output_data"]["score"] == 0.87
    assert payload["input_files"][0]["id"] == seeded["input_file_id"]
    assert payload["input_files"][0]["original_name"] == "pocket_input.pdb"
    assert payload["input_files"][0]["sha256"] == "a" * 64
    assert payload["input_files"][0]["url"] == f"/api/v1/files/{seeded['input_file_id']}/download"
    assert payload["output_files"][0]["id"] == seeded["output_file_id"]
    assert payload["output_files"][0]["original_name"] == "generated_ligand.sdf"
    assert payload["output_files"][0]["sha256"] == "b" * 64
    assert payload["output_files"][0]["url"] == f"/api/v1/files/{seeded['output_file_id']}/download"
    assert payload["tool"]["current_version"]["config"]["output_schema"]["viewer_hint"] == "molecule"
    assert "endpoint" not in payload["tool"]["current_version"]["config"]
    assert "headers" not in payload["tool"]["current_version"]["config"]
    assert "script_content" not in payload["tool"]["current_version"]["config"]


@pytest.mark.asyncio
async def test_task_detail_returns_structured_failure_diagnostics(test_client):
    client, session_factory, current_user = test_client
    seeded = await seed_visualization_task(session_factory, current_user)

    async with session_factory() as session:
        task = await session.get(Task, seeded["task_id"])
        assert task is not None
        task.status = "FAILURE"
        task.error_message = "Workflow node missing required standard artifacts: report (run_report@1)"
        output = (
            await session.execute(select(TaskOutput).where(TaskOutput.task_id == seeded["task_id"]))
        ).scalar_one()
        output.result = {
            "success": False,
            "details": {
                "stdout": "loading model",
                "stderr": "Missing required output artifact: report",
            },
        }
        output.file_ids = []
        output.output_type = "json"
        await session.commit()

    response = await client.get(f"/api/v1/tasks/{seeded['task_id']}")

    assert response.status_code == 200
    diagnostics = response.json()["data"]["failure_diagnostics"]
    assert diagnostics == {
        "error_message": "Workflow node missing required standard artifacts: report (run_report@1)",
        "stdout": "loading model",
        "stderr": "Missing required output artifact: report",
        "standard_artifact_message": "Workflow node missing required standard artifacts: report (run_report@1)",
    }


@pytest.mark.asyncio
async def test_task_detail_exposes_remote_recovery_state_without_run_handle(test_client):
    client, session_factory, current_user = test_client
    seeded = await seed_visualization_task(session_factory, current_user)

    async with session_factory() as session:
        task = await session.get(Task, seeded["task_id"])
        assert task is not None
        task.status = "RUNNING"
        task.extra_data = {
            "project_id": "project-1",
            "remote_run_id": "run-secret",
            "remote_recovery_failures": 3,
            "remote_recovery_next_attempt_at": "2026-09-20T12:03:00",
            "remote_recovery_last_error": "remote service unavailable",
            "remote_recovery_alerted": True,
        }
        await session.commit()

    response = await client.get(f"/api/v1/tasks/{seeded['task_id']}")

    assert response.status_code == 200
    recovery = response.json()["data"]["remote_recovery"]
    assert recovery == {
        "failures": 3,
        "next_attempt_at": "2026-09-20T12:03:00",
        "last_error": "remote service unavailable",
        "alerted": True,
    }
    assert "run-secret" not in response.text

    list_response = await client.get("/api/v1/tasks?page=1&page_size=20")

    assert list_response.status_code == 200
    list_item = next(
        item
        for item in list_response.json()["data"]["items"]
        if item["id"] == seeded["task_id"]
    )
    assert list_item["remote_recovery"] == recovery


@pytest.mark.asyncio
async def test_task_detail_exposes_resource_wait_state(test_client):
    client, session_factory, current_user = test_client
    seeded = await seed_visualization_task(session_factory, current_user)

    async with session_factory() as session:
        task = await session.get(Task, seeded["task_id"])
        assert task is not None
        task.status = "PENDING"
        task.extra_data = {
            "resource_wait_reason": "gpu_unavailable",
            "resource_retry_count": 2,
            "resource_retry_next_at": "2026-09-20T12:03:00",
        }
        await session.commit()

    response = await client.get(f"/api/v1/tasks/{seeded['task_id']}")

    assert response.status_code == 200
    resource_wait = response.json()["data"]["resource_wait"]
    assert resource_wait == {
        "reason": "gpu_unavailable",
        "retry_count": 2,
        "next_attempt_at": "2026-09-20T12:03:00",
    }

    list_response = await client.get("/api/v1/tasks?page=1&page_size=20")
    assert list_response.status_code == 200
    list_item = next(
        item
        for item in list_response.json()["data"]["items"]
        if item["id"] == seeded["task_id"]
    )
    assert list_item["resource_wait"] == resource_wait


@pytest.mark.asyncio
async def test_task_detail_exposes_quota_wait_reason(test_client):
    client, session_factory, current_user = test_client
    seeded = await seed_visualization_task(session_factory, current_user)

    async with session_factory() as session:
        task = await session.get(Task, seeded["task_id"])
        assert task is not None
        task.status = "PENDING"
        task.extra_data = {
            "resource_wait_reason": "worker_capability_unavailable",
            "resource_wait_code": "user_cpu_quota_exhausted",
            "resource_wait_category": "quota",
            "resource_wait_scope": "user",
            "resource_wait_dimension": "cpu",
            "resource_retry_count": 3,
            "resource_retry_next_at": "2026-09-22T12:03:00",
        }
        await session.commit()

    response = await client.get(f"/api/v1/tasks/{seeded['task_id']}")

    assert response.status_code == 200
    assert response.json()["data"]["resource_wait"] == {
        "reason": "user_cpu_quota_exhausted",
        "retry_count": 3,
        "next_attempt_at": "2026-09-22T12:03:00",
        "category": "quota",
        "scope": "user",
        "dimension": "cpu",
        "legacy_reason": "worker_capability_unavailable",
    }


@pytest.mark.asyncio
async def test_task_list_filters_resource_wait_category_and_exposes_stats(test_client):
    client, session_factory, current_user = test_client
    seeded = await seed_visualization_task(session_factory, current_user)

    async with session_factory() as session:
        task = await session.get(Task, seeded["task_id"])
        assert task is not None
        task.status = "PENDING"
        task.extra_data = {
            "resource_wait_reason": "worker_capability_unavailable",
            "resource_wait_code": "user_cpu_quota_exhausted",
            "resource_wait_category": "quota",
            "resource_wait_scope": "user",
            "resource_wait_dimension": "cpu",
            "resource_retry_count": 1,
            "resource_retry_next_at": "2026-09-22T12:03:00",
        }
        session.add(
            Task(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                tool_id=task.tool_id,
                tool_version_id=task.tool_version_id,
                status="PENDING",
                progress=0.0,
                extra_data={
                    "resource_wait_reason": "gpu_unavailable",
                    "resource_wait_code": "gpu_unavailable",
                    "resource_wait_category": "gpu",
                    "resource_wait_dimension": "gpu",
                    "resource_retry_count": 1,
                    "resource_retry_next_at": "2026-09-22T12:04:00",
                },
            )
        )
        await session.commit()

    filtered = await client.get(
        "/api/v1/tasks",
        params={"resource_wait_category": "quota", "page": 1, "page_size": 20},
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["data"]["items"]] == [
        seeded["task_id"]
    ]

    stats = await client.get("/api/v1/tasks/resource-wait-stats")
    assert stats.status_code == 200
    assert stats.json()["data"] == {
        "total": 2,
        "by_category": {"gpu": 1, "quota": 1},
        "by_reason": {
            "gpu_unavailable": 1,
            "user_cpu_quota_exhausted": 1,
        },
    }


@pytest.mark.asyncio
async def test_task_list_filters_remote_recovery_alerts(test_client):
    client, session_factory, current_user = test_client
    seeded = await seed_visualization_task(session_factory, current_user)
    clean_task_id = str(uuid.uuid4())

    async with session_factory() as session:
        task = await session.get(Task, seeded["task_id"])
        assert task is not None
        task.status = "RUNNING"
        task.extra_data = {
            "remote_recovery_failures": 5,
            "remote_recovery_alerted": True,
        }
        session.add(
            Task(
                id=clean_task_id,
                user_id=current_user.id,
                tool_id=seeded["tool_id"],
                tool_version_id=task.tool_version_id,
                status="RUNNING",
                progress=0.5,
                extra_data={},
            )
        )
        await session.commit()

    response = await client.get(
        "/api/v1/tasks?page=1&page_size=20&remote_recovery_alerted=true"
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["id"] for item in items] == [seeded["task_id"]]


@pytest.mark.asyncio
async def test_task_logs_endpoint_returns_paginated_items_with_metadata(test_client):
    client, session_factory, current_user = test_client
    seeded = await seed_visualization_task(session_factory, current_user)

    response = await client.get(f"/api/v1/tasks/{seeded['task_id']}/logs")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["message"] == "任务执行成功"
    assert payload["items"][0]["metadata"] == {"step": "completed"}


@pytest.mark.asyncio
async def test_create_task_persists_all_input_file_ids(test_client, monkeypatch):
    client, session_factory, current_user = test_client
    seeded = await seed_visualization_task(session_factory, current_user)
    second_input_file_id = str(uuid.uuid4())

    monkeypatch.setattr(
        TaskQueueManager,
        "determine_queue",
        classmethod(lambda cls, tool_config, user_role, priority, gpu_required=None: "default"),
    )
    monkeypatch.setattr(
        TaskQueueManager,
        "enqueue_task",
        classmethod(
            lambda cls, task_id, tool_version_id, queue: type(
                "DummyCeleryTask",
                (),
                {"id": "celery-task-id"},
            )()
        ),
    )
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "celery", raising=False)
    monkeypatch.setattr(config_settings, "CELERY_BROKER_URL", "redis://test", raising=False)

    async with session_factory() as session:
        session.add(
            File(
                id=second_input_file_id,
                owner_id=current_user.id,
                filename="pocket-extra.mmcif",
                content_type="chemical/x-cif",
                size_bytes=512,
                sha256="c" * 64,
                storage_path="/tmp/pocket-extra.mmcif",
                source_type="upload",
                file_meta={"original_name": "pocket-extra.mmcif"},
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/tasks",
        json={
            "tool_id": seeded["tool_id"],
            "params": {"seed": 7},
            "file_ids": [seeded["input_file_id"], second_input_file_id],
        },
    )

    assert response.status_code == 200
    created_task_id = response.json()["data"]["id"]

    async with session_factory() as session:
        result = await session.execute(select(TaskInput).where(TaskInput.task_id == created_task_id))
        task_input = result.scalar_one_or_none()
        task_result = await session.execute(select(Task).where(Task.id == created_task_id))
        created_task = task_result.scalar_one_or_none()

    assert task_input is not None
    assert created_task is not None
    assert task_input.file_ids == [seeded["input_file_id"], second_input_file_id]
    assert created_task.celery_task_id == "celery-task-id"
    assert created_task.extra_data["celery_task_id"] == "celery-task-id"


@pytest.mark.asyncio
async def test_cancel_task_without_celery_task_id_succeeds(test_client):
    client, session_factory, current_user = test_client
    seeded = await seed_visualization_task(session_factory, current_user)

    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == seeded["task_id"]))
        task = result.scalar_one()
        task.status = "PENDING"
        task.extra_data = {}
        await session.commit()

    response = await client.post(f"/api/v1/tasks/{seeded['task_id']}/cancel")

    assert response.status_code == 200

    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == seeded["task_id"]))
        canceled_task = result.scalar_one()

    assert canceled_task.status == "CANCELED"


def test_prepare_task_output_extracts_visualization_files():
    prepared = worker_tasks.prepare_task_output(
        {
            "success": True,
            "result": {
                "score": 0.87,
                "output_file_ids": ["file-out-1"],
            },
            "stderr": "",
        }
    )

    assert prepared["result"]["result"]["score"] == 0.87
    assert prepared["file_ids"] == ["file-out-1"]
    assert prepared["output_type"] == "visualization"


@pytest.mark.asyncio
async def test_delete_tool_removes_statistics_record(test_client):
    client, session_factory, current_user = test_client
    tool_id = str(uuid.uuid4())

    admin_user = User(
        id=str(uuid.uuid4()),
        email="admin@test.local",
        password_hash="bcrypt-placeholder",
        display_name="admin",
        role="admin",
        status="active",
    )

    async def override_get_admin_user():
        return admin_user

    app.dependency_overrides[get_admin_user] = override_get_admin_user

    async with session_factory() as session:
        session.add(admin_user)
        tool = Tool(
            id=tool_id,
            owner_id=admin_user.id,
            name="delete-me",
            slug="delete-me",
            description="Delete me",
            status="published",
            is_public=True,
            provider_type="platform",
            review_status="not_required",
        )
        session.add(tool)
        session.add(
            ToolStatistics(
                tool_id=tool_id,
                usage_count=3,
                favorite_count=1,
                view_count=9,
            )
        )
        await session.commit()

    try:
        response = await client.delete(f"/api/v1/tools/{tool_id}")
        assert response.status_code == 200

        async with session_factory() as session:
            tool_result = await session.execute(select(Tool).where(Tool.id == tool_id))
            statistics_result = await session.execute(
                select(ToolStatistics).where(ToolStatistics.tool_id == tool_id)
            )

        assert tool_result.scalar_one_or_none() is None
        assert statistics_result.scalar_one_or_none() is None
    finally:
        app.dependency_overrides.pop(get_admin_user, None)
