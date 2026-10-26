"""工作流启动端点的请求级幂等（``X-Idempotency-Key``，docs/05 §12）。

为什么单独一个文件
------------------
``test/test_idempotency.py`` 覆盖的是 ``POST /api/v1/tasks`` 这一条路径上的幂等
语义（重放、40905、40904、失败重试……）。本文件只回答一个不同的问题：**同一个
幂等机制挂到 ``POST /api/v1/workflows/{id}/runs`` 上还成不成立**。

一次工作流运行会按节点展开成多个任务，重复提交的代价比重复建一个任务高得多，
所以这个端点必须幂等地覆盖。这里验证的是「机制复用正确」，而不是重新验证机制本身：

1. 同键同体只落一条 ``WorkflowRun``；
2. 同键异体（换了 ``input_files``）被 40905 拦住；
3. 不带键完全透传，两次都建（幂等是增强，不是前置条件）；
4. **scope 用路径模板**：同一个键分别打在两个不同工作流上也能被 40905 拦住，
   这正是 ``path_template`` 必须写模板而不是真实路径的原因——若把 ``workflow_id``
   拼进 scope，两个工作流就变成两个互不相干的作用域，误用永远发现不了；
5. 端点仍然要求认证（装饰器不会把鉴权绕过去）。

测试隔离方式与 ``test/test_workflow_persistence_api.py`` 一致：内存 SQLite +
覆盖 ``get_db`` / ``get_current_user``，并把任务调度换成不落地的桩。
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import get_current_user  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models.idempotency import IdempotencyKey  # noqa: E402
from app.models.tasks import Task, TaskInput, TaskStatus  # noqa: E402
from app.models.tools import Tool  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.models.workflows import WorkflowRun  # noqa: E402

OWNER_TOKEN = "owner-token"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _create_user(db: AsyncSession, email: str = "owner@example.com") -> User:
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
async def owner(db_session: AsyncSession) -> User:
    return await _create_user(db_session)


async def _fake_scheduled_task(*, db, current_user, task_data, direct_runner=None):
    """不落地的调度桩：只把任务写进会话，不真的执行。"""
    tool = await db.get(Tool, task_data.tool_id)
    task = Task(
        user_id=current_user.id,
        tool_id=task_data.tool_id,
        tool_version_id=task_data.tool_version_id or tool.current_version_id,
        name=task_data.name,
        status=TaskStatus.PENDING.value,
        progress=0.0,
        priority=task_data.priority,
        extra_data={"project_id": task_data.project_id} if task_data.project_id else {},
    )
    db.add(task)
    await db.flush()
    db.add(
        TaskInput(
            task_id=task.id,
            params=task_data.params,
            file_ids=task_data.file_ids or [],
        )
    )
    return task


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    owner: User,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.services.workflows.create_and_schedule_tool_task",
        _fake_scheduled_task,
    )

    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization == f"Bearer {OWNER_TOKEN}":
            return owner
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


def _headers(*, key: str | None = None, token: str = OWNER_TOKEN) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["X-Idempotency-Key"] = key
    return headers


async def _create_workflow(
    client: httpx.AsyncClient, *, name: str
) -> dict:
    """建一个只含**一个输入节点**的工作流定义。

    ``create_workflow_run`` 会先跑 ``validate_workflow_definition``，空 ``nodes``
    直接 422「must include nodes」，所以不能用空定义。这里刻意只放一个 ``input``
    节点：它是合法定义（拓扑无环、无必需 Artifact 输入），但**不是**工具节点或控制
    流节点，因此 ``executable_node_order`` 为空——一次运行不会调度任何任务。幂等
    语义验证的是「运行记录本身建了几条」，节点任务由
    ``test/test_workflow_persistence_api.py`` 覆盖，这里不需要。
    """
    response = await client.post(
        "/api/v1/workflows",
        headers=_headers(),
        json={
            "name": name,
            "canvas_preset_id": "free-canvas",
            "nodes": [
                {
                    "id": "protein_input",
                    "kind": "input",
                    "semantic_type": "protein_pdb",
                }
            ],
            "edges": [],
            "selected_tool_by_node": {},
            "artifact_bindings_by_node": {},
        },
    )
    assert response.status_code == 200, (response.status_code, response.text)
    return response.json()["data"]


async def _start_run(
    client: httpx.AsyncClient,
    workflow_id: str,
    *,
    key: str | None = None,
    input_files: dict[str, str] | None = None,
    token: str = OWNER_TOKEN,
):
    return await client.post(
        f"/api/v1/workflows/{workflow_id}/runs",
        headers=_headers(key=key, token=token),
        json={"input_files": input_files or {}},
    )


async def _run_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(WorkflowRun))
    return int(result.scalar_one())


async def _idempotency_row_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(IdempotencyKey))
    return int(result.scalar_one())


# ---------------------------------------------------------------------------
# 1) 同键同体 → 重放首响，只落一条运行
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_key_replays_first_run_without_creating_a_second(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    workflow = await _create_workflow(api_client, name="Idempotent run")

    first = await _start_run(api_client, workflow["id"], key="wf-idem-1")
    assert first.status_code == 200, first.text
    first_id = first.json()["data"]["id"]

    second = await _start_run(api_client, workflow["id"], key="wf-idem-1")
    assert second.status_code == 200, second.text
    assert second.json()["data"]["id"] == first_id
    assert await _run_count(db_session) == 1


@pytest.mark.asyncio
async def test_replay_returns_identical_envelope(
    api_client: httpx.AsyncClient,
) -> None:
    workflow = await _create_workflow(api_client, name="Envelope replay")

    first = await _start_run(api_client, workflow["id"], key="wf-envelope")
    second = await _start_run(api_client, workflow["id"], key="wf-envelope")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["code"] == second.json()["code"] == 200
    assert first.json()["message"] == second.json()["message"]
    assert second.json()["data"] == first.json()["data"]


@pytest.mark.asyncio
async def test_snapshot_is_persisted_with_resource_type(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    workflow = await _create_workflow(api_client, name="Snapshot")

    first = await _start_run(api_client, workflow["id"], key="wf-snapshot")
    run_id = first.json()["data"]["id"]

    rows = (await db_session.execute(select(IdempotencyKey))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.state == "COMPLETED"
    assert row.resource_type == "workflow_run"
    # ``_resource_id_from_body`` 取 ``data.id``，对工作流运行同样成立。
    assert row.resource_id == run_id
    assert row.response_body["data"]["id"] == run_id


# ---------------------------------------------------------------------------
# 2) 同键异体 → 40905
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_key_different_body_conflicts(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    workflow = await _create_workflow(api_client, name="Body conflict")

    first = await _start_run(api_client, workflow["id"], key="wf-conflict")
    assert first.status_code == 200

    second = await _start_run(
        api_client,
        workflow["id"],
        key="wf-conflict",
        input_files={"protein_pdb": "another-file"},
    )
    assert second.status_code == 409
    assert second.json()["code"] == 40905
    assert await _run_count(db_session) == 1


# ---------------------------------------------------------------------------
# 3) 不带键 → 完全透传
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_without_header_creates_two_runs(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    workflow = await _create_workflow(api_client, name="No header")

    first = await _start_run(api_client, workflow["id"])
    second = await _start_run(api_client, workflow["id"])

    assert first.status_code == 200, (first.status_code, first.text)
    assert second.status_code == 200
    assert second.json()["data"]["id"] != first.json()["data"]["id"]
    assert await _run_count(db_session) == 2
    # 没带键时不应留下任何幂等行（「不产生数据库读写」是装饰器的承诺）。
    assert await _idempotency_row_count(db_session) == 0


# ---------------------------------------------------------------------------
# 4) scope 用路径模板：跨工作流的键误用必须被发现
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scope_uses_path_template_so_cross_workflow_reuse_conflicts(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """同一个键打在两个**不同**工作流上必须 40905。

    这是 ``path_template="/api/v1/workflows/{workflow_id}/runs"`` 的直接后果：
    scope 只由「用户 + 方法 + 模板」组成，不把具体 ``workflow_id`` 拼进去。若换成
    真实路径，两次请求会落在两个互不相干的作用域里，工具会「正常」创建两个运行，
    而客户端的键误用永远不被发现。
    """
    workflow_a = await _create_workflow(api_client, name="Workflow A")
    workflow_b = await _create_workflow(api_client, name="Workflow B")

    first = await _start_run(api_client, workflow_a["id"], key="wf-shared-key")
    assert first.status_code == 200

    second = await _start_run(api_client, workflow_b["id"], key="wf-shared-key")
    assert second.status_code == 409
    assert second.json()["code"] == 40905
    assert await _run_count(db_session) == 1


@pytest.mark.asyncio
async def test_same_key_on_two_workflows_after_first_completes(
    api_client: httpx.AsyncClient,
) -> None:
    """首个请求完成后，同键换工作流仍然报冲突，而不是被当成新请求。"""
    workflow_a = await _create_workflow(api_client, name="Done A")
    workflow_b = await _create_workflow(api_client, name="Done B")

    assert (await _start_run(api_client, workflow_a["id"], key="wf-done")).status_code == 200
    conflict = await _start_run(api_client, workflow_b["id"], key="wf-done")
    assert conflict.status_code == 409
    assert conflict.json()["code"] == 40905


# ---------------------------------------------------------------------------
# 5) 鉴权没有被装饰器绕过
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_credentials_still_unauthorized(
    api_client: httpx.AsyncClient,
) -> None:
    workflow = await _create_workflow(api_client, name="Auth")

    response = await api_client.post(
        f"/api/v1/workflows/{workflow['id']}/runs",
        headers={"X-Idempotency-Key": "wf-auth"},
        json={"input_files": {}},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 6) 失败必须把键还回去（与 ``/tasks`` 的语义一致）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_run_releases_key_for_retry(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次运行创建失败（4xx）后，同一个键必须还能用。

    「失败也算完成」会让客户端永远无法用同键重试，而那恰恰是幂等键最需要工作的
    场景。这里用「工作流不存在」制造一次确定性失败。
    """
    missing_workflow = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"

    failed = await _start_run(api_client, missing_workflow, key="wf-retry")
    assert failed.status_code == 404
    assert await _idempotency_row_count(db_session) == 0

    workflow = await _create_workflow(api_client, name="Retry target")
    retried = await _start_run(api_client, workflow["id"], key="wf-retry")
    assert retried.status_code == 200, retried.text
    assert await _run_count(db_session) == 1


@pytest.mark.asyncio
async def test_disabled_switch_ignores_header(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings as config_settings

    monkeypatch.setattr(config_settings, "IDEMPOTENCY_ENABLED", False, raising=False)
    workflow = await _create_workflow(api_client, name="Disabled")

    first = await _start_run(api_client, workflow["id"], key="wf-off")
    second = await _start_run(api_client, workflow["id"], key="wf-off")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["id"] != first.json()["data"]["id"]
    assert await _run_count(db_session) == 2


__all__: list[str] = []
