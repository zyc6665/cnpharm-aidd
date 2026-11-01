"""容器日志归档（``services/runtime_logs.py``）的行为契约。

这些用例保护三件事：
1. 任务进终态时日志真的进了 ``task_logs``，且 ``GET /tasks/{id}/logs`` 能读到；
2. 归档是幂等的——重试、重复回调不会写出重复日志；
3. 归档失败绝不冒泡——日志是「附加价值」，不能让任务结果写入回滚。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - 触发表注册
from app.config import settings
from app.database.base import Base
from app.models.tasks import Task, TaskLog
from app.services.runtime_logs import (
    MAX_MESSAGE_CHARS,
    RUNTIME_LOG_SOURCE,
    harvest_task_runtime_logs,
    split_log_content,
)


class FakeExecutionService:
    """按游标返回日志片段；最后一次返回 ``complete=True``。"""

    def __init__(self, pages: dict[str | None, tuple[str, str | None]]):
        self._pages = pages
        self.calls: list[tuple[str, str, str | None]] = []

    async def logs(self, adapter_type: str, execution_id: str, cursor: str | None = None):
        self.calls.append((adapter_type, execution_id, cursor))
        content, next_cursor = self._pages.get(cursor, ("", None))
        return SimpleNamespace(
            content=content,
            next_cursor=next_cursor,
            complete=next_cursor is None,
        )


class ExplodingExecutionService:
    async def logs(self, adapter_type: str, execution_id: str, cursor: str | None = None):
        raise RuntimeError("kubeconfig expired")


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _task(task_id: str = "task-1", *, external_id: str | None = "job-1") -> Task:
    extra = {"external_id": external_id} if external_id else {}
    return Task(
        id=task_id,
        user_id="user-1",
        tool_id="tool-1",
        tool_version_id="version-1",
        name="docking",
        status="RUNNING",
        extra_data=extra,
    )


async def _log_rows(db, task_id: str) -> list[TaskLog]:
    result = await db.execute(
        select(TaskLog).where(TaskLog.task_id == task_id).order_by(TaskLog.timestamp, TaskLog.id)
    )
    return list(result.scalars().all())


def test_split_log_content_prefers_newline_boundaries():
    content = "a" * 100 + "\n" + "b" * 100
    chunks = split_log_content(content)
    assert len(chunks) == 1  # 低于上限时不分块
    assert chunks[0] == content


def test_split_log_content_hard_splits_without_newlines():
    content = "x" * (MAX_MESSAGE_CHARS * 2 + 10)
    chunks = split_log_content(content)
    assert len(chunks) == 3
    assert all(len(chunk) <= MAX_MESSAGE_CHARS for chunk in chunks)
    assert "".join(chunks) == content


@pytest.mark.asyncio
async def test_harvest_persists_container_logs(db_session):
    db_session.add(_task())
    await db_session.flush()

    service = FakeExecutionService(
        {
            None: ("step 1: load receptor\n", "cursor-2"),
            "cursor-2": ("step 2: docking\n", "cursor-3"),
            "cursor-3": ("step 3: done\n", None),
        }
    )

    rows = await harvest_task_runtime_logs(db_session, task=_task(), execution_service=service)

    assert rows == 1  # 三段拼起来只有 49 字节，落在同一行
    stored = await _log_rows(db_session, "task-1")
    assert len(stored) == 1
    assert stored[0].log_data["source"] == RUNTIME_LOG_SOURCE
    assert stored[0].message == "step 1: load receptor\nstep 2: docking\nstep 3: done\n"
    assert [call[0] for call in service.calls] == ["k8s_job", "k8s_job", "k8s_job"]
    assert [call[2] for call in service.calls] == [None, "cursor-2", "cursor-3"]


@pytest.mark.asyncio
async def test_harvest_is_idempotent(db_session):
    db_session.add(_task())
    await db_session.flush()
    service = FakeExecutionService({None: ("only once\n", None)})

    first = await harvest_task_runtime_logs(db_session, task=_task(), execution_service=service)
    second = await harvest_task_runtime_logs(db_session, task=_task(), execution_service=service)

    assert first == 1
    assert second == 0
    assert len(await _log_rows(db_session, "task-1")) == 1


@pytest.mark.asyncio
async def test_harvest_skips_tasks_without_external_handle(db_session):
    db_session.add(_task(external_id=None))
    await db_session.flush()
    service = FakeExecutionService({None: ("should not be read\n", None)})

    rows = await harvest_task_runtime_logs(db_session, task=_task(external_id=None), execution_service=service)

    assert rows == 0
    assert service.calls == []


@pytest.mark.asyncio
async def test_harvest_truncates_and_marks_last_row(db_session):
    db_session.add(_task())
    await db_session.flush()
    service = FakeExecutionService({None: ("y" * 5000, None)})

    rows = await harvest_task_runtime_logs(
        db_session, task=_task(), execution_service=service, max_bytes=1000
    )

    assert rows == 1
    stored = await _log_rows(db_session, "task-1")
    assert len(stored[0].message) == 1000
    assert stored[0].log_data["truncated"] is True


@pytest.mark.asyncio
async def test_harvest_swallows_adapter_failures(db_session):
    db_session.add(_task())
    await db_session.flush()

    rows = await harvest_task_runtime_logs(
        db_session, task=_task(), execution_service=ExplodingExecutionService()
    )

    assert rows == 0
    assert await _log_rows(db_session, "task-1") == []


@pytest.mark.asyncio
async def test_harvest_respects_disabled_switch(db_session, monkeypatch):
    monkeypatch.setattr(settings, "TASK_LOG_HARVEST_ENABLED", False)
    db_session.add(_task())
    await db_session.flush()
    service = FakeExecutionService({None: ("ignored\n", None)})

    rows = await harvest_task_runtime_logs(db_session, task=_task(), execution_service=service)

    assert rows == 0
    assert service.calls == []


@pytest.mark.asyncio
async def test_harvest_ignores_empty_output(db_session):
    db_session.add(_task())
    await db_session.flush()
    service = FakeExecutionService({None: ("   \n", None)})

    rows = await harvest_task_runtime_logs(db_session, task=_task(), execution_service=service)

    assert rows == 0
    count = (
        await db_session.execute(
            select(func.count()).select_from(TaskLog).where(TaskLog.task_id == "task-1")
        )
    ).scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_harvest_falls_back_to_execution_record_handle(db_session):
    """句柄只在 ExecutionRecord 上时（Celery 直接派发的 k8s 任务就是这样）也要能归档。

    回归背景：任务元数据里没有 ``external_id``，而托管执行器把句柄写在
    ``execution_records.external_id``。只查 ``extra_data`` 会一直取到 None，
    归档于是静默不生效——线上表现为「任务失败但一条容器日志都没有」。
    """
    from app.models.executions import ExecutionRecord

    task = _task(external_id=None)
    db_session.add(task)
    db_session.add(
        ExecutionRecord(
            id="record-1",
            task_id="task-1",
            project_id="project-1",
            requested_by="user-1",
            tool_package_version_id="tpv-1",
            idempotency_key="idem-1",
            adapter_type="k8s_job",
            external_id="sciminer-model-jobs/sciminer-abc123",
            status="failed",
        )
    )
    await db_session.flush()
    task.extra_data = {"execution_record_id": "record-1"}

    service = FakeExecutionService({None: ("from record handle\n", None)})
    rows = await harvest_task_runtime_logs(db_session, task=task, execution_service=service)

    assert rows == 1
    assert service.calls[0][1] == "sciminer-model-jobs/sciminer-abc123"
