"""项目配额、算力分钟核销与准入检查的行为测试（docs/04 §5.3、docs/05 §3/§9、G-9）。

覆盖面
------
1. **折算系数**：1 DCU·分钟 = 1、1 CPU 核·分钟 = 1/64、内存不计费——系数就是把
   「算力」这个词变成可计算量的全部定义，改一个数字所有历史用量都会变；
2. **成本容错**：脏数据（缺 ``resource_snapshot``、没有 ``started_at``、时长为负）
   退化成 0 而不是抛异常。核销是收尾动作，一条脏数据不能让整个终态提交失败；
3. **周期窗口**：DAILY/MONTHLY/NONE 三种口径；
4. **配额读写**：``get_or_create`` 幂等、部分更新、非法值拒绝，且不留下「改了一半」；
5. **准入检查**：没配 = 不限（**不是**零额度）、DCU 并发、CPU 并发（含 QUEUED）、
   分钟额度，以及 ``overdraft_ratio=1.2`` 时 110% 放行 / 120% 拦截；
6. **核销幂等**：同一轮次重复调用不双计；换了一轮（``retry_count`` 变了）才累加；
7. **状态机接入**：``transition()`` 到终态自动落成本（它覆盖所有终态路径）；
8. **补核销巡检**：历史终态任务没有 ``cost`` 时后台扫描补上；循环 ``stop()`` 不得挂死；
9. **API 契约**：``GET/PUT /projects/{id}/quota`` 的 camelCase 字段、权限口径、
   ``GET /compute/quota`` 汇总；``GET`` 是纯读（不建记录、``configured=false``），
   且**不改变准入结果**——「有没有人点开过配额页」不能影响项目能不能提交任务；
10. **端到端**：超额时 ``POST /api/v1/tasks`` 返回 429 且**不留下任何任务行**；
    删项目时 ``project_quotas`` 不残留。

测试隔离方式与 ``test/test_idempotency.py`` / ``test/test_projects_api.py`` 一致：
内存 SQLite + StaticPool + 覆盖 ``get_db``/``get_current_user``，并把
``direct_task_runner`` 换成不落地的桩。
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1 import tasks as tasks_api
from app.auth.dependencies import get_current_user
from app.common.exceptions import QuotaExceededException, ValidationException
from app.common.time import utcnow
from app.config import settings as config_settings
from app.database.base import Base
from app.database.session import get_db
from app.gpu.allocator import GPUAllocator
from app.main import app
from app.models.projects import Organization, Project, ProjectMember
from app.models.quotas import ProjectQuota
from app.models.targets import Protein, Target
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.schemas.tasks import TaskCreate
from app.schemas.targets import StructurePredict
from app.services.domain_targets import submit_structure_prediction
from app.services.project_migration import ensure_migration_project_for_owner
from app.services.project_quotas import (
    CPU_CORE_MINUTE_WEIGHT,
    DCU_MINUTE_WEIGHT,
    MEMORY_GB_MINUTE_WEIGHT,
    check_submission_allowed,
    compute_cost,
    cost_from_task,
    get_or_create_project_quota,
    load_project_quota,
    period_window,
    project_active_counts,
    project_usage_minutes,
    settle_finished_tasks,
    settle_task_cost_in_memory,
    update_project_quota,
)
from app.services.quota_maintenance import (
    QuotaSettlementLoop,
    build_quota_settlement_loop,
    run_quota_settlement_once,
)
from app.tasks.state_machine import TaskStateMachine
from app.tasks.service import create_and_schedule_tool_task


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


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
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session
    await engine.dispose()


async def _create_user(db: AsyncSession, email: str) -> User:
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
async def users(db_session: AsyncSession) -> dict[str, User]:
    return {
        "owner": await _create_user(db_session, "owner@example.com"),
        "editor": await _create_user(db_session, "editor@example.com"),
        "viewer": await _create_user(db_session, "viewer@example.com"),
        "outsider": await _create_user(db_session, "outsider@example.com"),
    }


async def _create_project(
    db: AsyncSession,
    *,
    owner: User,
    name: str = "Quota Project",
    slug: str | None = None,
    members: dict[str, User] | None = None,
) -> Project:
    organization = Organization(name=f"{name} Org", slug=slug or f"org-{name}-{utcnow().timestamp()}")
    db.add(organization)
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name=name,
        status="active",
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    for role, user in (members or {}).items():
        db.add(ProjectMember(project_id=project.id, user_id=user.id, role=role))
    await db.commit()
    await db.refresh(project)
    return project


async def _create_tool(
    db: AsyncSession,
    *,
    owner: User,
    gpu_required: bool = False,
    slug: str | None = None,
    config: dict | None = None,
) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name="Quota Tool",
        slug=slug or f"quota-tool-{utcnow().timestamp()}",
        description="Tool for quota tests",
        category="generation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        gpu_required=gpu_required,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config=config or {"type": "python_script"},
        is_active=True,
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    await db.commit()
    await db.refresh(tool)
    return tool


async def _create_task(
    db: AsyncSession,
    *,
    user: User,
    tool: Tool,
    project_id: str | None = None,
    status: str = TaskStatus.SUCCESS.value,
    gpu_index: int | None = None,
    execution_time_sec: int | None = None,
    extra_data: dict | None = None,
    finished_at=None,
) -> Task:
    payload: dict = dict(extra_data or {})
    if project_id:
        payload["project_id"] = str(project_id)
    task = Task(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        name="quota task",
        status=status,
        gpu_index=gpu_index,
        execution_time_sec=execution_time_sec,
        started_at=None,
        finished_at=finished_at if finished_at is not None else utcnow(),
        extra_data=payload,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@pytest.fixture
def direct_runner_stub(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    runner = SimpleNamespace(
        scheduled=[],
        cancelled=[],
        schedule_task=lambda task_id, tool_version_id: runner.scheduled.append(
            (task_id, tool_version_id)
        ),
        cancel_task=lambda task_id: runner.cancelled.append(task_id) or True,
    )
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)
    return runner


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession, users: dict[str, User], direct_runner_stub: SimpleNamespace
):
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
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        yield client
    app.dependency_overrides.clear()


def _headers(role: str = "owner") -> dict[str, str]:
    return {"Authorization": f"Bearer {role}"}


# ---------------------------------------------------------------------------
# 1) 折算系数
# ---------------------------------------------------------------------------


def test_compute_cost_uses_documented_weights():
    """60 秒 × 1 卡 = 1.0 DCU·分钟；60 秒 × 64 核 = 1.0 CPU 核·分钟；内存为 0。

    这三个数字是配额的度量单位本身，被改掉就等于所有历史用量换了单位。
    """
    assert DCU_MINUTE_WEIGHT == 1.0
    assert CPU_CORE_MINUTE_WEIGHT == 1.0 / 64
    assert MEMORY_GB_MINUTE_WEIGHT == 0.0

    dcu_only = compute_cost(duration_seconds=60, dcu_count=1)
    assert dcu_only.dcu_minutes == 1.0
    assert dcu_only.cpu_minutes == 0.0
    assert dcu_only.total_minutes == 1.0

    cpu_only = compute_cost(duration_seconds=60, cpu_cores=64)
    assert cpu_only.dcu_minutes == 0.0
    assert cpu_only.cpu_minutes == 1.0
    assert cpu_only.total_minutes == 1.0

    # 规格原文给的校验值：1 核 × 60 秒 = 1/64 = 0.015625（不是四舍五入后的近似值）。
    single_core = compute_cost(duration_seconds=60, cpu_cores=1)
    assert single_core.cpu_minutes == pytest.approx(0.015625)
    assert single_core.total_minutes == pytest.approx(0.015625)

    # 32 核跑 1 分钟 = 0.5 算力分钟（CPU 便宜 64 倍，不是一个数量级的便宜）。
    half = compute_cost(duration_seconds=60, cpu_cores=32)
    assert half.total_minutes == pytest.approx(0.5)

    assert compute_cost(duration_seconds=0, dcu_count=4, cpu_cores=64).total_minutes == 0.0

    # 负数（时钟回拨 / finished_at < started_at）按 0 处理，不能让用量倒退。
    negative = compute_cost(duration_seconds=-100, dcu_count=-2, cpu_cores=-8)
    assert negative.total_minutes == 0.0


def test_cost_from_task_tolerates_missing_fields():
    """任何字段缺失都退化成 0，绝不抛异常。"""
    bare = Task(id="t-bare", status=TaskStatus.SUCCESS.value, extra_data=None)
    assert cost_from_task(bare).total_minutes == 0.0

    snapshot = Task(
        id="t-snap",
        status=TaskStatus.SUCCESS.value,
        gpu_index=0,
        execution_time_sec=120,
        extra_data={
            "resource_snapshot": {
                "resource_request": {"cpu": 16, "gpu_count": 1},
            }
        },
    )
    cost = cost_from_task(snapshot)
    # 2 分钟 × 1 卡 = 2.0；2 分钟 × 16 核 / 64 = 0.5
    assert cost.dcu_minutes == pytest.approx(2.0)
    assert cost.cpu_minutes == pytest.approx(0.5)
    assert cost.total_minutes == pytest.approx(2.5)

    # extra_data 结构坏掉（字符串而不是 dict）也不能炸。
    broken = Task(id="t-broken", status=TaskStatus.SUCCESS.value, extra_data="oops")
    assert cost_from_task(broken).total_minutes == 0.0

    # A-2 根因路径：``gpu_index`` 非空但**整份 ``resource_snapshot`` 缺失**。
    # 只认 ``resource_request.gpu_count`` 的实现会在这里返回 0 张卡——而快照缺失
    # 恰恰是最常见的情形（历史行、非平台下发的行、extra_data 被别的写入方覆盖过）。
    no_snapshot = Task(
        id="t-no-snapshot",
        status=TaskStatus.SUCCESS.value,
        gpu_index=0,
        execution_time_sec=120,
        extra_data={},
    )
    assert cost_from_task(no_snapshot).dcu_minutes == pytest.approx(2.0)
    assert cost_from_task(no_snapshot).cpu_minutes == 0.0


def test_duration_falls_back_to_timestamps_when_execution_time_missing():
    """``execution_time_sec`` 为空时用 ``finished_at - started_at``，不是直接归零。

    这条不是形式主义：``execution_time_sec`` 只在 worker 正常收尾时写，
    远端结果补回、直接改库修数据、worker 崩溃后由巡检定终态的行都可能是空的。
    直接归零等于这些任务全部免费。
    """
    started = utcnow() - timedelta(seconds=90)
    task = Task(
        id="t-timestamps",
        status=TaskStatus.SUCCESS.value,
        gpu_index=0,
        started_at=started,
        finished_at=started + timedelta(seconds=90),
        execution_time_sec=None,
        extra_data={},
    )
    cost = cost_from_task(task)
    assert cost.dcu_minutes == pytest.approx(1.5, abs=0.01)

    # ``execution_time_sec`` 优先于时间戳：它才是执行器实测的时长，
    # 时间戳含排队与收尾开销，两者不一致时以执行器上报为准。
    with_exec_time = Task(
        id="t-priority",
        status=TaskStatus.SUCCESS.value,
        gpu_index=0,
        started_at=started,
        finished_at=started + timedelta(seconds=90),
        execution_time_sec=600,
        extra_data={},
    )
    assert cost_from_task(with_exec_time).dcu_minutes == pytest.approx(10.0)

    # 只有 started_at、没有 finished_at：时长未知 → 0，不能拿「现在」去减，
    # 否则一个卡住的任务会被越算越多。
    only_started = Task(
        id="t-open",
        status=TaskStatus.RUNNING.value,
        gpu_index=0,
        started_at=utcnow() - timedelta(days=3),
        finished_at=None,
        execution_time_sec=None,
        extra_data={},
    )
    assert cost_from_task(only_started).total_minutes == 0.0


def test_cost_from_task_keeps_dcu_when_gpu_index_already_released():
    """A-2 回归：``gpu_index`` 已被清空，但 ``allocatedDcuCount`` 还在。

    这条路径是**事后补核销**的真实形状：``gpu_index`` 在任务释放时被置空
    （``app/gpu/allocator.py`` 三处 ``values(gpu_index=None)``、``factory.py`` 的
    ``self.task.gpu_index = None``），而被巡检捞出来核销时早就过了那个时刻。
    若只认 ``gpu_index``，一个真跑了 2 小时 DCU 的任务会被当成 CPU 任务：
    权重从 1.0 掉到 1/64，**少扣一个数量级**。
    """
    released = Task(
        id="t-dcu-released",
        status=TaskStatus.SUCCESS.value,
        gpu_index=None,  # 已释放
        execution_time_sec=7200,  # 2 小时
        extra_data={
            "allocatedDcuCount": 1,
            # 工具 gpu_required=False 但 profile 配了 GPU 时，这里也会是 0：
            "resource_snapshot": {
                "resource_request": {"cpu": 8, "gpu_count": 0},
            },
        },
    )
    cost = cost_from_task(released)
    assert cost.dcu_minutes == pytest.approx(120.0), "2 小时 × 1 卡 必须是 120 DCU·分钟"
    assert cost.cpu_minutes == pytest.approx(15.0)
    assert cost.total_minutes == pytest.approx(135.0)

    # 对照组：没有 allocatedDcuCount 也没有 gpu_index 的历史行，只能按 CPU 记。
    # 这说明该键确实是「补回 DCU 身份」的唯一依据，不是随手能被别的字段代替的。
    legacy = Task(
        id="t-legacy-cpu",
        status=TaskStatus.SUCCESS.value,
        gpu_index=None,
        execution_time_sec=7200,
        extra_data={"resource_snapshot": {"resource_request": {"cpu": 8, "gpu_count": 0}}},
    )
    assert cost_from_task(legacy).dcu_minutes == 0.0


def test_allocated_dcu_count_key_wins_over_stale_snapshot():
    """同一个任务上三个来源冲突时，``allocatedDcuCount`` 优先。

    分配是**已发生的事实**，快照是**下发前的声明**：工具没声明 GPU 但运行时真占了
    卡时，两者必然矛盾，此时以事实为准。
    """
    conflicting = Task(
        id="t-conflict",
        status=TaskStatus.SUCCESS.value,
        gpu_index=None,
        execution_time_sec=60,
        extra_data={
            "allocatedDcuCount": 1,
            "resource_snapshot": {"resource_request": {"cpu": 0, "gpu_count": 0}},
        },
    )
    assert cost_from_task(conflicting).dcu_minutes == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_settle_finished_tasks_recovers_dcu_after_gpu_release(
    db_session: AsyncSession, users: dict[str, User]
):
    """A-2 的端到端形状：终态任务 ``gpu_index`` 为 NULL，巡检仍要按 DCU 核销。"""
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"])
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.SUCCESS.value,
        gpu_index=None,
        execution_time_sec=3600,
        extra_data={
            "allocatedDcuCount": 1,
            "resource_snapshot": {"resource_request": {"cpu": 64, "gpu_count": 0}},
        },
    )

    assert await settle_finished_tasks(db_session, limit=10) == 1

    extra = (
        await db_session.execute(select(Task.extra_data))
    ).scalar_one()
    # 1 小时 × 1 卡 = 60；1 小时 × 64 核 / 64 = 60。
    assert extra["cost"]["dcuMinutes"] == pytest.approx(60.0)
    assert extra["cost"]["totalMinutes"] == pytest.approx(120.0)
    usage = await project_usage_minutes(
        db_session, project_id=project.id, period="DAILY"
    )
    assert usage == pytest.approx(120.0)


def test_period_window_daily_monthly_and_none():
    """DAILY 从今天 00:00 起、MONTHLY 从本月 1 日 00:00 起、NONE 无起点。"""
    moment = utcnow().replace(day=15, hour=13, minute=45, second=30, microsecond=0)

    daily_start, daily_end = period_window("DAILY", now=moment)
    assert daily_start == moment.replace(hour=0, minute=0, second=0, microsecond=0)
    assert daily_end == moment

    monthly_start, _ = period_window("MONTHLY", now=moment)
    assert monthly_start.day == 1
    assert (monthly_start.hour, monthly_start.minute, monthly_start.second) == (0, 0, 0)

    none_start, none_end = period_window("NONE", now=moment)
    assert none_start is None
    assert none_end == moment


# ---------------------------------------------------------------------------
# 2) 配额读写
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_project_quota_is_idempotent_with_defaults(
    db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])

    # 没有记录 = 不限，不是「零配额」。这个区分是整套逻辑的前提。
    assert await load_project_quota(db_session, project_id=project.id) is None

    first = await get_or_create_project_quota(
        db_session, project_id=project.id, created_by=str(users["owner"].id)
    )
    assert first.max_concurrent_dcu == 2
    assert first.max_concurrent_cpu_tasks == 10
    assert first.daily_quota_minutes == 0
    assert first.max_single_task_minutes == 1440
    assert first.quota_period == "DAILY"
    assert first.updated_by == str(users["owner"].id)

    second = await get_or_create_project_quota(db_session, project_id=project.id)
    assert second.id == first.id
    rows = (
        await db_session.execute(
            select(func.count()).select_from(ProjectQuota).where(
                ProjectQuota.project_id == project.id
            )
        )
    ).scalar_one()
    assert rows == 1


@pytest.mark.asyncio
async def test_project_quota_model_defaults_and_unique_constraint(
    db_session: AsyncSession, users: dict[str, User]
):
    """列默认值 + ``project_id`` 唯一：一个项目只能有一份配额。"""
    project = await _create_project(db_session, owner=users["owner"])
    quota = ProjectQuota(project_id=project.id)
    db_session.add(quota)
    await db_session.commit()
    await db_session.refresh(quota)

    # 这些默认值同时是「没配过」的项目第一次 GET 之后生效的上限，不能随手改。
    assert quota.max_concurrent_dcu == 2
    assert quota.max_concurrent_cpu_tasks == 10
    assert quota.daily_quota_minutes == 0
    assert quota.max_single_task_minutes == 1440
    assert quota.quota_period == "DAILY"
    assert Decimal(str(quota.overdraft_ratio)) == Decimal("1.00")
    assert quota.updated_by is None

    db_session.add(ProjectQuota(project_id=project.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_update_project_quota_is_partial_and_validates(
    db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])
    quota = await get_or_create_project_quota(db_session, project_id=project.id)

    updated = await update_project_quota(
        db_session,
        quota=quota,
        updated_by=str(users["owner"].id),
        daily_quota_minutes=500,
        quota_period="MONTHLY",
    )
    # 只改了传进来的两个字段，其余保持默认。
    assert updated.daily_quota_minutes == 500
    assert updated.quota_period == "MONTHLY"
    assert updated.max_concurrent_dcu == 2

    with pytest.raises(ValidationException):
        await update_project_quota(
            db_session, quota=quota, updated_by=None, max_concurrent_dcu=-1
        )
    with pytest.raises(ValidationException):
        await update_project_quota(
            db_session, quota=quota, updated_by=None, overdraft_ratio=0.5
        )
    with pytest.raises(ValidationException):
        await update_project_quota(
            db_session, quota=quota, updated_by=None, quota_period="WEEKLY"
        )
    # 校验失败后对象没被污染：仍是上次成功写入的值。
    await db_session.refresh(quota)
    assert quota.max_concurrent_dcu == 2
    assert quota.quota_period == "MONTHLY"
    assert Decimal(str(quota.overdraft_ratio)) == Decimal("1.00")


# ---------------------------------------------------------------------------
# 3) 占用统计与准入
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_active_counts_separates_running_dcu_and_queued_cpu(
    db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"])

    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.RUNNING.value, gpu_index=0,
    )
    # 排队中的无卡任务也算占用：名额是在提交时抢的。
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.QUEUED.value, gpu_index=None,
    )
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.RUNNING.value, gpu_index=None,
    )
    # 终态不计入占用。
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.SUCCESS.value, gpu_index=0,
    )

    counts = await project_active_counts(db_session, project_id=project.id)
    assert counts == {"dcu": 1, "cpu": 2}


@pytest.mark.asyncio
async def test_check_submission_allowed_is_unlimited_without_record(
    db_session: AsyncSession, users: dict[str, User]
):
    """没有配额记录时一律放行——否则升级那一刻所有存量项目都提交不了任务。"""
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"])
    for _ in range(5):
        await _create_task(
            db_session, user=users["owner"], tool=tool, project_id=project.id,
            status=TaskStatus.RUNNING.value, gpu_index=0,
        )

    # 不抛即通过。
    await check_submission_allowed(db_session, project_id=project.id, requires_dcu=True)
    await check_submission_allowed(db_session, project_id=project.id, requires_dcu=False)


@pytest.mark.asyncio
async def test_check_submission_allowed_blocks_dcu_concurrency(
    db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"])
    quota = await get_or_create_project_quota(db_session, project_id=project.id)
    await update_project_quota(
        db_session, quota=quota, updated_by=None, max_concurrent_dcu=1,
        daily_quota_minutes=0,
    )
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.RUNNING.value, gpu_index=0,
    )

    with pytest.raises(QuotaExceededException) as excinfo:
        await check_submission_allowed(db_session, project_id=project.id, requires_dcu=True)
    assert excinfo.value.code == 429
    assert excinfo.value.detail["dimension"] == "maxConcurrentDcu"
    assert excinfo.value.detail["limit"] == 1
    assert excinfo.value.detail["active"] == 1

    # CPU 提交不受 DCU 并发影响。
    await check_submission_allowed(db_session, project_id=project.id, requires_dcu=False)


@pytest.mark.asyncio
async def test_check_submission_allowed_counts_queued_cpu_tasks(
    db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"])
    quota = await get_or_create_project_quota(db_session, project_id=project.id)
    await update_project_quota(
        db_session, quota=quota, updated_by=None, max_concurrent_cpu_tasks=2,
        daily_quota_minutes=0,
    )
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.QUEUED.value, gpu_index=None,
    )
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.RUNNING.value, gpu_index=None,
    )

    with pytest.raises(QuotaExceededException) as excinfo:
        await check_submission_allowed(db_session, project_id=project.id, requires_dcu=False)
    assert excinfo.value.detail["dimension"] == "maxConcurrentCpuTasks"
    assert excinfo.value.detail["active"] == 2


@pytest.mark.asyncio
async def test_check_submission_allowed_enforces_max_single_task_minutes(
    db_session: AsyncSession, users: dict[str, User]
):
    """E-1 回归：``max_single_task_minutes`` 必须在准入时真的校验。

    此前它只存进库、在 GET 里返回，用户以为生效实际没有任何执行点——
    「看起来生效但其实没有」比不提供这个字段更糟。
    """
    project = await _create_project(db_session, owner=users["owner"])
    quota = await get_or_create_project_quota(db_session, project_id=project.id)
    await update_project_quota(
        db_session, quota=quota, updated_by=None, max_single_task_minutes=60
    )

    # 恰好 60 分钟：放行（边界不拒）。
    await check_submission_allowed(
        db_session, project_id=project.id, requires_dcu=False, timeout_sec=3600
    )

    with pytest.raises(QuotaExceededException) as excinfo:
        await check_submission_allowed(
            db_session, project_id=project.id, requires_dcu=False, timeout_sec=7200
        )
    assert excinfo.value.code == 429
    assert excinfo.value.detail["dimension"] == "maxSingleTaskMinutes"
    assert excinfo.value.detail["limitMinutes"] == 60
    assert excinfo.value.detail["requestedMinutes"] == pytest.approx(120.0)
    # 语义必须是「拒绝下发」，不是「跑超了 kill」——后者本期不实现。
    assert excinfo.value.detail["enforced"] == "admission"

    # 0 = 不限：这是默认值，不能让任何提交因为「没配」被拒。
    await update_project_quota(
        db_session, quota=quota, updated_by=None, max_single_task_minutes=0
    )
    await check_submission_allowed(
        db_session, project_id=project.id, requires_dcu=False, timeout_sec=86400
    )

    # 调用方没有快照（``timeout_sec=None``）时跳过这项校验，不是当无限时长。
    await update_project_quota(
        db_session, quota=quota, updated_by=None, max_single_task_minutes=60
    )
    await check_submission_allowed(
        db_session, project_id=project.id, requires_dcu=False, timeout_sec=None
    )


@pytest.mark.asyncio
async def test_overdraft_ratio_allows_110_percent_and_blocks_120_percent(
    db_session: AsyncSession, users: dict[str, User]
):
    """``overdraft_ratio=1.2`` → 110% 放行、120% 拦截（同一判据也用于 ``exceeded``）。"""
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"])
    quota = await get_or_create_project_quota(db_session, project_id=project.id)
    await update_project_quota(
        db_session,
        quota=quota,
        updated_by=None,
        daily_quota_minutes=100,
        overdraft_ratio=1.2,
        max_concurrent_dcu=100,
        max_concurrent_cpu_tasks=100,
    )

    def _settled(minutes: float) -> dict:
        return {
            "cost": {
                "dcuMinutes": minutes,
                "cpuMinutes": 0.0,
                "totalMinutes": minutes,
                "settledAt": "2026-10-26T00:00:00Z",
            }
        }

    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        gpu_index=0, extra_data=_settled(110.0), finished_at=utcnow(),
    )
    assert await project_usage_minutes(
        db_session, project_id=project.id, period="DAILY"
    ) == pytest.approx(110.0)
    # 110 < 100 × 1.2：允许。
    await check_submission_allowed(db_session, project_id=project.id, requires_dcu=True)

    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        gpu_index=0, extra_data=_settled(10.0), finished_at=utcnow(),
    )
    # 120 >= 100 × 1.2：拦截。
    with pytest.raises(QuotaExceededException) as excinfo:
        await check_submission_allowed(db_session, project_id=project.id, requires_dcu=True)
    assert excinfo.value.detail["dimension"] == "dailyQuotaMinutes"
    assert excinfo.value.detail["usedMinutes"] == pytest.approx(120.0)
    assert excinfo.value.detail["overdraftRatio"] == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# 4) 核销
# ---------------------------------------------------------------------------


def test_settle_task_cost_in_memory_ignores_non_terminal():
    running = Task(id="t-running", status=TaskStatus.RUNNING.value, extra_data={})
    assert settle_task_cost_in_memory(running) is None
    assert "cost" not in (running.extra_data or {})


def test_settle_task_cost_is_idempotent_per_attempt():
    """同一轮次重复核销不双计；``retry_count`` 变了才累加（失败重跑也要计入）。"""
    task = Task(
        id="t-settle",
        status=TaskStatus.SUCCESS.value,
        gpu_index=0,
        execution_time_sec=60,
        retry_count=0,
        extra_data={"resource_snapshot": {"resource_request": {"cpu": 64}}},
    )

    first = settle_task_cost_in_memory(task)
    assert first is not None
    # 1 分钟 × 1 卡 = 1.0；1 分钟 × 64 核 = 1.0
    assert first.total_minutes == pytest.approx(2.0)
    assert task.extra_data["cost"]["totalMinutes"] == pytest.approx(2.0)
    assert task.extra_data["cost"]["settledAt"].endswith("Z")
    assert task.extra_data["cost"]["settledAttempt"] == 0

    again = settle_task_cost_in_memory(task)
    assert again.total_minutes == pytest.approx(2.0)
    assert task.extra_data["cost"]["totalMinutes"] == pytest.approx(2.0)

    # 第二轮（重试后再次成功）：成本累加，历史保留。
    task.retry_count = 1
    second = settle_task_cost_in_memory(task)
    assert second.total_minutes == pytest.approx(4.0)
    assert task.extra_data["cost"]["totalMinutes"] == pytest.approx(4.0)
    assert task.extra_data["cost"]["settledAttempt"] == 1
    assert len(task.extra_data["cost"]["history"]) == 1
    assert task.extra_data["cost"]["history"][0]["attempt"] == 0


def test_state_machine_transition_settles_cost():
    """所有终态路径都经过 ``transition()``，核销写在这里才没有漏口。"""
    task = Task(
        id="t-sm",
        status=TaskStatus.RUNNING.value,
        gpu_index=0,
        started_at=utcnow() - timedelta(seconds=120),
        extra_data={"resource_snapshot": {"resource_request": {"cpu": 32}}},
    )

    TaskStateMachine.transition(task, TaskStatus.SUCCESS)

    cost = (task.extra_data or {}).get("cost")
    assert cost is not None
    assert cost["totalMinutes"] == pytest.approx(3.0, abs=0.05)
    assert cost["dcuMinutes"] == pytest.approx(2.0, abs=0.05)
    assert cost["cpuMinutes"] == pytest.approx(1.0, abs=0.05)


@pytest.mark.asyncio
async def test_settle_finished_tasks_backfills_legacy_rows(
    db_session: AsyncSession, users: dict[str, User]
):
    """状态机只管「经过它」的转换；历史终态行由巡检补核销。"""
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"])
    for _ in range(2):
        await _create_task(
            db_session, user=users["owner"], tool=tool, project_id=project.id,
            status=TaskStatus.FAILURE.value, gpu_index=0, execution_time_sec=60,
            extra_data={"resource_snapshot": {"resource_request": {"cpu": 64}}},
        )
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.RUNNING.value, gpu_index=0,
    )

    assert await settle_finished_tasks(db_session, limit=10) == 2
    # 幂等：同一批不会再核销第二遍。
    assert await settle_finished_tasks(db_session, limit=10) == 0

    rows = (
        await db_session.execute(
            select(Task.extra_data).where(Task.status == TaskStatus.FAILURE.value)
        )
    ).scalars().all()
    assert len(rows) == 2
    for extra in rows:
        # 失败同样核销：否则可以反复失败来白嫖算力。
        assert extra["cost"]["totalMinutes"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_settle_finished_tasks_advances_past_already_settled_batch(
    db_session: AsyncSession, users: dict[str, User]
):
    """A-1 回归：已核销的行不占本轮的 ``limit``，游标必须能往后推进。

    这是「永不推进」缺陷的形状：早期实现只按 ``finished_at`` 取前 ``batch`` 条、
    在 Python 里 ``continue`` 掉已核销的。一旦最早的 ``batch`` 条全部核销完，
    每轮都会取回同一批、全部跳过、返回 0——而 ``batch = limit * 4``，所以
    只要「已核销的早于未核销的」超过 4 × limit，后面那条就永远捞不到。
    这里造 ``limit * 4 + 5`` 条已核销的行垫在前面，再放 1 条待核销的。
    """
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"])
    base = utcnow() - timedelta(days=2)

    settled_cost = {
        "cost": {
            "dcuMinutes": 1.0,
            "cpuMinutes": 0.0,
            "totalMinutes": 1.0,
            "settledAt": "2026-10-01T00:00:00Z",
        }
    }
    for index in range(9):  # limit=2 → batch=8，9 > 8 才逼出「取不到」的旧行为
        await _create_task(
            db_session, user=users["owner"], tool=tool, project_id=project.id,
            status=TaskStatus.SUCCESS.value, gpu_index=0, execution_time_sec=60,
            finished_at=base + timedelta(minutes=index),
            extra_data=dict(settled_cost),
        )
    pending = await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.SUCCESS.value, gpu_index=0, execution_time_sec=60,
        finished_at=base + timedelta(days=1),
        extra_data={"resource_snapshot": {"resource_request": {"cpu": 64}}},
    )

    assert await settle_finished_tasks(db_session, limit=2) == 1

    await db_session.refresh(pending)
    # 1 分钟 × 1 卡 = 1.0（gpu_index 还在，DCU 口径），1 分钟 × 64 核 / 64 = 1.0。
    assert pending.extra_data["cost"]["totalMinutes"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_run_quota_settlement_once_rejects_non_positive_batch(
    db_session: AsyncSession, users: dict[str, User]
):
    """``batch_size <= 0`` 直接返 0，不连库（避免误配成 0 时全表扫描）。"""
    assert await run_quota_settlement_once(batch_size=0) == 0
    assert await run_quota_settlement_once(batch_size=-5) == 0


@pytest.mark.asyncio
async def test_loop_stop_returns_promptly_for_pure_compute_sweep():
    """回归：``stop()`` 必须先置事件再 cancel，否则纯计算的 sweep 会让循环永不退出。

    sweep 直接 ``return 0``、**不含任何 ``await`` 挂起点**——这正是仓库刚踩过的坑：
    ``while True`` + 只靠 ``cancel()`` 时,一个纯计算单轮跑完后循环立刻进入下一轮，
    ``CancelledError`` 没有落点，``stop()`` 会永久挂住（CI 挂死 45 分钟）。
    """
    calls: list[int] = []

    async def sweep() -> int:
        calls.append(1)
        return 0

    loop = QuotaSettlementLoop(sweep=sweep, interval_seconds=1.0)
    loop.start()
    assert loop.is_running is True
    await asyncio.sleep(0.05)
    assert calls, "循环跑起来后至少应执行过一轮"

    await asyncio.wait_for(loop.stop(), timeout=5)
    assert loop.is_running is False

    # 重复 stop 是安全的。
    await asyncio.wait_for(loop.stop(), timeout=5)


def test_state_machine_settles_cost_after_worker_commits_it():
    """核销写在 ``transition()`` 里 → worker 不需要额外改动（规格要求核实并写进报告）。

    这里只断言「成本在 transition 结束时已在内存中」，落库由持有 session 的调用方
    用同一次 commit 完成；``test_settle_finished_tasks_backfills_legacy_rows``
    覆盖了「没经过 transition 的老数据」。
    """
    task = Task(id="t-worker-shape", status=TaskStatus.RUNNING.value, extra_data={})
    assert (task.extra_data or {}).get("cost") is None
    TaskStateMachine.transition(task, TaskStatus.FAILURE)
    assert task.extra_data["cost"]["totalMinutes"] == 0.0


def test_build_quota_settlement_loop_respects_switch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config_settings, "PROJECT_QUOTA_ENABLED", False, raising=False)
    assert build_quota_settlement_loop() is None
    monkeypatch.setattr(config_settings, "PROJECT_QUOTA_ENABLED", True, raising=False)
    built = build_quota_settlement_loop()
    assert built is not None


# ---------------------------------------------------------------------------
# 5) API：/projects/{id}/quota、/compute/quota
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_project_quota_returns_camel_case_defaults(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/quota", headers=_headers("owner")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["projectId"] == project.id
    assert data["maxConcurrentDcu"] == 2
    assert data["maxConcurrentCpuTasks"] == 10
    assert data["dailyQuotaMinutes"] == 0
    assert data["maxSingleTaskMinutes"] == 1440
    assert data["quotaPeriod"] == "DAILY"
    assert data["overdraftRatio"] == pytest.approx(1.0)
    assert data["usedMinutes"] == 0.0
    # 不限额时必须给 None；给 0 会被前端渲染成「额度已用尽」。
    assert data["remainingMinutes"] is None
    assert data["activeDcuTasks"] == 0
    assert data["activeCpuTasks"] == 0
    assert data["exceeded"] is False
    # 没配过 → 没有「谁在什么时候配的」，也明确标出这是默认值。
    assert data["configured"] is False
    assert data["updatedAt"] is None
    assert data["updatedBy"] is None


@pytest.mark.asyncio
async def test_get_quota_does_not_create_a_row(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    """GET 是纯读：查完之后库里仍然没有配额记录。

    这是本缺陷的核心回归：``check_submission_allowed`` 里「无记录 = 不限」，
    一旦 GET 落一条默认记录（``max_concurrent_dcu=2``），「有没有人点开过配额页」
    就会决定这个项目能不能提交任务。
    """
    project = await _create_project(db_session, owner=users["owner"])
    assert await load_project_quota(db_session, project_id=project.id) is None

    for _ in range(3):  # 多查几次也不能攒出记录
        response = await api_client.get(
            f"/api/v1/projects/{project.id}/quota", headers=_headers("owner")
        )
        assert response.status_code == 200

    # 用独立 session 复核，排除「对象还在身份映射里没落盘」的假阴性。
    async with async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )() as probe:
        count = (
            await probe.execute(
                select(func.count())
                .select_from(ProjectQuota)
                .where(ProjectQuota.project_id == project.id)
            )
        ).scalar_one()
    assert count == 0
    assert await load_project_quota(db_session, project_id=project.id) is None


@pytest.mark.asyncio
async def test_get_quota_reports_default_values_as_unconfigured(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    """默认值要标 ``configured=false``，让前端能区分「没配」与「配了 2 张」。"""
    project = await _create_project(db_session, owner=users["owner"])

    body = (
        await api_client.get(
            f"/api/v1/projects/{project.id}/quota", headers=_headers("owner")
        )
    ).json()["data"]
    assert body["configured"] is False
    # 默认值本身仍然要给出来（前端一套渲染），只是标明它不是管理员配的。
    assert body["maxConcurrentDcu"] == 2

    # PUT 之后同一字段变为「已配置」。
    await api_client.put(
        f"/api/v1/projects/{project.id}/quota",
        headers=_headers("owner"),
        json={"maxConcurrentDcu": 2},
    )
    configured = (
        await api_client.get(
            f"/api/v1/projects/{project.id}/quota", headers=_headers("owner")
        )
    ).json()["data"]
    assert configured["configured"] is True
    assert configured["maxConcurrentDcu"] == 2
    assert configured["updatedAt"].endswith("Z")


@pytest.mark.asyncio
async def test_get_quota_does_not_change_submission_behaviour(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    """语义守护：GET 之前与之后，准入判断必须完全一致。

    项目有 3 个在跑的 DCU 任务、没有配额记录 → 默认值 ``max_concurrent_dcu=2``
    若因 GET 落库而生效，第 4 次提交就会被拦；「点开过配额页」不该改变业务结果。
    """
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"], gpu_required=True)
    for index in range(3):
        await _create_task(
            db_session,
            user=users["owner"],
            tool=tool,
            project_id=project.id,
            status=TaskStatus.RUNNING.value,
            gpu_index=index,
        )

    # GET 之前：没记录 = 不限，不抛。
    await check_submission_allowed(db_session, project_id=project.id, requires_dcu=True)

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/quota", headers=_headers("owner")
    )
    assert response.status_code == 200
    assert response.json()["data"]["activeDcuTasks"] == 3

    # GET 之后：仍然不抛。若 GET 建了记录，这里会抛 QuotaExceededException。
    await check_submission_allowed(db_session, project_id=project.id, requires_dcu=True)
    assert await load_project_quota(db_session, project_id=project.id) is None


@pytest.mark.asyncio
async def test_get_project_quota_requires_membership(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])
    response = await api_client.get(
        f"/api/v1/projects/{project.id}/quota", headers=_headers("outsider")
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_project_quota_accepts_camel_case_and_persists(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])

    response = await api_client.put(
        f"/api/v1/projects/{project.id}/quota",
        headers=_headers("owner"),
        json={"maxConcurrentDcu": 5, "dailyQuotaMinutes": 600, "overdraftRatio": 1.5},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["maxConcurrentDcu"] == 5
    assert data["dailyQuotaMinutes"] == 600
    assert data["overdraftRatio"] == pytest.approx(1.5)
    # 未传字段保持原值。
    assert data["maxConcurrentCpuTasks"] == 10
    assert data["remainingMinutes"] == pytest.approx(600.0)

    quota = await load_project_quota(db_session, project_id=project.id)
    assert quota.max_concurrent_dcu == 5
    assert quota.updated_by == str(users["owner"].id)


@pytest.mark.asyncio
async def test_put_project_quota_rejects_empty_and_unknown_fields(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])

    empty = await api_client.put(
        f"/api/v1/projects/{project.id}/quota", headers=_headers("owner"), json={}
    )
    assert empty.status_code == 422

    unknown = await api_client.put(
        f"/api/v1/projects/{project.id}/quota",
        headers=_headers("owner"),
        json={"maxConcurrentDcu": 3, "nonsense": 1},
    )
    assert unknown.status_code == 422


@pytest.mark.asyncio
async def test_put_project_quota_rejects_invalid_overdraft_ratio(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])

    response = await api_client.put(
        f"/api/v1/projects/{project.id}/quota",
        headers=_headers("owner"),
        json={"overdraftRatio": 0.5},
    )
    assert response.status_code == 422
    assert response.json()["code"] == 422
    # 校验失败不留半状态。
    assert await load_project_quota(db_session, project_id=project.id) is None


@pytest.mark.asyncio
async def test_editor_cannot_write_quota_but_viewer_can_read(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(
        db_session,
        owner=users["owner"],
        members={"editor": users["editor"], "viewer": users["viewer"]},
    )

    denied = await api_client.put(
        f"/api/v1/projects/{project.id}/quota",
        headers=_headers("editor"),
        json={"maxConcurrentDcu": 9},
    )
    assert denied.status_code == 403

    readable = await api_client.get(
        f"/api/v1/projects/{project.id}/quota", headers=_headers("viewer")
    )
    assert readable.status_code == 200
    assert readable.json()["data"]["maxConcurrentDcu"] == 2


@pytest.mark.asyncio
async def test_compute_quota_summary_aggregates_owned_projects(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    owner = users["owner"]
    tool = await _create_tool(db_session, owner=owner)
    first = await _create_project(db_session, owner=owner, name="Alpha", slug="org-alpha")
    second = await _create_project(db_session, owner=owner, name="Beta", slug="org-beta")
    # 用户看得到、但没配额度的项目不应进分母。
    unconfigured = await _create_project(db_session, owner=owner, name="Gamma", slug="org-gamma")

    for project, minutes in ((first, 100), (second, 50)):
        quota = await get_or_create_project_quota(db_session, project_id=project.id)
        await update_project_quota(
            db_session, quota=quota, updated_by=None, daily_quota_minutes=minutes
        )
    await _create_task(
        db_session, user=owner, tool=tool, project_id=first.id, gpu_index=0,
        extra_data={
            "cost": {
                "dcuMinutes": 30.0,
                "cpuMinutes": 0.0,
                "totalMinutes": 30.0,
                "settledAt": "2026-10-26T00:00:00Z",
            }
        },
        finished_at=utcnow(),
    )
    assert unconfigured is not None

    response = await api_client.get("/api/v1/compute/quota", headers=_headers("owner"))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["projectCount"] == 2
    assert data["limitMinutes"] == 150
    assert data["usedTotalMinutes"] == pytest.approx(30.0)
    assert data["remainingMinutes"] == pytest.approx(120.0)
    assert data["period"] == "DAILY"
    assert data["exceeded"] is False

    # 没项目的用户拿到全零汇总，而不是 500。
    empty = await api_client.get("/api/v1/compute/quota", headers=_headers("outsider"))
    assert empty.status_code == 200
    assert empty.json()["data"]["projectCount"] == 0


# ---------------------------------------------------------------------------
# 6) 端到端：提交拦截 + 删项目
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task_blocked_by_quota_leaves_no_task_row(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"], gpu_required=True)
    quota = await get_or_create_project_quota(db_session, project_id=project.id)
    await update_project_quota(
        db_session, quota=quota, updated_by=None, max_concurrent_dcu=1
    )
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.RUNNING.value, gpu_index=0,
    )

    before = (
        await db_session.execute(select(func.count()).select_from(Task))
    ).scalar_one()

    response = await api_client.post(
        "/api/v1/tasks",
        headers=_headers("owner"),
        json={
            "tool_id": tool.id,
            "project_id": project.id,
            "name": "blocked by quota",
            "params": {},
        },
    )
    assert response.status_code == 429
    body = response.json()
    assert body["code"] == 429
    assert body["detail"]["dimension"] == "maxConcurrentDcu"

    after = (
        await db_session.execute(select(func.count()).select_from(Task))
    ).scalar_one()
    # 拦在 create_and_schedule_tool_task 之前：连 PENDING 空壳都不留。
    assert after == before


@pytest.mark.asyncio
async def test_delete_project_removes_quota_row(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    project = await _create_project(db_session, owner=users["owner"])
    await get_or_create_project_quota(db_session, project_id=project.id)
    assert await load_project_quota(db_session, project_id=project.id) is not None

    response = await api_client.delete(
        f"/api/v1/projects/{project.id}", headers=_headers("owner")
    )
    assert response.status_code == 200

    left = (
        await db_session.execute(
            select(func.count()).select_from(ProjectQuota).where(
                ProjectQuota.project_id == project.id
            )
        )
    ).scalar_one()
    # 普通外键在 SQLite 不强制；孤儿行会让同名新项目沿用旧配额。
    assert left == 0


# ---------------------------------------------------------------------------
# 7) B-1/B-2：准入必须覆盖所有建任务入口，且按最终项目落点判定
# ---------------------------------------------------------------------------


async def _create_target_and_protein(
    db: AsyncSession, *, project: Project, owner: User
) -> tuple[Target, Protein]:
    target = Target(project_id=project.id, created_by=owner.id, name="Quota Target")
    db.add(target)
    await db.flush()
    protein = Protein(
        target_id=target.id, name="Quota Protein", sequence="MKV", seq_length=3
    )
    db.add(protein)
    await db.commit()
    await db.refresh(protein)
    return target, protein


@pytest.mark.asyncio
async def test_structure_prediction_is_blocked_by_quota(
    db_session: AsyncSession, users: dict[str, User]
):
    """B-1 回归：准入在 ``create_and_schedule_tool_task`` 里，领域入口同样被拦。

    领域服务（结构预测/准备/口袋预测）、workflow 节点、k8s smoke、direct recovery
    全部走同一个建任务函数，**没有一条经过 ``POST /api/v1/tasks``**。准入挂在那条
    路由上时，这些入口可以完全绕开配额——一条 workflow 链路就能无限刷算力，
    G-9 的核心就此失效。这条用例故意不走 HTTP，直接调领域服务。
    """
    project = await _create_project(db_session, owner=users["owner"])
    _target, protein = await _create_target_and_protein(
        db_session, project=project, owner=users["owner"]
    )
    tool = await _create_tool(
        db_session, owner=users["owner"], gpu_required=True, slug="boltz-2"
    )
    assert tool.slug == "boltz-2"  # 领域层按 slug 找工具
    quota = await get_or_create_project_quota(db_session, project_id=project.id)
    await update_project_quota(
        db_session, quota=quota, updated_by=None, max_concurrent_dcu=1
    )
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.RUNNING.value, gpu_index=0,
    )

    before = (
        await db_session.execute(select(func.count()).select_from(Task))
    ).scalar_one()

    with pytest.raises(QuotaExceededException) as excinfo:
        await submit_structure_prediction(
            db_session,
            protein=protein,
            user=users["owner"],
            data=StructurePredict(),
        )
    assert excinfo.value.code == 429
    assert excinfo.value.detail["dimension"] == "maxConcurrentDcu"

    after = (
        await db_session.execute(select(func.count()).select_from(Task))
    ).scalar_one()
    # 抛在建任务之前：领域入口被拦时也不留 PENDING 空壳。
    assert after == before


@pytest.mark.asyncio
async def test_task_attached_to_migration_project_is_blocked_by_quota(
    db_session: AsyncSession, users: dict[str, User]
):
    """B-2 回归：没传 ``project_id`` 也要按**最终落点**判定。

    没有显式项目的 k8s_job / 标准产物任务会被 ``_prepare_tool_task_run`` 自动挂到
    用户的迁移项目（``ensure_migration_project_for_owner``）。若拿
    ``task_data.project_id`` 判空后 return，这类任务会带着迁移项目的 project_id
    入库、被 ``project_usage_*`` / ``project_active_counts`` 计入——配额白设。
    """
    project = await _create_project(db_session, owner=users["owner"])
    migration = await ensure_migration_project_for_owner(db_session, users["owner"])
    assert str(migration.id) != str(project.id)
    quota = await get_or_create_project_quota(db_session, project_id=migration.id)
    await update_project_quota(
        db_session, quota=quota, updated_by=None, max_concurrent_dcu=1
    )

    k8s_tool = await _create_tool(
        db_session, owner=users["owner"], gpu_required=True, config={"type": "k8s_job"}
    )
    await _create_task(
        db_session, user=users["owner"], tool=k8s_tool, project_id=migration.id,
        status=TaskStatus.RUNNING.value, gpu_index=0,
    )

    with pytest.raises(QuotaExceededException) as excinfo:
        await create_and_schedule_tool_task(
            db=db_session,
            current_user=users["owner"],
            task_data=TaskCreate(name="no project", tool_id=k8s_tool.id, params={}),
        )
    # 报错里的项目是迁移项目，不是「没指定项目所以放过」。
    assert excinfo.value.detail["dimension"] == "maxConcurrentDcu"


@pytest.mark.asyncio
async def test_task_without_any_project_stays_unrestricted(
    db_session: AsyncSession,
    users: dict[str, User],
    direct_runner_stub: SimpleNamespace,
):
    """既无显式项目、也不落迁移项目的任务：不适用配额（写在这里是为了说明）。

    这是 ``_enforce_project_quota`` 里 ``project_id`` 为空的**唯一**合法分支：
    普通 CPU 脚本工具、不带标准上传/产物，``prepare_run`` 拿到的是
    ``project_id=None``，任务也就不会写 ``extra_data["project_id"]``——它不会
    被任何项目的用量统计或占用计数捞到，因此也不该被任何项目的配额拦住。

    **必须把 ``direct_runner`` 显式传成 stub**：这是本文件里唯一一个真的走到
    ``dispatch_tool_task`` 却不被配额拦下的用例（另两个调
    ``create_and_schedule_tool_task`` 的用例都停在 ``QuotaExceededException``，
    到不了分发）。不传的话会落到 ``service.py`` 里绑定在函数定义上的
    ``default_direct_task_runner``，它用 ``asyncio.create_task`` 起一个真任务；
    测试函数返回后那个 task 仍挂在事件循环上，pytest 跑完 41 个用例也不退出，
    被 ``timeout`` 杀掉时退出码是 124（现象是「41 passed 然后卡住」）。

    注意不能靠 ``direct_runner_stub`` fixture：它 monkeypatch 的是
    ``tasks_api.direct_task_runner``，只影响 HTTP 路由，对直接调用 service 的
    用例无效——默认参数在函数定义时就已绑定。
    """
    project = await _create_project(db_session, owner=users["owner"])
    quota = await get_or_create_project_quota(db_session, project_id=project.id)
    await update_project_quota(
        db_session, quota=quota, updated_by=None, max_concurrent_cpu_tasks=1
    )
    tool = await _create_tool(db_session, owner=users["owner"])

    # 迁移项目里塞满 CPU 任务也没用：本次任务不挂任何项目。
    await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.RUNNING.value, gpu_index=None,
    )

    task = await create_and_schedule_tool_task(
        db=db_session,
        current_user=users["owner"],
        task_data=TaskCreate(name="no project", tool_id=tool.id, params={}),
        direct_runner=direct_runner_stub,
    )
    assert task is not None
    assert (task.extra_data or {}).get("project_id") is None
    # 任务确实被分发（不是被配额拦住），但分发交给 stub，没有起真后台任务。
    assert direct_runner_stub.scheduled == [(str(task.id), str(tool.current_version_id))]


@pytest.mark.asyncio
async def test_allocator_stamps_allocated_dcu_count_once(
    db_session: AsyncSession, users: dict[str, User]
):
    """A-2 写侧：分配器落 ``allocatedDcuCount``，重复分配取最大值不累加。

    写在分配器（而不是 executor）是因为它是所有 DCU 获取路径的汇聚点，
    而「取最大值」是因为重试不会让一条任务同时占两张卡——重复分配是同一个
    物理事实的重复上报。
    """
    project = await _create_project(db_session, owner=users["owner"])
    tool = await _create_tool(db_session, owner=users["owner"], gpu_required=True)
    task = await _create_task(
        db_session, user=users["owner"], tool=tool, project_id=project.id,
        status=TaskStatus.RUNNING.value, gpu_index=None,
    )

    allocator = GPUAllocator(db=db_session)
    await allocator._stamp_allocated_dcu_count(task.id, gpu_index=0)
    await db_session.commit()

    await db_session.refresh(task)
    assert task.extra_data["allocatedDcuCount"] == 1
    # 分配器写入不能踩掉已有的 extra_data（project_id 就在里面）。
    assert task.extra_data["project_id"] == str(project.id)

    # 再次分配（重试）：仍为 1，不是 2。
    await allocator._stamp_allocated_dcu_count(task.id, gpu_index=1)
    await db_session.commit()
    await db_session.refresh(task)
    assert task.extra_data["allocatedDcuCount"] == 1

    # 释放后 ``gpu_index`` 清空，但标记还在 → 核销仍按 DCU 记。
    from sqlalchemy import update

    await db_session.execute(
        update(Task).where(Task.id == task.id).values(gpu_index=None)
    )
    await db_session.commit()
    await db_session.refresh(task)
    assert task.gpu_index is None
    assert cost_from_task(task).dcu_minutes >= 0.0
    assert task.extra_data["allocatedDcuCount"] == 1

