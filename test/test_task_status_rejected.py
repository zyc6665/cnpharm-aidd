"""``REJECTED``（第 8 个任务状态）的专门测试。

为什么需要这个状态
------------------
``docs/03 §3.4`` 的状态机里 ``CREATED --> REJECTED`` 是一条独立边（配额/参数校验
失败），``docs/04 §2.3`` 的枚举也是八态。在此之前平台只有七态：配额不足时直接抛
HTTP 429，**什么都不落库**，于是「我那次提交被拒了，原因是并发 DCU 超限」这件事
在任务中心里查不到。本文件守的就是这条新语义，以及它与既有七态的边界：

* REJECTED 是**终态**（不会自己再动），但**不核销算力**（它没跑过）；
* REJECTED **不可重试**（重试路径不做配额准入，允许重试等于开一条绕过配额的路）；
* REJECTED 出现在任务中心「历史」，但**不在**「需要关注」与「结果中心」；
* 工作流的节点/循环体/map 子任务被拒时按**失败**处理，否则工作流会等一个永远
  不会开始的任务直到整体超时。

任何一条被改坏，本文件都会有对应用例变红。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.task_status import (  # noqa: E402
    task_status_to_api,
    task_status_to_execution_state,
)
from app.database.base import Base  # noqa: E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models.tasks import Task, TaskStatus  # noqa: E402
from app.tasks.state_machine import TaskStateMachine, TaskStateError  # noqa: E402


def _make_task(status: TaskStatus = TaskStatus.PENDING, **extra) -> Task:
    """构造一个不入库的任务对象（状态机是纯同步模块，不需要 session）。"""
    task = Task(
        id="task-rejected-1",
        user_id="user-1",
        tool_id="tool-1",
        tool_version_id="version-1",
        status=status.value,
    )
    for key, value in extra.items():
        setattr(task, key, value)
    return task


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


# ---------------------------------------------------------------------------
# 枚举与映射
# ---------------------------------------------------------------------------


def test_rejected_is_the_eighth_task_status() -> None:
    """八态齐全（docs/04 §2.3）。少一个就说明有人回退了这个状态。"""
    assert {status.value for status in TaskStatus} == {
        "PENDING",
        "REJECTED",
        "QUEUED",
        "RUNNING",
        "SUCCESS",
        "FAILURE",
        "TIMEOUT",
        "CANCELED",
    }


def test_rejected_api_and_execution_mappings_are_distinct() -> None:
    """API 词表给 ``rejected``；执行契约也必须是 ``rejected`` 而不是 ``queued``。

    映射成 queued 会让「被拒」在监控面板上与「排队中」混为一谈——一个是没让你
    跑，一个是马上要跑。
    """
    assert task_status_to_api("REJECTED") == "rejected"
    assert task_status_to_execution_state("REJECTED") == "rejected"
    assert task_status_to_execution_state("REJECTED") != task_status_to_execution_state(
        "QUEUED"
    )


# ---------------------------------------------------------------------------
# 状态机：入边、终态、副作用
# ---------------------------------------------------------------------------


def test_only_pending_can_become_rejected() -> None:
    """``docs/03 §3.4`` 只有 ``CREATED --> REJECTED`` 一条入边。"""
    assert TaskStatus.REJECTED in TaskStateMachine.TRANSITIONS[TaskStatus.PENDING]

    for source in (
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.SUCCESS,
        TaskStatus.FAILURE,
        TaskStatus.TIMEOUT,
        TaskStatus.CANCELED,
    ):
        assert TaskStatus.REJECTED not in TaskStateMachine.TRANSITIONS[source], source


def test_rejected_has_no_outgoing_transition() -> None:
    """真终态：一旦落库就再也不会自己动。"""
    assert TaskStateMachine.TRANSITIONS[TaskStatus.REJECTED] == set()
    assert TaskStateMachine.is_terminal(TaskStatus.REJECTED) is True


def test_rejected_is_terminal_but_not_settled() -> None:
    """「终态」与「要核销算力」是两个集合。

    如果哪天有人把核销判断改回 ``TERMINAL_STATES``，这条会红——那等于让每一次
    被拒都从用户的算力额度里扣一笔钱。
    """
    assert TaskStatus.REJECTED in TaskStateMachine.TERMINAL_STATES
    assert TaskStatus.REJECTED not in TaskStateMachine._SETTLED_STATUSES
    # 四个「真的跑过」的终态必须仍在核销集合里，否则反过来会漏账。
    assert TaskStateMachine._SETTLED_STATUSES == {
        TaskStatus.SUCCESS,
        TaskStatus.FAILURE,
        TaskStatus.CANCELED,
        TaskStatus.TIMEOUT,
    }


def test_reject_sets_finished_at_without_starting_the_task() -> None:
    """被拒的任务要有「被拒时间」，但不能有开始时间与执行时长。"""
    task = _make_task(TaskStatus.PENDING)

    TaskStateMachine.reject(task, error_message="并发 DCU 已达上限 2")

    assert task.status == TaskStatus.REJECTED.value
    assert task.error_message == "并发 DCU 已达上限 2"
    assert task.finished_at is not None
    assert task.started_at is None
    assert task.execution_time_sec is None
    assert task.progress == 0.0
    assert task.progress_message == "任务被拒绝"


def test_reject_does_not_write_cost_metadata() -> None:
    """没有 started_at 就没有成本，``extra_data`` 里不该出现 ``cost``。"""
    task = _make_task(TaskStatus.PENDING, extra_data={})

    TaskStateMachine.reject(task, error_message="算力分钟已用尽")

    assert "cost" not in (task.extra_data or {})


def test_completing_a_settled_task_still_writes_cost_metadata() -> None:
    """反向守护：别为了 REJECTED 把正常终态的核销一起关掉。"""
    task = _make_task(
        TaskStatus.PENDING,
        extra_data={"project_id": "project-1"},
    )
    TaskStateMachine.start(task)
    TaskStateMachine.complete(task, success=True)

    assert task.status == TaskStatus.SUCCESS.value
    assert task.extra_data["cost"]["totalMinutes"] >= 0.0


def test_rejected_task_cannot_be_retried() -> None:
    """不可重试：``retry_task`` 不做配额准入，允许重试就是绕过配额。"""
    task = _make_task(TaskStatus.REJECTED)
    assert TaskStateMachine.can_retry(task) is False

    with pytest.raises(TaskStateError):
        TaskStateMachine.retry(task)


def test_rejected_task_cannot_be_started_or_completed() -> None:
    """终态不该能被「开始」或「完成」——那会把审计证据改写掉。"""
    started = _make_task(TaskStatus.REJECTED)
    with pytest.raises(TaskStateError):
        TaskStateMachine.start(started)

    completed = _make_task(TaskStatus.REJECTED)
    with pytest.raises(TaskStateError):
        TaskStateMachine.complete(completed, success=True)


# ---------------------------------------------------------------------------
# 视图 / 事件流 / 结果中心的口径
# ---------------------------------------------------------------------------


def test_rejected_shows_up_in_task_history_but_not_needs_attention() -> None:
    """被拒行存在的唯一理由就是被找到——所以必须在「历史」里。"""
    from app.services.task_views import _VIEW_STATUSES

    assert TaskStatus.REJECTED.value in _VIEW_STATUSES["history"]
    # 「需要关注」是运维口径（执行侧炸了/超时了），被拒是用户输入问题。
    assert TaskStatus.REJECTED.value not in _VIEW_STATUSES["needs_attention"]
    # 也不该被算成「进行中」，否则用户会等一个永远不会开始的任务。
    assert TaskStatus.REJECTED.value not in _VIEW_STATUSES["running"]
    assert TaskStatus.REJECTED.value not in _VIEW_STATUSES["recent_results"]


def test_rejected_is_a_terminal_state_for_the_event_stream() -> None:
    """SSE 订阅方必须在 REJECTED 时收尾，否则会挂到 max_duration 才断。"""
    from app.services.task_event_stream import TaskEventState

    state = TaskEventState(
        status=TaskStatus.REJECTED.value,
        progress=0.0,
        progress_message="任务被拒绝",
        error_message="并发 DCU 已达上限 2",
        updated_at=None,
    )

    assert state.terminal is True
    payload = state.to_payload("task-rejected-1")
    assert payload["status"] == "rejected"
    assert payload["rawStatus"] == "REJECTED"
    assert payload["terminal"] is True


def test_results_center_excludes_rejected_tasks() -> None:
    """结果中心列的是「跑出东西的任务」，被拒的没有产物。"""
    from app.api.v1.results import RESULT_STATUSES

    assert TaskStatus.REJECTED.value not in RESULT_STATUSES
    assert TaskStatus.SUCCESS.value in RESULT_STATUSES


# ---------------------------------------------------------------------------
# 工作流：被拒的子任务按失败处理
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_waiting_node_task_rejected_marks_node_failed(
    db_session: AsyncSession,
) -> None:
    """节点任务被拒 → 节点失败。

    不这么处理的话，工作流会一直等一个永远不会开始的任务，直到整体超时。
    """
    from app.services.workflow_waiting_task import load_finished_workflow_node_task

    db_session.add(
        Task(
            id="task-node-rejected",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.REJECTED.value,
            error_message="并发 DCU 已达上限 2",
        )
    )
    await db_session.flush()

    run = SimpleNamespace(status="waiting_task", error_message=None, finished_at=None)
    state = {"status": "waiting_task", "task_id": "task-node-rejected"}
    node_states = {"node-a": state}

    task = await load_finished_workflow_node_task(
        db_session,
        run=run,
        node_states=node_states,
        node_id="node-a",
        state=state,
    )

    assert task is None
    assert state["status"] == "failure"
    assert state["error_message"] == "并发 DCU 已达上限 2"
    assert run.status == "failure"


@pytest.mark.asyncio
async def test_loop_body_task_rejected_fails_the_loop_node(
    db_session: AsyncSession,
) -> None:
    from app.services.workflow_loop_scheduler import reconcile_loop_body

    db_session.add(
        Task(
            id="task-loop-rejected",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.REJECTED.value,
            error_message="算力分钟已用尽",
        )
    )
    await db_session.flush()

    state = {
        "status": "waiting_task",
        "loop_iteration": 1,
        "loop_body_states": {"body-a": {"task_id": "task-loop-rejected"}},
    }
    node_states = {"loop-a": state}
    node = {"id": "loop-a", "kind": "loop", "body": [{"id": "body-a"}]}
    run = SimpleNamespace(status="running", error_message=None, finished_at=None)

    changed = await reconcile_loop_body(
        db_session,
        node_id="loop-a",
        node=node,
        state=state,
        node_states=node_states,
        run=run,
    )

    assert changed is True
    assert state["status"] == "failure"
    assert state["loop_body_states"]["body-a"]["status"] == "failure"


@pytest.mark.asyncio
async def test_map_sub_task_rejected_counts_as_failure(db_session: AsyncSession) -> None:
    from app.services.workflow_map_scheduler import reconcile_map_sub_tasks

    db_session.add(
        Task(
            id="task-map-rejected",
            tool_id="tool-1",
            tool_version_id="version-1",
            status=TaskStatus.REJECTED.value,
            error_message="单任务时长超限",
        )
    )
    await db_session.flush()

    state = {
        "status": "waiting_task",
        "map_total": 2,
        "sub_tasks": {
            "sub-a": {"task_id": "task-map-rejected"},
            "sub-b": {},
        },
    }
    state["sub_tasks"]["sub-b"] = {"status": "success"}
    node_states = {"map-a": state}
    run = SimpleNamespace(status="running", error_message=None, finished_at=None)

    changed = await reconcile_map_sub_tasks(
        db_session,
        node_id="map-a",
        state=state,
        node_states=node_states,
        run=run,
    )

    assert changed is True
    assert state["map_failed"] == 1
    assert state["status"] == "failure"
    assert state["sub_tasks"]["sub-a"]["status"] == "failure"
