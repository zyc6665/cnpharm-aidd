"""Remote Tool v1 reference service contract tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import files as _files_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tools as _tools_models  # noqa: F401
from app.models.files import File as FileModel
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import ToolVersion
from app.remote_tools.client import RemoteToolDiscoveryClient
from app.tasks.executors.remote_api import RemoteAPIExecutor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PROJECT_ROOT / "example" / "remote-tool-v1-template"
REQUIRED_FILES = {
    "README.md",
    "requirements.txt",
    "service.py",
    "tests/test_remote_tool_v1_contract.py",
}


def _load_service_module():
    spec = importlib.util.spec_from_file_location(
        "remote_tool_v1_template_service",
        TEMPLATE_ROOT / "service.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _create_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, session_factory


def test_remote_tool_v1_template_contains_required_files():
    missing = sorted(path for path in REQUIRED_FILES if not (TEMPLATE_ROOT / path).is_file())

    assert missing == []


def test_remote_tool_v1_template_serves_discovery_and_examples():
    service = _load_service_module()
    client = TestClient(service.create_app())

    manifest_response = client.get("/.well-known/sciminer-tool.json")
    health_response = client.get("/health")
    examples_response = client.get("/examples")

    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["api_version"] == "aidd.sciminer/remote-tool.v1"
    assert manifest["kind"] == "RemoteTool"
    assert manifest["endpoints"]["invoke"] == "/invoke"
    assert manifest["endpoints"]["status"] == "/runs/{remote_run_id}"
    assert manifest["endpoints"]["logs"] == "/runs/{remote_run_id}/logs"
    assert manifest["endpoints"]["cancel"] == "/runs/{remote_run_id}/cancel"
    assert manifest["endpoints"]["artifacts"] == "/runs/{remote_run_id}/artifacts"
    assert manifest["capabilities"] == {
        "async": True,
        "logs": True,
        "cancel": True,
        "progress": True,
    }
    assert manifest["artifacts"]["inputs"][0]["type"] == "protein_structure@1"
    assert manifest["artifacts"]["outputs"][0]["type"] == "binding_pocket@1"

    assert health_response.json()["status"] == "healthy"
    examples = examples_response.json()["examples"]
    assert examples[0]["smoke"] is True
    assert examples[0]["input_artifacts"]["protein"]["files"]["structure_file"]["url"]


def test_remote_tool_v1_template_runs_async_lifecycle_and_cancel():
    service = _load_service_module()
    client = TestClient(service.create_app())

    invoke_response = client.post(
        "/invoke",
        json={
            "request_id": "request-1",
            "task": {"id": "task-1", "tool_slug": "remote-pocket-demo", "tool_version": "1.0.0"},
            "inputs": {},
            "parameters": {"threshold": 0.5},
            "context": {"project_id": "project-1"},
        },
    )

    assert invoke_response.status_code == 200
    run_id = invoke_response.json()["remote_run_id"]
    assert invoke_response.json()["status"] == "queued"

    first_status = client.get(f"/runs/{run_id}").json()
    second_status = client.get(f"/runs/{run_id}").json()
    logs = client.get(f"/runs/{run_id}/logs").json()
    result = client.get(f"/runs/{run_id}/artifacts").json()

    assert first_status["status"] == "running"
    assert second_status["status"] == "success"
    assert logs["items"][0]["message"] == "run accepted"
    assert result["result_version"] == "aidd.sciminer/result.v2"
    assert result["artifacts"]["pocket"]["type"] == "binding_pocket@1"

    cancel_response = client.post(f"/runs/{run_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "canceled"


@pytest.mark.asyncio
async def test_remote_tool_v1_template_runs_through_platform_client_and_executor(
    monkeypatch: pytest.MonkeyPatch,
):
    service = _load_service_module()
    remote_app = service.create_app()
    discovery_transport = httpx.ASGITransport(app=remote_app)

    discovery = await RemoteToolDiscoveryClient(
        "http://remote-tool-template.test",
        transport=discovery_transport,
    ).discover()

    assert discovery.manifest is not None
    assert discovery.examples is not None
    assert discovery.manifest.metadata.slug == "remote-pocket-demo"

    engine, session_factory = await _create_session_factory()

    async def fake_get_async_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr("app.tasks.executors.remote_api.get_async_session", fake_get_async_session)

    executor_transport = httpx.ASGITransport(app=remote_app)
    manifest_payload = discovery.manifest.model_dump(mode="json", by_alias=True)
    config = {
        "type": "remote_api",
        "mode": "remote_tool_v1",
        "base_url": "http://remote-tool-template.test",
        "tool_slug": manifest_payload["metadata"]["slug"],
        "endpoints": manifest_payload["endpoints"],
        "artifacts": manifest_payload["artifacts"],
        "parameters_schema": manifest_payload["parameters_schema"],
        "httpx_transport": executor_transport,
        "timeout_sec": 30,
        "max_polls": 3,
    }
    task = Task(
        id="task-template-e2e",
        user_id="user-1",
        tool_id="tool-1",
        tool_version_id="version-1",
        status=TaskStatus.RUNNING.value,
        extra_data={"project_id": "project-1"},
    )
    task.inputs = TaskInput(
        task_id="task-template-e2e",
        params={"parameters": {"threshold": 0.5}},
        file_ids=[],
    )
    tool_version = ToolVersion(
        id="version-1",
        tool_id="tool-1",
        version="1.0.0",
        config=config,
    )

    try:
        result = await RemoteAPIExecutor(task, tool_version, config=config).execute()

        assert result["success"] is True
        assert result["result"]["result_version"] == "aidd.sciminer/result.v2"
        assert result["output_file_ids"]
        assert task.extra_data["remote_run_id"].startswith("run-")

        async with session_factory() as session:
            file_record = (
                await session.execute(
                    select(FileModel).where(FileModel.id == result["output_file_ids"][0])
                )
            ).scalar_one()

        assert file_record.filename == "residue_pocket.pdb"
        assert Path(file_record.storage_path).read_bytes() == service.RESIDUE_POCKET_BYTES
    finally:
        await engine.dispose()
