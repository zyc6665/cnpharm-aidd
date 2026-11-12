"""运行期日志与进度同步的测试（docs/26 H-2、H-3）。

覆盖四件事：
1. ``__DRP_PROGRESS__`` 解析：取最后一条、忽略坏 JSON、越界丢弃
2. 增量同步：写 ``task_logs``（``source=runtime`` / ``stream=live``）、去掉行首时间戳、
   游标落进 ``task.extra_data["runtimeLog"]`` 并在下一轮传给适配器
3. 进度只前进不后退
4. ``already_harvested`` 只认终态归档（``stream=final``），运行期同步过也仍要再归档
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.models.tasks import Task, TaskLog, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services.runtime_log_sync import (  # noqa: E402
    RUNTIME_LOG_META_KEY,
    parse_progress_marker,
    sync_task_runtime_logs,
)
from app.services.runtime_logs import (  # noqa: E402
    RUNTIME_LOG_SOURCE,
    RUNTIME_LOG_STREAM_LIVE,
    already_harvested,
    harvest_task_runtime_logs,
)


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


@pytest_asyncio.fixture
async def task(db_session: AsyncSession) -> Task:
    # tasks.user_id / tool_id / tool_version_id 都是 NOT NULL 且有外键，
    # 因此必须建真实的父行，不能塞假 id（SQLite 开了 foreign_keys 会直接报错）。
    owner = User(
        email="runtime-owner@example.com",
        password_hash="hashed-password",
        display_name="Runtime Owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(owner)
    await db_session.flush()

    tool = Tool(
        owner_id=owner.id,
        name="MD Tool",
        slug="md-tool",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(tool_id=tool.id, version="1.0.0", config={"type": "k8s_job"})
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id

    task = Task(
        user_id=owner.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        name="MD simulation",
        status=TaskStatus.RUNNING.value,
        progress=0.0,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


class FakeExecutionService:
    """记录调用参数的假执行服务：只回放一段带时间戳的日志。"""

    def __init__(self, chunk: str, *, next_cursor: str | None = None) -> None:
        self.chunk = chunk
        self.next_cursor = next_cursor
        self.calls: list[tuple[str, str, str | None]] = []

    async def logs(self, adapter_type: str, external_id: str, cursor: str | None):
        self.calls.append((adapter_type, external_id, cursor))
        return SimpleNamespace(content=self.chunk, next_cursor=self.next_cursor, complete=False)


TIMESTAMPED_LOG = (
    "2026-11-10T09:00:01.000000000Z 开始体系构建\n"
    '2026-11-10T09:00:02.000000000Z __DRP_PROGRESS__ {"pct": 20, "message": "能量最小化"}\n'
    "2026-11-10T09:00:03.000000000Z 完成 1000 步\n"
    '2026-11-10T09:00:04.000000000Z __DRP_PROGRESS__ {"pct": 45, "message": "阶段 3/7：平衡"}\n'
)


async def _runtime_rows(db: AsyncSession, task_id: str) -> list[TaskLog]:
    result = await db.execute(
        select(TaskLog)
        .where(TaskLog.task_id == task_id)
        .order_by(TaskLog.timestamp.asc())
    )
    return [
        row
        for row in result.scalars().all()
        if (row.log_data or {}).get("source") == RUNTIME_LOG_SOURCE
    ]


# ---------------------------------------------------------------------------
# 1. 进度标记解析
# ---------------------------------------------------------------------------


def test_parse_progress_marker_takes_the_last_one():
    progress = parse_progress_marker(TIMESTAMPED_LOG)
    assert progress == {"pct": 45.0, "message": "阶段 3/7：平衡"}


def test_parse_progress_marker_ignores_broken_json():
    content = (
        '__DRP_PROGRESS__ {"pct": 10, "message": "ok"}\n'
        '__DRP_PROGRESS__ {"pct": 90, "message": "截断\n'
    )
    # 第二条是半行：解析失败就跳过，绝不退回上一条或猜一个值。
    assert parse_progress_marker(content) == {"pct": 10.0, "message": "ok"}


def test_parse_progress_marker_rejects_out_of_range_pct():
    assert parse_progress_marker('__DRP_PROGRESS__ {"pct": 140}') is None
    assert parse_progress_marker('__DRP_PROGRESS__ {"pct": -5}') is None
    assert parse_progress_marker('__DRP_PROGRESS__ {"pct": "abc"}') is None
    assert parse_progress_marker('__DRP_PROGRESS__ {"pct": true}') is None


def test_parse_progress_marker_returns_none_without_marker():
    assert parse_progress_marker("just a log line\n") is None
    assert parse_progress_marker("") is None


def test_parse_progress_marker_accepts_marker_without_message():
    assert parse_progress_marker('__DRP_PROGRESS__ {"pct": 7.5}') == {"pct": 7.5, "message": None}


# ---------------------------------------------------------------------------
# 2. 增量同步
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_writes_logs_and_progress(db_session: AsyncSession, task: Task):
    service = FakeExecutionService(TIMESTAMPED_LOG)

    summary = await sync_task_runtime_logs(
        db_session,
        task=task,
        execution_service=service,
        # 绕过执行记录查表的兜底路径：直接从 extra_data 取句柄。
    )

    assert summary["skipped"] == "没有外部执行句柄"

    task.extra_data = {"externalExecutionId": "job-abc"}
    summary = await sync_task_runtime_logs(
        db_session, task=task, execution_service=service
    )
    assert summary["lines"] == 1  # 整段只有 300 字节不到，切成一行
    assert summary["progress"] == 45.0

    rows = await _runtime_rows(db_session, task.id)
    assert len(rows) == 1
    assert rows[0].log_data["stream"] == RUNTIME_LOG_STREAM_LIVE
    assert rows[0].log_data["external_id"] == "job-abc"
    # 行首时间戳被剥掉：task_logs.timestamp 才是权威时间，正文里再留一份只会让人误读。
    assert "2026-11-10T09:00:01" not in rows[0].message
    assert "开始体系构建" in rows[0].message

    assert task.progress == 45.0
    assert task.progress_message == "阶段 3/7：平衡"
    assert task.extra_data[RUNTIME_LOG_META_KEY]["cursor"] == "2026-11-10T09:00:04.000000000Z"


@pytest.mark.asyncio
async def test_sync_forwards_stored_cursor_on_next_round(db_session: AsyncSession, task: Task):
    task.extra_data = {"externalExecutionId": "job-abc"}
    service = FakeExecutionService(TIMESTAMPED_LOG)

    await sync_task_runtime_logs(db_session, task=task, execution_service=service)
    await sync_task_runtime_logs(db_session, task=task, execution_service=service)

    assert service.calls[0][2] is None
    # 第二轮必须带上上一轮最后一行的时间戳，否则每轮都会把整段日志重写一遍。
    assert service.calls[1][2] == "2026-11-10T09:00:04.000000000Z"


@pytest.mark.asyncio
async def test_sync_skips_when_no_new_content(db_session: AsyncSession, task: Task):
    task.extra_data = {"externalExecutionId": "job-abc"}
    service = FakeExecutionService("")

    summary = await sync_task_runtime_logs(db_session, task=task, execution_service=service)

    assert summary["lines"] == 0
    assert await _runtime_rows(db_session, task.id) == []
    assert RUNTIME_LOG_META_KEY not in (task.extra_data or {})


@pytest.mark.asyncio
async def test_sync_does_not_write_progress_without_marker(db_session: AsyncSession, task: Task):
    task.extra_data = {"externalExecutionId": "job-abc"}
    service = FakeExecutionService("2026-11-10T09:00:01.000000000Z 普通日志\n")

    summary = await sync_task_runtime_logs(db_session, task=task, execution_service=service)

    assert summary["lines"] == 1
    assert summary["progress"] is None
    assert task.progress == 0.0


# ---------------------------------------------------------------------------
# 3. 进度只前进
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_never_moves_backwards(db_session: AsyncSession, task: Task):
    task.progress = 80.0
    task.extra_data = {"externalExecutionId": "job-abc"}
    service = FakeExecutionService(
        '2026-11-10T09:05:00.000000000Z __DRP_PROGRESS__ {"pct": 30, "message": "重跑阶段 2"}\n'
    )

    summary = await sync_task_runtime_logs(db_session, task=task, execution_service=service)

    # 进度条倒退比不动更让人怀疑任务在重来；消息仍然更新，因为它说明了发生了什么。
    assert summary["progress"] == 30.0
    assert task.progress == 80.0
    assert task.progress_message == "重跑阶段 2"


# ---------------------------------------------------------------------------
# 4. 归档幂等只认终态
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_rows_do_not_count_as_archived(db_session: AsyncSession, task: Task):
    task.extra_data = {"externalExecutionId": "job-abc"}
    service = FakeExecutionService(TIMESTAMPED_LOG)
    await sync_task_runtime_logs(db_session, task=task, execution_service=service)

    # 运行期同步过一轮不算「已归档」：终态那次还要把任务结尾的日志补进来。
    assert await already_harvested(db_session, task_id=task.id) is False

    db_session.add(
        TaskLog(
            task_id=task.id,
            level="INFO",
            message="final chunk",
            log_data={"source": RUNTIME_LOG_SOURCE, "stream": "final", "sequence": 0},
        )
    )
    await db_session.flush()

    assert await already_harvested(db_session, task_id=task.id) is True


# ---------------------------------------------------------------------------
# 5. 终态归档接着运行期游标往后拉（否则同一段日志会被写第二遍）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_terminal_harvest_continues_from_synced_cursor(
    db_session: AsyncSession, task: Task
):
    task.extra_data = {"externalExecutionId": "job-abc"}
    live = FakeExecutionService(TIMESTAMPED_LOG, next_cursor="2026-11-10T09:00:04.000000000Z")
    summary = await sync_task_runtime_logs(db_session, task=task, execution_service=live)
    await db_session.commit()
    await db_session.refresh(task)
    synced_cursor = task.extra_data[RUNTIME_LOG_META_KEY]["cursor"]
    assert synced_cursor == "2026-11-10T09:00:04.000000000Z"
    assert summary["lines"] == 1

    # 终态归档：适配器这边只会返回运行期同步之后的尾巴。
    tail = FakeExecutionService(
        '2026-11-10T09:10:00.000000000Z __DRP_PROGRESS__ {"pct": 100, "message": "完成"}\n',
        next_cursor=None,
    )
    rows = await harvest_task_runtime_logs(
        db_session, task=task, execution_service=tail, max_bytes=100_000
    )
    await db_session.commit()

    # 关键断言：第一次调用就带着已存游标，不是从头再拉一遍。
    assert tail.calls[0][2] == synced_cursor
    assert rows == 1
    messages = (
        await db_session.execute(select(TaskLog.message).where(TaskLog.task_id == task.id))
    ).scalars().all()
    assert len(messages) == 2
    # 归档行只包含尾部内容，运行期那一行没有被复制。
    final_messages = [
        row.message
        for row in (
            await db_session.execute(
                select(TaskLog).where(TaskLog.task_id == task.id).order_by(TaskLog.timestamp)
            )
        ).scalars()
        if (row.log_data or {}).get("stream") == "final"
    ]
    assert final_messages == ['__DRP_PROGRESS__ {"pct": 100, "message": "完成"}\n']
