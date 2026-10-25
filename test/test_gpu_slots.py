"""卡位（slot）调度测试。

覆盖 `docs/09` §5.5~§5.6 与 `docs/13` §4.1~§4.4 的可验证契约：

* ``slots.yaml`` 解析、校验（DCU 挂载、``--gpus`` + ``CUDA_VISIBLE_DEVICES`` 陷阱、重复卡位）。
* 卡位状态机与 ``device_count()!=1 → FAULT`` 铁律。
* 分配器按卡位声明发现节点（生产形态），未声明时回退本机探测。
* ``GPUAllocation`` 写入卡位追溯字段。
* Agent 客户端与上报端点（含 token 缺失/错误/未启用）。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1 import gpu as gpu_api
from app.auth.dependencies import get_current_user
from app.cache.factory import get_cache_backend
from app.config import settings
from app.database.base import Base
from app.database.session import get_db
from app.gpu import slots as slot_module
from app.gpu.allocator import GPUAllocator
from app.gpu.node_agent import AgentJobRequest, NodeAgentClient, NodeAgentError
from app.gpu.slots import (
    SLOT_STATE_BUSY,
    SLOT_STATE_FAULT,
    SLOT_STATE_FREE,
    SlotConfigError,
    load_slot_registry,
    load_slot_states,
    parse_slot_document,
    record_slot_state,
    schedulable_node_view,
    slot_view,
)
from app.models.gpu import GPUAllocation, GPUAllocationStatus
from app.models.tasks import Task, TaskPriority, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole

DCU_SLOTS_YAML = """
schemaVersion: 2
nodes:
  - nodeId: dcu-node-a
    hostname: dcu-a.local
    agentEndpoint: http://dcu-a.local:8780
    accelerator:
      model: Hygon K100-AI
      count: 8
    slots:
      - id: A1
        deviceIds: [0]
        memoryMb: 65536
        image: harbor.local/drp/compute-boltz2:2.0.1-dtk26.04
        env:
          ROCR_VISIBLE_DEVICES: "0"
          HIP_VISIBLE_DEVICES: "0"
        dockerArgs:
          - --device=/dev/kfd
          - --device=/dev/dri
          - --group-add
          - video
        models: [boltz-2, lvpocket]
      - id: A2
        deviceIds: [1]
        memoryMb: 65536
        env:
          ROCR_VISIBLE_DEVICES: "1"
          HIP_VISIBLE_DEVICES: "1"
        dockerArgs:
          - --device=/dev/kfd
          - --device=/dev/dri
  - nodeId: nvidia-node-b
    agentEndpoint: http://nvidia-b.local:8780
    accelerator:
      model: NVIDIA RTX 4090
      count: 8
    slots:
      - id: B1
        deviceIds: [6]
        env:
          NVIDIA_VISIBLE_DEVICES: "6"
          CUDA_VISIBLE_DEVICES: "0"
        dockerArgs: [--gpus, device=6, --ipc=host]
