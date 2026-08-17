"""remote-tool.v1 executor tests."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from urllib.parse import parse_qs, urlparse

from app.database.base import Base
from app.files.remote_access_tokens import validate_remote_file_access_token
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.files import File as FileModel
from app.models.tools import ToolVersion
from app.models.users import User
from app.tasks.cancellation import cancel_platform_task
from app.tasks.executors.remote_api import RemoteAPIExecutor
from app.tasks.executors.errors import TaskExecutionError


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def remote_tool_config(transport: httpx.AsyncBaseTransport) -> dict:
    return {
        "type": "remote_api",
        "mode": "remote_tool_v1",
        "base_url": "https://model.example.com",
        "endpoints": {
            "invoke": "/invoke",
            "status": "/runs/{remote_run_id}",
            "logs": "/runs/{remote_run_id}/logs",
            "cancel": "/runs/{remote_run_id}/cancel",
            "artifacts": "/runs/{remote_run_id}/artifacts",
        },
        "httpx_transport": transport,
    }


def remote_tool_config_with_artifact_inputs() -> dict:
    return {
        "type": "remote_api",
        "mode": "remote_tool_v1",
        "base_url": "https://model.example.com",
        "platform_base_url": "https://platform.example.com",
        "artifacts": {
            "inputs": [
                {"name": "protein", "type": "protein_structure@1", "required": True},
            ],
            "outputs": [],
        },
    }


def build_task() -> Task:
    task = Task(
        id="task-1",
        user_id="user-1",
        tool_id="tool-1",
        tool_version_id="version-1",
        status=TaskStatus.RUNNING.value,
        extra_data={"project_id": "project-1"},
    )
    task.inputs = TaskInput(
        task_id="task-1",
        params={"threshold": 0.5},
        file_ids=[],
    )
    return task


def build_tool_version(config: dict) -> ToolVersion:
    return ToolVersion(
        id="version-1",
        tool_id="tool-1",
        version="1.0.0",
        config=config,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_remote_tool_executor_invokes_polls_logs_and_collects_artifacts():
    seen_requests: list[tuple[str, str]] = []
    status_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal status_calls
        seen_requests.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/invoke":
            body = await request.aread()
            assert b'"request_id"' in body
            assert b'"threshold":0.5' in body.replace(b" ", b"")
            return httpx.Response(200, json={"remote_run_id": "run-1", "status": "queued"})
        if request.method == "GET" and request.url.path == "/runs/run-1/logs":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"timestamp": "2026-08-17T10:00:00Z", "level": "INFO", "message": "started"}
                    ],
                    "next_cursor": None,
                    "has_more": False,
                },
            )
        if request.method == "GET" and request.url.path == "/runs/run-1":
            status_calls += 1
            if status_calls == 1:
                return httpx.Response(
                    200,
                    json={
                        "remote_run_id": "run-1",
                        "status": "running",
                        "phase": "model_inference",
                        "progress": 45,
                        "message": "Running model",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "remote_run_id": "run-1",
                    "status": "success",
                    "progress": 100,
                    "message": "Done",
                },
            )
        if request.method == "GET" and request.url.path == "/runs/run-1/artifacts":
            return httpx.Response(
                200,
                json={"result_version": "aidd.sciminer/result.v2", "artifacts": [], "relations": []},
            )
        return httpx.Response(404)

    progress: list[tuple[float, str]] = []

    async def progress_callback(value: float, message: str) -> None:
        progress.append((value, message))

    transport = httpx.MockTransport(handler)
    task = build_task()
    executor = RemoteAPIExecutor(
        task,
        build_tool_version(remote_tool_config(transport)),
        config=remote_tool_config(transport),
        progress_callback=progress_callback,
    )

    result = await executor.execute()

    assert result["success"] is True
    assert result["remote_run_id"] == "run-1"
    assert result["result"]["result_version"] == "aidd.sciminer/result.v2"
    assert task.extra_data["remote_run_id"] == "run-1"
    assert ("POST", "/invoke") in seen_requests
    assert ("GET", "/runs/run-1/logs") in seen_requests
    assert ("GET", "/runs/run-1/artifacts") in seen_requests
    assert any(message == "started" for _, message in progress)
    assert progress[-1] == (100.0, "Done")


@pytest.mark.asyncio
async def test_remote_tool_executor_raises_on_remote_failure():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/invoke":
            return httpx.Response(200, json={"remote_run_id": "run-1", "status": "queued"})
        if request.method == "GET" and request.url.path == "/runs/run-1/logs":
            return httpx.Response(200, json={"items": [], "next_cursor": None, "has_more": False})
        if request.method == "GET" and request.url.path == "/runs/run-1":
            return httpx.Response(
                200,
                json={
                    "remote_run_id": "run-1",
                    "status": "failure",
                    "error": {"message": "model crashed"},
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    executor = RemoteAPIExecutor(
        build_task(),
        build_tool_version(remote_tool_config(transport)),
        config=remote_tool_config(transport),
    )

    with pytest.raises(TaskExecutionError) as exc_info:
        await executor.execute()

    assert "model crashed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_remote_tool_executor_can_cancel_remote_run():
    seen_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json={"remote_run_id": "run-1", "status": "canceled"})

    transport = httpx.MockTransport(handler)
    task = build_task()
    task.extra_data = {"remote_run_id": "run-1"}
    executor = RemoteAPIExecutor(
        task,
        build_tool_version(remote_tool_config(transport)),
        config=remote_tool_config(transport),
    )

    result = await executor.cancel_remote_run()

    assert result["status"] == "canceled"
    assert seen_paths == ["/runs/run-1/cancel"]


@pytest.mark.asyncio
async def test_remote_tool_executor_copies_result_files_to_platform_storage(
    db_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/invoke":
            return httpx.Response(200, json={"remote_run_id": "run-1", "status": "queued"})
        if request.method == "GET" and request.url.path == "/runs/run-1/logs":
            return httpx.Response(200, json={"items": [], "next_cursor": None, "has_more": False})
        if request.method == "GET" and request.url.path == "/runs/run-1":
            return httpx.Response(200, json={"remote_run_id": "run-1", "status": "success"})
        if request.method == "GET" and request.url.path == "/runs/run-1/artifacts":
            return httpx.Response(
                200,
                json={
                    "result_version": "aidd.sciminer/result.v2",
                    "artifacts": [
                        {
                            "ref": "pocket",
                            "type": "binding_pocket@1",
                            "files": {
                                "pdb": {
                                    "path": "output/pocket.pdb",
                                    "url": "/runs/run-1/files/output/pocket.pdb",
                                    "sha256": "fdda3539d63f1ec143ad7b54774b89be75ddfa1f4c3b5e33a41e8900e4589314",
                                    "content_type": "chemical/x-pdb",
                                }
                            },
                            "metadata": {},
                        }
                    ],
                    "relations": [],
                },
            )
        if request.method == "GET" and request.url.path == "/runs/run-1/files/output/pocket.pdb":
            return httpx.Response(200, content=b"POCKET")
        return httpx.Response(404)

    async def fake_get_async_session():
        yield db_session

    def fake_get_file_path(file_id: str, filename: str):
        return tmp_path / f"{file_id}_{filename}"

    monkeypatch.setattr("app.tasks.executors.remote_api.get_async_session", fake_get_async_session)
    monkeypatch.setattr("app.tasks.executors.remote_api.get_file_path", fake_get_file_path)

    transport = httpx.MockTransport(handler)
    executor = RemoteAPIExecutor(
        build_task(),
        build_tool_version(remote_tool_config(transport)),
        config=remote_tool_config(transport),
    )

    result = await executor.execute()

    assert len(result["output_file_ids"]) == 1
    file_record = await db_session.get(FileModel, result["output_file_ids"][0])
    assert file_record is not None
    assert file_record.filename == "pocket.pdb"
    assert file_record.sha256 == "fdda3539d63f1ec143ad7b54774b89be75ddfa1f4c3b5e33a41e8900e4589314"
    assert result["result"]["artifacts"][0]["files"]["pdb"]["file_id"] == file_record.id


@pytest.mark.asyncio
async def test_remote_tool_executor_copies_standard_dict_result_files(
    db_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/invoke":
            return httpx.Response(200, json={"remote_run_id": "run-1", "status": "queued"})
        if request.method == "GET" and request.url.path == "/runs/run-1/logs":
            return httpx.Response(200, json={"items": [], "next_cursor": None, "has_more": False})
        if request.method == "GET" and request.url.path == "/runs/run-1":
            return httpx.Response(200, json={"remote_run_id": "run-1", "status": "success"})
        if request.method == "GET" and request.url.path == "/runs/run-1/artifacts":
            return httpx.Response(
                200,
                json={
                    "result_version": "aidd.sciminer/result.v2",
                    "artifacts": {
                        "report": {
                            "name": "Run report",
                            "type": "run_report@1",
                            "files": {
                                "report_json": {
                                    "path": "reports/report.json",
                                    "url": "/runs/run-1/files/reports/report.json",
                                    "sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
                                    "content_type": "application/json",
                                }
                            },
                        }
                    },
                    "relations": [],
                },
            )
        if request.method == "GET" and request.url.path == "/runs/run-1/files/reports/report.json":
            return httpx.Response(200, content=b"{}")
        return httpx.Response(404)

    async def fake_get_async_session():
        yield db_session

    def fake_get_file_path(file_id: str, filename: str):
        return tmp_path / f"{file_id}_{filename}"

    monkeypatch.setattr("app.tasks.executors.remote_api.get_async_session", fake_get_async_session)
    monkeypatch.setattr("app.tasks.executors.remote_api.get_file_path", fake_get_file_path)

    transport = httpx.MockTransport(handler)
    executor = RemoteAPIExecutor(
        build_task(),
        build_tool_version(remote_tool_config(transport)),
        config=remote_tool_config(transport),
    )

    result = await executor.execute()

    assert len(result["output_file_ids"]) == 1
    file_record = await db_session.get(FileModel, result["output_file_ids"][0])
    assert file_record.file_meta["relative_path"] == "reports/report.json"
    assert result["result"]["artifacts"]["report"]["files"]["report_json"]["file_id"] == file_record.id


@pytest.mark.asyncio
async def test_remote_tool_invoke_payload_includes_signed_artifact_input_urls(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_async_session():
        yield db_session

    monkeypatch.setattr("app.tasks.executors.remote_api.get_async_session", fake_get_async_session)
    user = User(
        id="user-1",
        email="remote-input@example.com",
        password_hash="hashed",
    )
    db_session.add(user)
    structure_file = FileModel(
        id="file-structure",
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=12,
        sha256="c" * 64,
        storage_path="/tmp/protein.pdb",
        owner_id="user-1",
        is_public=False,
    )
    metadata_file = FileModel(
        id="file-metadata",
        filename="metadata.json",
        content_type="application/json",
        size_bytes=2,
        sha256="d" * 64,
        storage_path="/tmp/metadata.json",
        owner_id="user-1",
        is_public=False,
    )
    artifact = Artifact(
        id="artifact-1",
        project_id="project-1",
        created_by="user-1",
        artifact_type="protein_structure",
        semantic_type="protein_structure@1",
        standard_type="protein_structure",
        standard_version=1,
        name="Protein",
    )
    artifact_version = ArtifactVersion(
        id="artifact-version-1",
        artifact_id="artifact-1",
        created_by="user-1",
        version=1,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=12,
        sha256="c" * 64,
        storage_key="protein.pdb",
        status="available",
        manifest_json={"type": "protein_structure@1", "metadata": {"chain": "A"}},
    )
    structure_link = ArtifactVersionFile(
        artifact_version_id="artifact-version-1",
        role="structure_file",
        file_id="file-structure",
        is_primary=True,
        sort_order=0,
    )
    metadata_link = ArtifactVersionFile(
        artifact_version_id="artifact-version-1",
        role="metadata_json",
        file_id="file-metadata",
        is_primary=False,
        sort_order=1,
    )
    db_session.add_all([
        structure_file,
        metadata_file,
        artifact,
        artifact_version,
        structure_link,
        metadata_link,
    ])
    await db_session.commit()

    task = build_task()
    task.extra_data = {
        "project_id": "project-1",
        "input_bindings": {"protein": "artifact-version-1"},
    }
    executor = RemoteAPIExecutor(
        task,
        build_tool_version(remote_tool_config_with_artifact_inputs()),
    )

    payload = await executor._remote_tool_invoke_payload()
    file_payload = payload["inputs"]["protein"]["files"]["structure_file"]
    parsed = urlparse(file_payload["url"])
    token = parse_qs(parsed.query)["token"][0]

    assert payload["inputs"]["protein"]["artifact_version_id"] == "artifact-version-1"
    assert payload["inputs"]["protein"]["type"] == "protein_structure@1"
    assert payload["inputs"]["protein"]["metadata"] == {"chain": "A"}
    assert file_payload["url"].startswith("https://platform.example.com/api/v1/files/file-structure/download")
    assert file_payload["filename"] == "protein.pdb"
    assert file_payload["sha256"] == "c" * 64
    assert file_payload["content_type"] == "chemical/x-pdb"
    assert "metadata_json" in payload["inputs"]["protein"]["files"]
    assert validate_remote_file_access_token(
        token,
        file_id="file-structure",
        task_id="task-1",
    )["file_id"] == "file-structure"


@pytest.mark.asyncio
async def test_remote_tool_invoke_payload_uses_materialized_smoke_example_inputs(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_async_session():
        yield db_session

    monkeypatch.setattr("app.tasks.executors.remote_api.get_async_session", fake_get_async_session)
    db_session.add(
        FileModel(
            id="file-smoke-structure",
            filename="protein.pdb",
            content_type="chemical/x-pdb",
            size_bytes=12,
            sha256="e" * 64,
            storage_path="/tmp/protein.pdb",
            owner_id="user-1",
            is_public=False,
        )
    )
    await db_session.commit()
    task = build_task()
    task.extra_data = {
        "remote_example_inputs": {
            "protein": {
                "type": "protein_structure@1",
                "metadata": {"chain_ids": ["A"]},
                "files": {"structure_file": "file-smoke-structure"},
            }
        }
    }
    executor = RemoteAPIExecutor(
        task,
        build_tool_version(remote_tool_config_with_artifact_inputs()),
    )

    payload = await executor._remote_tool_invoke_payload()
    file_payload = payload["inputs"]["protein"]["files"]["structure_file"]

    assert payload["inputs"]["protein"]["type"] == "protein_structure@1"
    assert payload["inputs"]["protein"]["metadata"] == {"chain_ids": ["A"]}
    assert "token=" in file_payload["url"]
    assert file_payload["filename"] == "protein.pdb"


@pytest.mark.asyncio
async def test_cancel_platform_task_calls_remote_cancel_for_remote_tool(monkeypatch: pytest.MonkeyPatch):
    task = build_task()
    config = remote_tool_config(httpx.MockTransport(lambda _request: httpx.Response(200)))
    task.tool_version = build_tool_version(config)
    task.extra_data = {"remote_run_id": "run-1"}
    current_user = User(id="user-1", role="user")
    calls: list[str] = []

    class FakeRemoteAPIExecutor:
        def __init__(self, task: Task, tool_version: ToolVersion, config: dict):
            calls.append(str(task.id))
            assert tool_version.version == "1.0.0"
            assert config["mode"] == "remote_tool_v1"

        async def cancel_remote_run(self):
            return {"status": "canceled"}

    class FakeDirectRunner:
        def cancel_task(self, task_id: str) -> bool:
            return True

    monkeypatch.setattr("app.tasks.cancellation.use_direct_task_execution", lambda: True)
    monkeypatch.setattr("app.tasks.cancellation.RemoteAPIExecutor", FakeRemoteAPIExecutor)

    canceled = await cancel_platform_task(
        None,
        task=task,
        current_user=current_user,
        direct_runner=FakeDirectRunner(),
    )

    assert canceled is True
    assert calls == ["task-1"]
    assert task.status == TaskStatus.CANCELED.value
