"""排队超时巡检（docs/18 §6.4 B-2b）。

这里守的是「安静卡住」这个失败模式：调度器漏消息、卡位全占、配额被占死时，
任务会永远停在 QUEUED，页面显示「排队中」而实际永远不会开始——用户看不到失败
也就不会重试，运维看队列深度还正常。所以必须有与用户行为无关的时间上限。

关键回归点有四条，任何一条退回去都会让巡检失去意义：
1. 锚点必须是入队时刻（`queued_at`），不是 `created_at`——PENDING 停留的时间
   不该计入排队；
2. 转 TIMEOUT 必须走状态机（CAS），否则 `test_worker_state_machine.py` 的
   AST 守卫会失败，且 `finished_at`/`error_message` 会缺；
3. 离开 QUEUED 时必须清掉锚点，否则重排的任务带着旧时间会被立刻判超时；
4. 巡检循环的退出条件必须写在 `while` 上——`stop()` 先 set 事件再 cancel，
   若循环只靠 cancel 退出、而 sweep 又是纯计算，事件循环会被占满而投递不到
   `CancelledError`，`stop()` 永久挂住（Linux 上必现，Windows 上因时序侥幸通过）。
"""

import asyncio
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base, utcnow
from app.models.tasks import Task, TaskLog, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.services.queue_timeout import (
    QUEUED_ANCHOR_KEY,
    QueueTimeoutSweepLoop,
    build_queue_timeout_sweep_loop,
    expire_timed_out_queue_entries,
    queue_anchor,
)
from app.tasks.state_machine import QUEUED_AT_METADATA_KEY, TaskStateMachine


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _make_owner(db: AsyncSession) -> User:
    user = User(
        email="queue-owner@example.com",
        password_hash="hashed-password",
        display_name="Queue Owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_task(
    db: AsyncSession,
    owner: User,
    *,
    status: TaskStatus = TaskStatus.QUEUED,
    queued_at=None,
    suffix: str = "",
) -> Task:
    tool = Tool(
        owner_id=owner.id,
        name=f"Queue Tool{suffix}",
        slug=f"queue-tool{suffix}",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(tool_id=tool.id, version="1.0.0", config={"type": "python_script"})
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id

    extra_data: dict[str, object] = {}
    if queued_at is not None:
        extra_data[QUEUED_AT_METADATA_KEY] = queued_at.isoformat()

    task = Task(
        user_id=owner.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        name=f"queue-task{suffix}",
        status=status.value,
        extra_data=extra_data,
    )
    db.add(task)
    await db.flush()
    return task


class TestQueueAnchor:
    def test_enqueue_writes_anchor(self):
        task = Task(
            id="t-1", user_id="u-1", tool_id="tool-1", tool_version_id="v-1",
            status=TaskStatus.PENDING.value,
        )
        TaskStateMachine.enqueue(task)

        assert task.extra_data[QUEUED_ANCHOR_KEY] == task.extra_data[QUEUED_AT_METADATA_KEY]
        assert queue_anchor(task) is not None

    def test_anchor_uses_enqueue_moment_not_created_at(self):
        task = Task(
            id="t-1", user_id="u-1", tool_id="tool-1", tool_version_id="v-1",
            status=TaskStatus.PENDING.value,
        )
        TaskStateMachine.enqueue(task)

        anchor = queue_anchor(task)

        # 写的是转换时刻，不是模型默认值
        assert anchor is not None
        assert abs((utcnow() - anchor).total_seconds()) < 5

    def test_leaving_queue_clears_anchor(self):
        task = Task(
            id="t-1",
            user_id="u-1",
            tool_id="tool-1",
            tool_version_id="v-1",
            status=TaskStatus.QUEUED.value,
            extra_data={QUEUED_AT_METADATA_KEY: "2026-01-01T00:00:00", "keep": "me"},
        )

        TaskStateMachine.start(task)

        assert QUEUED_AT_METADATA_KEY not in task.extra_data
        # 其它键必须原样保留
        assert task.extra_data["keep"] == "me"

    def test_anchor_falls_back_to_updated_at_for_legacy_rows(self):
        # 历史行没有 queued_at：用 updated_at 代替，否则老任务永远判不出超时
        task = Task(id="t-1", user_id="u-1", tool_id="tool-1", tool_version_id="v-1")
        task.updated_at = utcnow() - timedelta(hours=12)

        assert queue_anchor(task) == task.updated_at

    def test_bad_anchor_string_is_ignored(self):
        task = Task(
            id="t-1",
            user_id="u-1",
            tool_id="tool-1",
            tool_version_id="v-1",
            extra_data={QUEUED_AT_METADATA_KEY: "not-a-timestamp"},
        )

        assert queue_anchor(task) == task.updated_at

    def test_aware_anchor_is_normalised_to_naive(self):
        task = Task(
            id="t-1",
            user_id="u-1",
            tool_id="tool-1",
            tool_version_id="v-1",
            extra_data={QUEUED_AT_METADATA_KEY: "2026-10-26T13:00:00+08:00"},
        )

        anchor = queue_anchor(task)

        assert anchor is not None
        assert anchor.tzinfo is None


class TestExpireQueueEntries:
    @pytest.mark.asyncio
    async def test_expires_only_entries_over_the_window(self, db_session):
        owner = await _make_owner(db_session)
        stale = await _make_task(
            db_session, owner, queued_at=utcnow() - timedelta(hours=7), suffix="-stale"
        )
        fresh = await _make_task(
            db_session, owner, queued_at=utcnow() - timedelta(minutes=5), suffix="-fresh"
        )

        expired = await expire_timed_out_queue_entries(db_session, timeout_seconds=21600)
        await db_session.commit()

        assert expired == 1
        assert stale.status == TaskStatus.TIMEOUT.value
        assert fresh.status == TaskStatus.QUEUED.value

    @pytest.mark.asyncio
    async def test_timeout_writes_terminal_columns(self, db_session):
        owner = await _make_owner(db_session)
        task = await _make_task(
            db_session, owner, queued_at=utcnow() - timedelta(hours=7)
        )

        await expire_timed_out_queue_entries(db_session, timeout_seconds=21600)
        await db_session.commit()

        assert task.finished_at is not None
        assert task.progress_message == "排队超时"
        assert "6 小时" in (task.error_message or "")

    @pytest.mark.asyncio
    async def test_timeout_writes_a_warning_log(self, db_session):
        owner = await _make_owner(db_session)
        task = await _make_task(
            db_session, owner, queued_at=utcnow() - timedelta(hours=7)
        )

        await expire_timed_out_queue_entries(db_session, timeout_seconds=21600)
        await db_session.commit()

        logs = (
            await db_session.execute(select(TaskLog).where(TaskLog.task_id == task.id))
        ).scalars().all()
        assert len(logs) == 1
        assert logs[0].level == "WARNING"
        assert "排队" in logs[0].message

    @pytest.mark.asyncio
    async def test_running_tasks_are_never_touched(self, db_session):
        owner = await _make_owner(db_session)
        running = await _make_task(
            db_session,
            owner,
            status=TaskStatus.RUNNING,
            queued_at=utcnow() - timedelta(hours=7),
        )

        expired = await expire_timed_out_queue_entries(db_session, timeout_seconds=21600)
        await db_session.commit()

        assert expired == 0
        assert running.status == TaskStatus.RUNNING.value

    @pytest.mark.asyncio
    async def test_batch_size_caps_one_round(self, db_session):
        owner = await _make_owner(db_session)
        for index in range(3):
            await _make_task(
                db_session,
                owner,
                queued_at=utcnow() - timedelta(hours=7),
                suffix=f"-{index}",
            )

        expired = await expire_timed_out_queue_entries(
            db_session, timeout_seconds=21600, batch_size=2
        )
        await db_session.commit()

        assert expired == 2
        remaining = (
            await db_session.execute(
                select(Task).where(Task.status == TaskStatus.QUEUED.value)
            )
        ).scalars().all()
        assert len(remaining) == 1

    @pytest.mark.asyncio
    async def test_zero_window_is_a_noop(self, db_session):
        owner = await _make_owner(db_session)
        task = await _make_task(
            db_session, owner, queued_at=utcnow() - timedelta(hours=7)
        )

        assert await expire_timed_out_queue_entries(db_session, timeout_seconds=0) == 0
        assert task.status == TaskStatus.QUEUED.value

    @pytest.mark.asyncio
    async def test_idempotent_on_second_run(self, db_session):
        owner = await _make_owner(db_session)
        await _make_task(db_session, owner, queued_at=utcnow() - timedelta(hours=7))

        first = await expire_timed_out_queue_entries(db_session, timeout_seconds=21600)
        await db_session.commit()
        second = await expire_timed_out_queue_entries(db_session, timeout_seconds=21600)
        await db_session.commit()

        assert (first, second) == (1, 0)
        # 不能写两条日志
        logs = (await db_session.execute(select(TaskLog))).scalars().all()
        assert len(logs) == 1

    @pytest.mark.asyncio
    async def test_timeout_task_can_be_retried(self, db_session):
        owner = await _make_owner(db_session)
        task = await _make_task(
            db_session, owner, queued_at=utcnow() - timedelta(hours=7)
        )

        await expire_timed_out_queue_entries(db_session, timeout_seconds=21600)
        await db_session.commit()

        # TIMEOUT 是「可重试的终态」，不是死路（docs/04 §9.1 状态机）
        assert TaskStateMachine.can_retry(task) is True
        TaskStateMachine.transition(task, TaskStatus.QUEUED, progress_message="重新排队")
        assert task.status == TaskStatus.QUEUED.value
        # 重排后锚点必须换成新的，否则下一轮立刻又判超时
        anchor = queue_anchor(task)
        assert anchor is not None
        assert abs((utcnow() - anchor).total_seconds()) < 5


class TestSweepLoop:
    def test_loop_is_configured_from_settings(self):
        loop = build_queue_timeout_sweep_loop()

        assert loop is not None
        assert isinstance(loop, QueueTimeoutSweepLoop)
        assert loop.is_running is False

    def test_disabled_setting_yields_no_loop(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "TASK_QUEUE_TIMEOUT_ENABLED", False)

        assert build_queue_timeout_sweep_loop() is None

    @pytest.mark.asyncio
    async def test_loop_start_stop_cycles(self):
        calls: list[int] = []

        async def sweep():
            calls.append(1)
            return 0

        loop = QueueTimeoutSweepLoop(sweep=sweep, interval_seconds=1)
        loop.start()
        assert loop.is_running is True
        # stop() 必须加超时：一旦循环的退出条件写错（例如 while True 只靠
        # cancel()），事件循环会被纯计算的 sweep 占满而投递不到 CancelledError，
        # 没有超时的话整个测试进程就永久挂住、CI 只会表现为「一直跑」。
        await asyncio.wait_for(loop.stop(), timeout=5)
        assert loop.is_running is False

    @pytest.mark.asyncio
    async def test_loop_survives_a_failing_round(self):
        state = {"count": 0}

        async def sweep():
            state["count"] += 1
            if state["count"] == 1:
                raise RuntimeError("boom")
            return 0

        loop = QueueTimeoutSweepLoop(sweep=sweep, interval_seconds=1)
        loop.start()
        # 单轮抛异常不能让循环退出（否则一次数据库抖动静默关掉整个兜底）
        await asyncio.sleep(1.1)
        assert loop.is_running is True
        await asyncio.wait_for(loop.stop(), timeout=5)
        assert loop.is_running is False

    @pytest.mark.asyncio
    async def test_stop_does_not_loop_forever_on_pure_compute_sweep(self):
        """`stop()` 必须在有限时间内返回，即使 sweep 从不挂起。

        这是 Linux CI 上真实卡死过一次的回归：循环写 `while True` 时，`stop()`
        先 set 事件让 `wait_for` 立即返回，紧接着一轮纯计算的 sweep 又把控制权
        抢回去，`CancelledError` 没有机会投递，`await self._task` 永不返回。
        """

        async def sweep():
            return 0

        loop = QueueTimeoutSweepLoop(sweep=sweep, interval_seconds=1)
        loop.start()
        await asyncio.wait_for(loop.stop(), timeout=5)
        assert loop.is_running is False


class TestExpireQueueEntriesCas:
    """超时落库必须是带 `status='QUEUED'` 条件的 CAS（docs/04 §9.1）。

    SQLite 下 `with_for_update` 被忽略，普通 ORM UPDATE 会把「巡检 SELECT 之后、
    写回之前」刚被 worker 启动成 RUNNING 的任务覆盖回 TIMEOUT，已经花掉的算力和
    产物随之丢弃。这里用 monkeypatch 精确制造这个竞态窗口。
    """

    @pytest.mark.asyncio
    async def test_skips_row_started_by_worker_before_write(self, db_session, monkeypatch):
        """worker 在巡检拿到行之后、CAS 写回之前把它启动成 RUNNING。

        直接把库里的状态改成 RUNNING（不 commit、不同步 ORM），巡检手里的 ORM
        对象仍显示 QUEUED——正是真实竞态里巡检进程看到的样子。此时 CAS 应该
        匹配不到行，返回 False，并且**不能**归还资源租约（任务还在跑）。
        """
        import app.services.queue_timeout as queue_timeout_module

        owner = await _make_owner(db_session)
        task = await _make_task(
            db_session, owner, queued_at=utcnow() - timedelta(hours=7)
        )
        task_id = task.id

        await db_session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(status=TaskStatus.RUNNING.value)
            .execution_options(synchronize_session=False)
        )

        released: list[str] = []

        async def record_release(task, *, reason, **kwargs):
            released.append(reason)
            return False

        # 若 CAS 之前就归还租约，这里会记录到一次调用——正是要防的回归。
        monkeypatch.setattr(
            queue_timeout_module,
            "release_task_resource_reservation",
            record_release,
        )
        expired = await queue_timeout_module._expire_task_if_still_queued(
            db_session, task, window=21600
        )
        await db_session.commit()

        assert expired is False
        assert released == []
        db_session.expire_all()
        row = (
            await db_session.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert row.status == TaskStatus.RUNNING.value
        logs = (
            await db_session.execute(select(TaskLog).where(TaskLog.task_id == task_id))
        ).scalars().all()
        assert logs == []

    @pytest.mark.asyncio
    async def test_releases_reservation_only_after_cas_succeeds(self, db_session, monkeypatch):
        """CAS 命中后再归还租约，并把归还结果写回（否则配额状态丢失）。"""
        import app.services.queue_timeout as queue_timeout_module

        owner = await _make_owner(db_session)
        task = await _make_task(
            db_session, owner, queued_at=utcnow() - timedelta(hours=7)
        )
        task_id = task.id

        async def fake_release(task, *, reason, **kwargs):
            task.extra_data = {**(task.extra_data or {}), "lease_released": True}
            return True

        monkeypatch.setattr(
            queue_timeout_module,
            "release_task_resource_reservation",
            fake_release,
        )

        expired = await queue_timeout_module._expire_task_if_still_queued(
            db_session, task, window=21600
        )
        await db_session.commit()

        assert expired is True
        db_session.expire_all()
        row = (
            await db_session.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert row.status == TaskStatus.TIMEOUT.value
        assert row.extra_data["lease_released"] is True

    @pytest.mark.asyncio
    async def test_one_bad_row_does_not_abort_the_batch(self, db_session, monkeypatch):
        owner = await _make_owner(db_session)
        bad = await _make_task(
            db_session, owner, queued_at=utcnow() - timedelta(hours=7), suffix="-bad"
        )
        good = await _make_task(
            db_session, owner, queued_at=utcnow() - timedelta(hours=7), suffix="-good"
        )

        original = TaskStateMachine.mark_timeout

        def flaky_mark_timeout(task, **kwargs):
            if task.id == bad.id:
                raise RuntimeError("boom")
            return original(task, **kwargs)

        monkeypatch.setattr(
            TaskStateMachine, "mark_timeout", staticmethod(flaky_mark_timeout)
        )

        expired = await expire_timed_out_queue_entries(db_session, timeout_seconds=21600)
        await db_session.commit()

        assert expired == 1
        db_session.expire_all()
        rows = {
            row.id: row.status
            for row in (
                await db_session.execute(
                    select(Task).where(Task.id.in_((bad.id, good.id)))
                )
            ).scalars()
        }
        assert rows[bad.id] == TaskStatus.QUEUED.value
        assert rows[good.id] == TaskStatus.TIMEOUT.value