"""


# ---------------------------------------------------------------- fixtures


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def memory_cache():
    """每个用例用干净的内存缓存（``get_cache_backend`` 是单例，必须显式清空）。"""
    cache = get_cache_backend("memory")
    await cache.clear()
    yield cache
    await cache.clear()


@pytest.fixture
def patched_slots_yaml(monkeypatch):
    def _apply(raw: str | None):
        monkeypatch.setattr(settings, "DRP_NODE_SLOTS_YAML", raw, raising=False)
        monkeypatch.setattr(settings, "DRP_NODE_SLOTS_FILE", None, raising=False)

    return _apply


async def _make_tool(db: AsyncSession, owner_id: str, *, suffix: str = "") -> Tool:
    tool = Tool(
        owner_id=owner_id,
        name=f"Boltz-2{suffix}",
        slug=f"boltz-2{suffix}",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="2.0.1",
        config={"type": "ssh_job", "gpu_required": True, "gpu_memory_required_mb": 8192},
        is_active=True,
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    await db.flush()
    return tool


async def _make_task(db: AsyncSession, owner_id: str, *, suffix: str = "") -> Task:
    tool = await _make_tool(db, owner_id, suffix=suffix)
    task = Task(
        user_id=owner_id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        name=f"boltz-2 run{suffix}",
        status=TaskStatus.PENDING.value,
        priority=TaskPriority.NORMAL.value,
    )
    db.add(task)
    await db.flush()
    return task


# ---------------------------------------------------------------- 解析与校验


def test_parse_dcu_and_nvidia_slots():
    registry = parse_slot_document(slot_module.yaml.safe_load(DCU_SLOTS_YAML), source="test")

    assert [node.node_id for node in registry.nodes] == ["dcu-node-a", "nvidia-node-b"]
    assert len(registry.slots) == 3

    dcu_slot = registry.find("dcu-node-a", "A1")
    assert dcu_slot is not None
    assert dcu_slot.identifier == "dcu-node-a/A1"
    assert dcu_slot.vendor == "haiguang-dcu"
    assert dcu_slot.gpu_index == 0
    assert dcu_slot.visible_device == "0"
    assert dcu_slot.memory_mb == 65536
    assert dcu_slot.models == ("boltz-2", "lvpocket")
    assert dcu_slot.image == "harbor.local/drp/compute-boltz2:2.0.1-dtk26.04"

    # A2 未声明 image / models，允许继承节点默认值（镜像随部署注入，卡位级别才显式指定）
    a2 = registry.find("dcu-node-a", "A2")
    assert a2 is not None and a2.memory_mb == 65536 and a2.image is None
    assert a2.models == ()
    assert a2.accelerator_model == "Hygon K100-AI"

    nvidia = registry.find("nvidia-node-b", "B1")
    assert nvidia is not None
    assert nvidia.vendor == "nvidia-cuda"
    # 宿主卡号 6 进 gpu_index（与 gpu_allocations.gpu_index 语义一致）
    assert nvidia.gpu_index == 6
    # 容器内序号必须是 0
    assert nvidia.visible_device == "0"


def test_parse_rejects_gpus_flag_with_host_index_visible_device():
    """`docs/09` §5.6 v1.4 实测陷阱：--gpus device=6 + CUDA_VISIBLE_DEVICES=6 → device_count()==0。"""
    payload = {
        "schemaVersion": 2,
        "nodeId": "bad-node",
        "slots": [
            {
                "id": "X1",
                "deviceIds": [6],
                "env": {"NVIDIA_VISIBLE_DEVICES": "6", "CUDA_VISIBLE_DEVICES": "6"},
                "dockerArgs": ["--gpus", "device=6"],
            }
        ],
    }
    with pytest.raises(SlotConfigError, match="CUDA_VISIBLE_DEVICES"):
        parse_slot_document(payload)


def test_parse_accepts_gpus_flag_without_cuda_visible_devices():
    payload = {
        "schemaVersion": 2,
        "nodeId": "ok-node",
        "slots": [{"id": "X1", "deviceIds": [3], "dockerArgs": ["--gpus", "device=3"]}],
    }
    registry = parse_slot_document(payload)
    slot = registry.find("ok-node", "X1")
    assert slot is not None and slot.visible_device is None


def test_parse_rejects_dcu_slot_without_device_mounts():
    payload = {
        "schemaVersion": 2,
        "nodeId": "dcu-node",
        "slots": [
            {
                "id": "A1",
                "deviceIds": [0],
                "env": {"ROCR_VISIBLE_DEVICES": "0"},
                "dockerArgs": [],
            }
        ],
    }
    with pytest.raises(SlotConfigError, match="dockerArgs"):
        parse_slot_document(payload)


def test_parse_rejects_duplicate_slot_ids():
    payload = {
        "schemaVersion": 2,
        "nodeId": "dup-node",
        "slots": [{"id": "A1", "deviceIds": [0]}, {"id": "A1", "deviceIds": [1]}],
    }
    with pytest.raises(SlotConfigError, match="卡位 id 重复"):
        parse_slot_document(payload)


def test_parse_rejects_unknown_schema_version():
    with pytest.raises(SlotConfigError, match="schemaVersion"):
        parse_slot_document({"schemaVersion": 1, "nodeId": "n", "slots": [{"id": "A1"}]})


def test_parse_rejects_node_without_slots():
    with pytest.raises(SlotConfigError, match="没有声明任何卡位"):
        parse_slot_document({"schemaVersion": 2, "nodeId": "empty", "slots": []})


def test_load_registry_returns_empty_when_unconfigured(patched_slots_yaml):
    patched_slots_yaml(None)
    registry = load_slot_registry()
    assert registry.nodes == ()
    assert registry.slots == ()


def test_load_registry_reads_inline_yaml(patched_slots_yaml):
    patched_slots_yaml(DCU_SLOTS_YAML)
    registry = load_slot_registry()
    assert len(registry.nodes) == 2
    assert registry.source.startswith("settings:")


def test_slots_for_model_includes_generic_slots(patched_slots_yaml):
    patched_slots_yaml(DCU_SLOTS_YAML)
    registry = load_slot_registry()
    # boltz-2 只被 A1 点名，但通用卡位（A2/B1，models 为空）也应可用
    matched = {slot.identifier for slot in registry.slots_for_model("boltz-2")}
    assert matched == {"dcu-node-a/A1", "dcu-node-a/A2", "nvidia-node-b/B1"}
    # 未在任何卡位点名的模型仍能落到通用卡位
    assert len(registry.slots_for_model("std-diff")) == 2


# ---------------------------------------------------------------- 卡位状态


@pytest.mark.asyncio
async def test_record_slot_state_marks_fault_when_device_count_is_not_one():
    record = await record_slot_state(
        node_id="dcu-node-a",
        slot_id="A1",
        state=SLOT_STATE_BUSY,
        device_count=0,
        cache_client=get_cache_backend("memory"),
    )
    assert record["state"] == SLOT_STATE_FAULT
    assert "device_count()=0" in record["message"]


@pytest.mark.asyncio
async def test_record_slot_state_keeps_state_when_device_count_is_one():
    record = await record_slot_state(
        node_id="dcu-node-a",
        slot_id="A1",
        state=SLOT_STATE_BUSY,
        device_count=1,
        cache_client=get_cache_backend("memory"),
    )
    assert record["state"] == SLOT_STATE_BUSY


@pytest.mark.asyncio
async def test_record_slot_state_rejects_unknown_state():
    with pytest.raises(SlotConfigError):
        await record_slot_state(
            node_id="n",
            slot_id="A1",
            state="IDLE",
            cache_client=get_cache_backend("memory"),
        )


@pytest.mark.asyncio
async def test_load_slot_states_defaults_to_free(patched_slots_yaml):
    patched_slots_yaml(DCU_SLOTS_YAML)
    registry = load_slot_registry()
    states = await load_slot_states(registry, cache_client=get_cache_backend("memory"))
    assert set(states) == {"dcu-node-a/A1", "dcu-node-a/A2", "nvidia-node-b/B1"}
    assert {record["state"] for record in states.values()} == {SLOT_STATE_FREE}


@pytest.mark.asyncio
async def test_schedulable_node_view_excludes_non_free_slots(patched_slots_yaml):
    patched_slots_yaml(DCU_SLOTS_YAML)
    registry = load_slot_registry()
    cache = get_cache_backend("memory")
    await record_slot_state(
        node_id="dcu-node-a", slot_id="A1", state=SLOT_STATE_BUSY, cache_client=cache
    )

    nodes = await schedulable_node_view(registry, cache_client=cache)
    by_id = {node["id"]: node for node in nodes}
    assert set(by_id) == {"dcu-node-a", "nvidia-node-b"}
    assert [gpu["slot_id"] for gpu in by_id["dcu-node-a"]["gpus"]] == ["A2"]
    assert by_id["dcu-node-a"]["agent_endpoint"] == "http://dcu-a.local:8780"
    assert by_id["dcu-node-a"]["gpus"][0]["accelerator_model"] == "Hygon K100-AI"


@pytest.mark.asyncio
async def test_slot_view_reports_states(patched_slots_yaml):
    patched_slots_yaml(DCU_SLOTS_YAML)
    registry = load_slot_registry()
    cache = get_cache_backend("memory")
    await record_slot_state(
        node_id="nvidia-node-b", slot_id="B1", state=SLOT_STATE_FAULT, cache_client=cache
    )

    states = await load_slot_states(registry, cache_client=cache)
    nodes = slot_view(registry, states)
    nvidia = next(node for node in nodes if node["nodeId"] == "nvidia-node-b")
    assert nvidia["schedulableSlotCount"] == 0
    assert nvidia["slots"][0]["state"] == SLOT_STATE_FAULT
    assert nvidia["slots"][0]["schedulable"] is False


# ---------------------------------------------------------------- 分配器


@pytest.mark.asyncio
async def test_allocator_discovers_slot_nodes(db_session, patched_slots_yaml):
    patched_slots_yaml(DCU_SLOTS_YAML)
    owner = User(email="slot-owner@example.com", password_hash="x", role=UserRole.USER.value)
    db_session.add(owner)
    await db_session.flush()

    allocator = GPUAllocator(db=db_session, cache_client=get_cache_backend("memory"))
    nodes = await allocator._get_slot_nodes()

    assert {node["id"] for node in nodes} == {"dcu-node-a", "nvidia-node-b"}
    assert all(node["source"] == "slots" for node in nodes)
    assert nodes[0]["gpus"][0]["slot_id"] == "A1"


@pytest.mark.asyncio
async def test_allocator_allocates_slot_and_persists_trace_fields(
    db_session, patched_slots_yaml
):
    patched_slots_yaml(DCU_SLOTS_YAML)
    owner = User(email="slot-owner2@example.com", password_hash="x", role=UserRole.USER.value)
    db_session.add(owner)
    await db_session.flush()
    task = await _make_task(db_session, owner.id)
    await db_session.commit()

    allocator = GPUAllocator(db=db_session, cache_client=get_cache_backend("memory"))
    result = await allocator.allocate(task_id=task.id, memory_required_mb=8192)
    await db_session.commit()

    assert result.success is True
    assert result.gpu_node_id == "dcu-node-a"
    assert result.slot_id == "A1"
    assert result.slot_identifier == "dcu-node-a/A1"
    assert result.accelerator_vendor == "haiguang-dcu"
    assert result.image_ref == "harbor.local/drp/compute-boltz2:2.0.1-dtk26.04"
    assert result.agent_endpoint == "http://dcu-a.local:8780"

    allocation = await db_session.get(GPUAllocation, result.allocation_id)
    assert allocation is not None
    assert allocation.status == GPUAllocationStatus.ACTIVE.value
    assert allocation.slot_id == "A1"
    assert allocation.accelerator_model == "Hygon K100-AI"
    assert allocation.accelerator_vendor == "haiguang-dcu"
    assert allocation.device_ids == "0"
    assert allocation.image_ref == "harbor.local/drp/compute-boltz2:2.0.1-dtk26.04"

    refreshed = await db_session.get(Task, task.id)
    assert refreshed is not None
    # 分配器用 `update(Task).values(...)` 直接写库，内存对象不会自动同步
    await db_session.refresh(refreshed)
    assert refreshed.gpu_node_id == "dcu-node-a"
    assert refreshed.gpu_index == 0


@pytest.mark.asyncio
async def test_allocation_stats_expose_slot_trace_fields(db_session, patched_slots_yaml):
    """P-36 算力页分配表依赖卡位追溯字段，摘要必须真的带出来。"""
    patched_slots_yaml(DCU_SLOTS_YAML)
    owner = User(email="slot-owner-stats@example.com", password_hash="x", role=UserRole.USER.value)
    db_session.add(owner)
    await db_session.flush()
    task = await _make_task(db_session, owner.id)
    await db_session.commit()

    allocator = GPUAllocator(db=db_session, cache_client=get_cache_backend("memory"))
    result = await allocator.allocate(task_id=task.id, memory_required_mb=8192)
    await db_session.commit()
    assert result.success is True

    stats = await allocator.get_allocation_stats()
    summary = stats["allocations"][0]

    assert summary["allocation_id"] == result.allocation_id
    assert summary["task_id"] == task.id
    assert summary["slot_id"] == "A1"
    assert summary["accelerator_model"] == "Hygon K100-AI"
    assert summary["accelerator_vendor"] == "haiguang-dcu"
    assert summary["gpu_node_id"] == "dcu-node-a"
    assert summary["gpu_index"] == 0
    assert summary["status"] == GPUAllocationStatus.ACTIVE.value
    assert isinstance(summary["allocated_at"], str)
    assert summary["allocated_at"]


@pytest.mark.asyncio
async def test_allocator_skips_busy_slot(db_session, patched_slots_yaml):
    patched_slots_yaml(DCU_SLOTS_YAML)
    owner = User(email="slot-owner3@example.com", password_hash="x", role=UserRole.USER.value)
    db_session.add(owner)
    await db_session.flush()
    first = await _make_task(db_session, owner.id)
    second = await _make_task(db_session, owner.id, suffix="-b")
    await db_session.commit()

    cache = get_cache_backend("memory")
    allocator = GPUAllocator(db=db_session, cache_client=cache)

    first_result = await allocator.allocate(task_id=first.id, memory_required_mb=8192)
    await db_session.commit()
    assert first_result.success is True

    # A1 已被活动租约占用，下一次应落到 A2
    second_result = await allocator.allocate(task_id=second.id, memory_required_mb=8192)
    await db_session.commit()
    assert second_result.success is True
    assert second_result.slot_id == "A2"
    assert second_result.slot_identifier == "dcu-node-a/A2"


@pytest.mark.asyncio
async def test_allocator_falls_back_to_local_probe_without_slots(db_session, patched_slots_yaml):
    patched_slots_yaml(None)
    allocator = GPUAllocator(db=db_session, cache_client=get_cache_backend("memory"))
    assert await allocator._get_slot_nodes() == []


# ---------------------------------------------------------------- Agent 客户端


@pytest.mark.asyncio
async def test_agent_client_submits_job():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"jobId": "job-123"})

    client = NodeAgentClient(
        "http://dcu-a.local:8780",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )
    job_id = await client.submit(
        AgentJobRequest(
            task_id="task-1",
            slot_id="A1",
            image="harbor.local/drp/compute-boltz2:2.0.1-dtk26.04",
            model_entry=("/opt/model/run.sh", "--task", "task-1"),
            env={"DRP_DEVICE": "cuda:0"},
            docker_args=("--device=/dev/kfd",),
            max_minutes=240,
        )
    )

    assert job_id == "job-123"
    assert captured["url"] == "http://dcu-a.local:8780/api/v1/jobs"
    assert captured["auth"] == "Bearer secret-token"
    body = captured["body"]
    assert body["taskId"] == "task-1"
    assert body["slotId"] == "A1"
    assert body["modelEntry"] == ["/opt/model/run.sh", "--task", "task-1"]
    assert body["maxMinutes"] == 240


@pytest.mark.asyncio
async def test_agent_client_cancel_and_status():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(":cancel"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(
            200,
            json={
                "jobId": "job-9",
                "state": "succeeded",
                "slotId": "A3",
                "progress": 100,
                "exitCode": 0,
                "deviceCount": 1,
            },
        )

    client = NodeAgentClient("http://agent.local:8780", transport=httpx.MockTransport(handler))
    await client.cancel("job-9", reason="用户取消")
    status = await client.status("job-9")

    assert status.job_id == "job-9"
    assert status.state == "SUCCEEDED"
    assert status.terminal is True
    assert status.device_count == 1


@pytest.mark.asyncio
async def test_agent_client_requires_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "DRP_NODE_AGENT_BASE_URL", None, raising=False)
    client = NodeAgentClient(None)
    assert client.configured is False
    with pytest.raises(NodeAgentError, match="未配置"):
        await client.status("job-1")


@pytest.mark.asyncio
async def test_agent_client_surfaces_http_errors():
    client = NodeAgentClient(
        "http://agent.local:8780",
        transport=httpx.MockTransport(lambda request: httpx.Response(503, text="busy")),
    )
    with pytest.raises(NodeAgentError, match="503"):
        await client.status("job-1")


# ---------------------------------------------------------------- 上报端点


@pytest_asyncio.fixture
async def slot_api_client(db_session, patched_slots_yaml):
    patched_slots_yaml(DCU_SLOTS_YAML)
    app = FastAPI()
    app.include_router(gpu_api.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: object()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_slot_view_endpoint_lists_declared_slots(slot_api_client):
    response = await slot_api_client.get("/api/v1/gpu/slots")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["configured"] is True
    assert payload["nodeCount"] == 2
    assert payload["slotCount"] == 3
    assert payload["schedulableSlotCount"] == 3


@pytest.mark.asyncio
async def test_report_endpoint_is_disabled_without_token(slot_api_client, monkeypatch):
    monkeypatch.setattr(settings, "DRP_NODE_AGENT_REPORT_TOKEN", None, raising=False)
    response = await slot_api_client.post(
        "/api/v1/gpu/slots/report",
        json={"nodeId": "dcu-node-a", "slotId": "A1", "state": "BUSY"},
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_report_endpoint_rejects_wrong_token(slot_api_client, monkeypatch):
    monkeypatch.setattr(settings, "DRP_NODE_AGENT_REPORT_TOKEN", "report-secret", raising=False)
    response = await slot_api_client.post(
        "/api/v1/gpu/slots/report",
        json={"nodeId": "dcu-node-a", "slotId": "A1", "state": "BUSY"},
        headers={"X-DRP-Agent-Token": "nope"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_report_endpoint_records_state(slot_api_client, monkeypatch):
    monkeypatch.setattr(settings, "DRP_NODE_AGENT_REPORT_TOKEN", "report-secret", raising=False)
    response = await slot_api_client.post(
        "/api/v1/gpu/slots/report",
        json={
            "nodeId": "dcu-node-a",
            "slotId": "A1",
            "state": "BUSY",
            "deviceCount": 1,
        },
        headers={"X-DRP-Agent-Token": "report-secret"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "BUSY"

    view = await slot_api_client.get("/api/v1/gpu/slots")
    node = next(n for n in view.json()["data"]["nodes"] if n["nodeId"] == "dcu-node-a")
    slot = next(s for s in node["slots"] if s["slotId"] == "A1")
    assert slot["state"] == "BUSY"
    assert slot["schedulable"] is False


@pytest.mark.asyncio
async def test_report_endpoint_flags_fault_on_bad_device_count(slot_api_client, monkeypatch):
    monkeypatch.setattr(settings, "DRP_NODE_AGENT_REPORT_TOKEN", "report-secret", raising=False)
    response = await slot_api_client.post(
        "/api/v1/gpu/slots/report",
        json={
            "nodeId": "dcu-node-a",
            "slotId": "A1",
            "state": "BUSY",
            "deviceCount": 0,
        },
        headers={"X-DRP-Agent-Token": "report-secret"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == SLOT_STATE_FAULT


@pytest.mark.asyncio
async def test_report_endpoint_rejects_undeclared_slot(slot_api_client, monkeypatch):
    monkeypatch.setattr(settings, "DRP_NODE_AGENT_REPORT_TOKEN", "report-secret", raising=False)
    response = await slot_api_client.post(
        "/api/v1/gpu/slots/report",
        json={"nodeId": "dcu-node-a", "slotId": "Z9", "state": "FREE"},
        headers={"X-DRP-Agent-Token": "report-secret"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_report_endpoint_rejects_unknown_state(slot_api_client, monkeypatch):
    monkeypatch.setattr(settings, "DRP_NODE_AGENT_REPORT_TOKEN", "report-secret", raising=False)
    response = await slot_api_client.post(
        "/api/v1/gpu/slots/report",
        json={"nodeId": "dcu-node-a", "slotId": "A1", "state": "IDLE"},
        headers={"X-DRP-Agent-Token": "report-secret"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------- 随仓交付的声明文件


def test_shipped_slots_example_parses():
    """`deploy/slots/slots.example.yaml` 必须始终可解析——它是运维照抄的模板。"""
    example = Path(__file__).resolve().parents[1] / "deploy" / "slots" / "slots.example.yaml"
    assert example.exists()

    registry = load_slot_registry(example.read_text(encoding="utf-8"))

    assert registry.schema_version == 2
    assert len(registry.nodes) >= 1
    dcu_node = registry.node("dcu-node-01")
    assert dcu_node is not None and len(dcu_node.slots) == 8
    # 每个 DCU 卡位都必须挂驱动设备节点且容器内序号为 0
    for slot in dcu_node.slots:
        assert slot.vendor == "haiguang-dcu"
        assert "--device=/dev/kfd" in slot.docker_args
        assert slot.visible_device == "0" or slot.visible_device == str(slot.gpu_index)
    # 通用卡位（未点名模型）至少存在一个，保证新模型不用改声明就能跑
    assert any(not slot.models for slot in dcu_node.slots)


def test_slot_identifier_is_stable_across_lookups():
    registry = load_slot_registry(
        (Path(__file__).resolve().parents[1] / "deploy" / "slots" / "slots.example.yaml").read_text(
            encoding="utf-8"
        )
    )
    slot = registry.find_by_identifier("dcu-node-01/A3")
    assert slot is not None
    assert slot.identifier == "dcu-node-01/A3"
    assert slot.gpu_index == 2
