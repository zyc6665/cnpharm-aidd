"""项目配额：计量口径、准入检查、核销与序列化（docs/04 §5.3、docs/03 §5.6）。

三个必须解释清楚的设计点
------------------------

**为什么是「算力分钟」而不是任务个数。**
按任务个数计量时，一个 10 万条的批量筛选与一个单分子对接等价，配额形同虚设。
算力分钟按 ``实际时长 × 实际卡数/核数`` 折算，折算系数见 ``DCU_MINUTE_WEIGHT`` 与
``CPU_CORE_MINUTE_WEIGHT``。

**为什么 CPU 是 1/64 而不是 1/128。**
甲方已确认计算节点为 128 核（``D-03-11``），但系数**不变**：它表达的是
「一张 DCU 与一个 CPU 核的单位算力**价值**比」，不是物理核数。改成 1/128 会让
全部历史核销记录与告警阈值失真（docs/03:642 明确禁止）。

**为什么是软上限。**
超额**不回杀**已在跑的任务——一个跑了 6 小时的 MD 任务因为配额到点被 kill，
代价远高于多花的那点算力，而且用户完全无法预期。超额只做两件事：

1. **阻塞新提交**（``check_submission_allowed``）；
2. **打一条 WARNING 日志**（跨过 100% 时，在 ``check_submission_allowed`` 里）。

第 2 条是 docs/04:261「超额后告警」目前唯一落地的形态：只到日志，**没有**站内信 /
邮件 / 指标通道（那需要新建推送设施，超出本 PR 范围）。用户侧可见的信号是提交被拒时
``429`` 响应体里的 ``detail``（含 ``dimension`` / ``limit`` / 已用量），以及
``GET /projects/{id}/quota`` 的 ``exceeded``。

``overdraft_ratio`` **不是告警阈值，它只放宽拒绝线**。``1.00`` = 一用完就拒，
``1.20`` = 可以用到 120% 才拒。告警线固定在 100%（``limit_minutes`` 本身），
拒绝线是 ``limit × ratio``，两者故意不同：``1.20`` 时 100%~120% 这段会告警、会放行，
用户从此有信号，而不是「无感地被允许继续用、然后突然被拒」。

核销口径
--------
任务进入终态（``SUCCESS`` / ``FAILURE`` / ``TIMEOUT`` / ``CANCELED``）时按
``duration × 实际卡数/核数`` **一次性**核销；失败与取消同样核销——否则可以反复
失败来白嫖算力。``PENDING`` / ``QUEUED`` / ``RUNNING`` 不核销。

核销结果写在 ``task.extra_data["cost"]``（JSON 列，不新表不加列），所以：

* 幂等：同一执行轮次重复调用直接返回已落账值，重试/重复提交不会双计；
* 可回溯：``settledAt`` 记录核销时刻，出问题能回答「这条成本是什么时候落的账」；
* 不丢账：任务被重试后再跑一次时 ``retry_count`` 变了，新一轮的成本**累加**进
  ``history``，而不是被「已经核销过」挡住。若只做「有 cost 就跳过」，一个失败三次
  才成功的任务只会记到第一次的算力——那正好是白嫖算力的另一条路。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.common.exceptions import QuotaExceededException, ValidationException
from app.common.time import isoformat_utc, utcnow
from app.models.projects import ProjectMember
from app.models.quotas import (
    DEFAULT_DAILY_QUOTA_MINUTES,
    DEFAULT_MAX_CONCURRENT_CPU_TASKS,
    DEFAULT_MAX_CONCURRENT_DCU,
    DEFAULT_MAX_SINGLE_TASK_MINUTES,
    DEFAULT_OVERDRAFT_RATIO,
    DEFAULT_QUOTA_PERIOD,
    QUOTA_PERIOD_DAILY,
    QUOTA_PERIOD_MONTHLY,
    QUOTA_PERIODS,
    ProjectQuota,
)
from app.models.tasks import Task, TaskStatus

logger = logging.getLogger(__name__)

#: 1 张 DCU·分钟 = 1.0（基准）。见模块 docstring 的「为什么 CPU 是 1/64」。
DCU_MINUTE_WEIGHT = 1.0
#: 1 个 CPU 核·分钟 = 1/64。**不要**因为节点 128 核就改成 1/128。
CPU_CORE_MINUTE_WEIGHT = 1.0 / 64
#: 内存不计费：无法公平折算，而且它不是瓶颈。
MEMORY_GB_MINUTE_WEIGHT = 0.0

#: 算力分钟核销结果在 ``task.extra_data`` 里的键。
COST_METADATA_KEY = "cost"
#: 分配时落下的不可变 DCU 卡数（见 ``allocated_dcu_count``）。只写一次、永不清空。
ALLOCATED_DCU_COUNT_KEY = "allocatedDcuCount"

#: 计入用量的终态（``REJECTED`` 尚未落库，自然也不在此列）。
SETTLED_STATUSES = (
    TaskStatus.SUCCESS.value,
    TaskStatus.FAILURE.value,
    TaskStatus.TIMEOUT.value,
    TaskStatus.CANCELED.value,
)


@dataclass(frozen=True)
class CostBreakdown:
    """一次任务执行的算力成本（单位：算力分钟）。"""

    dcu_minutes: float
    cpu_minutes: float
    total_minutes: float

    def as_dict(self) -> dict[str, float]:
        """转成 ``task.extra_data["cost"]`` 的载荷（保留 4 位小数）。"""
        return {
            "dcuMinutes": round(self.dcu_minutes, 4),
            "cpuMinutes": round(self.cpu_minutes, 4),
            "totalMinutes": round(self.total_minutes, 4),
        }


def compute_cost(
    *,
    duration_seconds: float,
    dcu_count: int = 0,
    cpu_cores: float = 0.0,
) -> CostBreakdown:
    """按「实际时长 × 实际卡数/核数」折算算力分钟。

    负数一律按 0 处理：时长为负（时钟回拨、``finished_at < started_at``）或卡数为负
    都是脏数据，把它当成负数会让用量倒退，比丢弃更糟。
    """
    minutes = max(float(duration_seconds or 0.0), 0.0) / 60.0
    dcu_minutes = minutes * max(int(dcu_count or 0), 0) * DCU_MINUTE_WEIGHT
    cpu_minutes = minutes * max(float(cpu_cores or 0.0), 0.0) * CPU_CORE_MINUTE_WEIGHT
    return CostBreakdown(
        dcu_minutes=dcu_minutes,
        cpu_minutes=cpu_minutes,
        total_minutes=dcu_minutes + cpu_minutes,
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _duration_seconds(source: Any) -> float:
    """执行时长：优先 ``execution_time_sec``，缺失时用起止时间兜底。

    参数既可以是 ``Task`` 实例，也可以是 ``select(Task.id, ...)`` 出来的 ``Row``
    ——两者都支持属性访问，所以口径函数只写一份，避免「ORM 口径改了、汇总口径
    没改」导致页面数字与准入判断对不上。

    两者都没有（如还停在 ``QUEUED`` 就失败的任务）退化成 0——**不抛异常**：
    核销是收尾动作，不能因为一条脏数据让整个终态提交失败。
    """
    explicit = getattr(source, "execution_time_sec", None)
    if isinstance(explicit, (int, float)):
        return float(explicit)
    started_at = getattr(source, "started_at", None)
    finished_at = getattr(source, "finished_at", None)
    if isinstance(started_at, datetime) and isinstance(finished_at, datetime):
        return (finished_at - started_at).total_seconds()
    return 0.0


def _resource_request(extra_data: Any) -> dict[str, Any]:
    snapshot = _as_dict(_as_dict(extra_data).get("resource_snapshot"))
    return _as_dict(snapshot.get("resource_request"))


def allocated_dcu_count(extra_data: Any) -> int:
    """分配时落下的**不可变** DCU 卡数；``0`` 表示这条任务从未占用过 DCU。

    为什么需要它（而不是直接看 ``gpu_index``）：``gpu_index`` 是**当前占用**，
    任务一释放就被清空（``app/gpu/allocator.py`` 的三处
    ``values(gpu_index=None)``、``app/tasks/executors/factory.py`` 的
    ``self.task.gpu_index = None``）。而核销发生在**终态之后**（状态机或
    ``settle_finished_tasks`` 事后读库），那时 ``gpu_index`` 必然是 ``NULL``。
    若再叠加「工具的 ``gpu_required=False``、但 resource_profile 里配了 GPU」这种
    组合（此时 ``resource_request.gpu_count`` 也是 0），一个真跑了 6 小时 DCU 的
    任务会被当成 CPU 任务核销：权重从 1.0 掉到 1/64，**少扣一个数量级**。
    """
    explicit = _as_dict(extra_data).get(ALLOCATED_DCU_COUNT_KEY)
    if isinstance(explicit, (int, float)):
        return max(int(explicit), 0)
    return 0


def _dcu_count(source: Any) -> int:
    """DCU 占用卡数（核销口径）。约定「1 任务 1 卡」，判定优先级见下。

    1. ``extra_data["allocatedDcuCount"]``——分配时写下的不可变事实，最可信；
    2. ``resource_request.gpu_count``——资源画像声明的卡数（下发前就存在）；
    3. ``gpu_index is not None``——只在任务还占着卡时成立，事后读库必然为假。

    第 3 条保留是为了兼容本改动之前落库的历史任务：它们没有
    ``allocatedDcuCount``，而有 ``gpu_count=0`` + ``gpu_index`` 的只可能来自
    「工具没声明 GPU、但运行时真占了卡」这条老路径。
    """
    extra_data = getattr(source, "extra_data", None)
    allocated = allocated_dcu_count(extra_data)
    if allocated > 0:
        return allocated
    gpu_count = _resource_request(extra_data).get("gpu_count")
    if isinstance(gpu_count, (int, float)) and int(gpu_count) > 0:
        return int(gpu_count)
    return 1 if getattr(source, "gpu_index", None) is not None else 0


def _cpu_cores(source: Any) -> float:
    """CPU 核数：从资源快照的 ``resource_request.cpu`` 取，取不到按 0。"""
    cpu = _resource_request(getattr(source, "extra_data", None)).get("cpu")
    if isinstance(cpu, (int, float)) and float(cpu) > 0:
        return float(cpu)
    return 0.0


def cost_from_task(task: Task) -> CostBreakdown:
    """从任务记录推算成本。任何字段缺失都退化成 0，不抛异常。"""
    return compute_cost(
        duration_seconds=_duration_seconds(task),
        dcu_count=_dcu_count(task),
        cpu_cores=_cpu_cores(task),
    )


# ---------------------------------------------------------------------------
# 配额读写
# ---------------------------------------------------------------------------


async def load_project_quota(db: AsyncSession, *, project_id: str) -> ProjectQuota | None:
    """读项目配额；``None`` 表示这个项目还没配过（= 不限，不是「零配额」）。"""
    result = await db.execute(
        select(ProjectQuota).where(ProjectQuota.project_id == str(project_id))
    )
    return result.scalar_one_or_none()


async def get_or_create_project_quota(
    db: AsyncSession,
    *,
    project_id: str,
    created_by: str | None = None,
) -> ProjectQuota:
    """读配额，没有就按默认值建一条并提交。

    **只给 ``PUT`` 用**（写配置时才真正落库）。``GET`` 走 ``load_project_quota`` +
    ``serialize_default_quota``，不建记录——原因见 ``serialize_default_quota``：
    查询动作一旦产生写入，就会让「有没有人点开过配额页」改变这个项目能不能提交
    任务（``check_submission_allowed`` 里「无记录 = 不限」）。那才是真正的半状态：
    库里有了一条没人显式配过的记录，且它立刻生效。

    这里**自己 commit**：建配额是配置动作不是业务写，调用方（PUT 端点）后续还要
    走 ``update_project_quota`` 写字段，把建行与写字段分两次提交没有意义，但让
    建行先落地可以保证唯一索引冲突时的行为可预期（并发 PUT 由唯一索引兜底）。
    """
    quota = await load_project_quota(db, project_id=project_id)
    if quota is not None:
        return quota
    quota = ProjectQuota(
        project_id=str(project_id),
        max_concurrent_dcu=DEFAULT_MAX_CONCURRENT_DCU,
        max_concurrent_cpu_tasks=DEFAULT_MAX_CONCURRENT_CPU_TASKS,
        daily_quota_minutes=DEFAULT_DAILY_QUOTA_MINUTES,
        max_single_task_minutes=DEFAULT_MAX_SINGLE_TASK_MINUTES,
        quota_period=DEFAULT_QUOTA_PERIOD,
        overdraft_ratio=DEFAULT_OVERDRAFT_RATIO,
        updated_by=created_by,
    )
    db.add(quota)
    await db.commit()
    await db.refresh(quota)
    return quota


def _validate_overdraft_ratio(value: Any) -> Decimal:
    try:
        ratio = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationException("overdraft_ratio 必须是数字") from exc
    # 小于 1 的阈值意味着「没用完就告警」，与 `overdraft`（超额）的语义相反，
    # 且会让准入检查在配额远未用完时就开始拒绝，属于配置错误而非业务选择。
    if ratio < Decimal("1.0"):
        raise ValidationException("overdraft_ratio 不能小于 1.00（1.00 = 用完即拒绝新提交）")
    if ratio > Decimal("99.99"):
        raise ValidationException("overdraft_ratio 超出 numeric(4,2) 可表示范围")
    return ratio


def _validate_non_negative(name: str, value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationException(f"{name} 必须是整数") from exc
    if number < 0:
        raise ValidationException(f"{name} 不能为负数（0 = 不限）")
    return number


def validate_quota_changes(**fields: Any) -> dict[str, Any]:
    """校验并规范化配额变更字段（纯函数，不碰数据库）。

    单独暴露它，是为了让调用方能在 ``get_or_create_project_quota`` **之前**先校验：
    否则一次被拒的 ``PUT`` 会顺手留下一条默认配额记录——请求失败却改了状态，
    是最难排查的那类副作用（而且这条默认记录立刻就让并发上限生效了）。
    """
    pending: dict[str, Any] = {}

    if fields.get("quota_period") is not None:
        period = str(fields["quota_period"]).upper()
        if period not in QUOTA_PERIODS:
            raise ValidationException(
                f"quota_period 必须是 {'/'.join(QUOTA_PERIODS)} 之一"
            )
        pending["quota_period"] = period

    if fields.get("overdraft_ratio") is not None:
        pending["overdraft_ratio"] = _validate_overdraft_ratio(fields["overdraft_ratio"])

    for name in (
        "max_concurrent_dcu",
        "max_concurrent_cpu_tasks",
        "daily_quota_minutes",
        "max_single_task_minutes",
    ):
        if fields.get(name) is not None:
            pending[name] = _validate_non_negative(name, fields[name])

    if not pending:
        raise ValidationException("至少需要修改一项配额字段")

    return pending


async def update_project_quota(
    db: AsyncSession,
    *,
    quota: ProjectQuota,
    updated_by: str | None,
    **fields: Any,
) -> ProjectQuota:
    """部分更新配额：只认传入的非 ``None`` 字段，非法值抛 ``ValidationException``。

    校验放在写入前一次性做完（而不是边写边校验），避免「前三个字段已经改了、
    第四个字段校验失败」的半更新——虽然本函数不 commit，但对象已被污染，
    调用方再 commit 就落库了。
    """
    pending = validate_quota_changes(**fields)

    for name, value in pending.items():
        setattr(quota, name, value)
    quota.updated_by = updated_by
    await db.commit()
    await db.refresh(quota)
    return quota


# ---------------------------------------------------------------------------
# 用量统计
# ---------------------------------------------------------------------------


def period_window(
    period: str,
    *,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime]:
    """返回配额窗口 ``[start, now]``；``start is None`` 表示不限周期。"""
    moment = now or utcnow()
    normalized = str(period or DEFAULT_QUOTA_PERIOD).upper()
    if normalized == QUOTA_PERIOD_DAILY:
        return moment.replace(hour=0, minute=0, second=0, microsecond=0), moment
    if normalized == QUOTA_PERIOD_MONTHLY:
        return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0), moment
    return None, moment


def _cost_total_from_extra_data(extra_data: Any) -> float | None:
    """读取已核销的成本；返回 ``None`` 表示这条任务还没核销。"""
    cost = _as_dict(_as_dict(extra_data).get(COST_METADATA_KEY))
    total = cost.get("totalMinutes")
    if isinstance(total, (int, float)):
        return float(total)
    return None


def _cost_split_from_extra_data(extra_data: Any) -> tuple[float, float] | None:
    cost = _as_dict(_as_dict(extra_data).get(COST_METADATA_KEY))
    dcu = cost.get("dcuMinutes")
    cpu = cost.get("cpuMinutes")
    if isinstance(dcu, (int, float)) and isinstance(cpu, (int, float)):
        return float(dcu), float(cpu)
    return None


async def _window_rows(
    db: AsyncSession,
    *,
    project_ids: list[str],
    period: str,
    now: datetime | None = None,
):
    """取窗口内指定项目的终态任务行（只读需要的列）。"""
    start, end = period_window(period, now=now)
    conditions = [
        Task.project_id_expression().in_([str(pid) for pid in project_ids]),
        Task.status.in_(SETTLED_STATUSES),
    ]
    if start is not None:
        # 用 finished_at 而不是 created_at：跨周期边界的长任务应该算在**结束**的那个
        # 周期里（它的算力是在那个周期消费掉的）。finished_at 为空的终态行是脏数据，
        # 统一按 0 处理而不是丢掉整条（否则少计量）。
        conditions.append(Task.finished_at.is_not(None))
        conditions.append(Task.finished_at >= start)
        conditions.append(Task.finished_at <= end)

    return (
        await db.execute(
            select(
                Task.id,
                Task.extra_data,
                Task.execution_time_sec,
                Task.started_at,
                Task.finished_at,
                Task.gpu_index,
            ).where(*conditions)
        )
    ).all()


def _row_cost(row) -> CostBreakdown:
    """一行的成本：已核销直接读，未核销（升级前的存量）现算兜底。

    已核销的不再重算：核销是历史事实，事后改了资源快照也不该让已落账的成本变动。
    """
    settled = _cost_total_from_extra_data(row.extra_data)
    if settled is not None:
        split = _cost_split_from_extra_data(row.extra_data) or (settled, 0.0)
        return CostBreakdown(
            dcu_minutes=split[0], cpu_minutes=split[1], total_minutes=settled
        )
    # 口径函数与 ORM 路径共用同一份实现（``Row`` 与 ``Task`` 都支持属性访问）：
    # 汇总口径与核销口径一旦分叉，页面上的用量与准入判断就会对不上。
    return compute_cost(
        duration_seconds=_duration_seconds(row),
        dcu_count=_dcu_count(row),
        cpu_cores=_cpu_cores(row),
    )


async def project_usage_breakdown(
    db: AsyncSession,
    *,
    project_id: str,
    period: str,
    now: datetime | None = None,
) -> dict[str, float]:
    """窗口内单个项目的用量拆分（DCU / CPU / 合计，单位算力分钟）。

    没有新加汇总表/列：配额是低频读取（每次提交一次 + 页面打开一次），
    而算力分钟的量级下，扫一个项目的终态任务远不到需要预聚合的程度；
    预聚合反而要处理「任务重跑/回滚」的一致性，得不偿失。
    """
    rows = await _window_rows(db, project_ids=[project_id], period=period, now=now)
    dcu = 0.0
    cpu = 0.0
    total = 0.0
    for row in rows:
        cost = _row_cost(row)
        dcu += cost.dcu_minutes
        cpu += cost.cpu_minutes
        total += cost.total_minutes
    return {
        "dcuMinutes": round(dcu, 4),
        "cpuMinutes": round(cpu, 4),
        "totalMinutes": round(total, 4),
    }


async def project_usage_minutes(
    db: AsyncSession,
    *,
    project_id: str,
    period: str,
    now: datetime | None = None,
) -> float:
    """汇总窗口内该项目所有终态任务的算力分钟（= ``project_usage_breakdown`` 的合计）。"""
    breakdown = await project_usage_breakdown(
        db, project_id=project_id, period=period, now=now
    )
    return breakdown["totalMinutes"]


async def project_active_counts(db: AsyncSession, *, project_id: str) -> dict[str, int]:
    """当前占用：DCU 看 RUNNING 有卡任务，CPU 看 RUNNING/QUEUED 无卡任务。

    CPU 侧把 ``QUEUED`` 也算占用：名额是在**提交**时抢的，排队中的任务已经占住了
    队列位置，若不算，用户可以无限往队列里塞任务绕过并发上限。
    """
    result = await db.execute(
        select(Task.status, Task.gpu_index).where(
            Task.project_id_expression() == str(project_id),
            Task.status.in_(
                (TaskStatus.RUNNING.value, TaskStatus.QUEUED.value)
            ),
        )
    )
    dcu = 0
    cpu = 0
    for status, gpu_index in result.all():
        has_dcu = gpu_index is not None
        if has_dcu and status == TaskStatus.RUNNING.value:
            dcu += 1
        elif not has_dcu and status in (
            TaskStatus.RUNNING.value,
            TaskStatus.QUEUED.value,
        ):
            cpu += 1
    return {"dcu": dcu, "cpu": cpu}


# ---------------------------------------------------------------------------
# 准入检查
# ---------------------------------------------------------------------------


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def check_submission_allowed(
    db: AsyncSession,
    *,
    project_id: str,
    requires_dcu: bool,
    timeout_sec: float | None = None,
) -> None:
    """准入检查：超额只阻塞**新提交**，已入队的任务不受影响。

    **没有配额记录 = 不限**（``if quota is None: return``）：配额是管理员显式分配的，
    「没配」与「配了 0」语义完全不同，后者才是零额度。若把「没配」当零额度，
    升级那一刻所有历史项目都会提交不了任务。

    ``timeout_sec`` 传本次提交的资源快照里声明的墙钟超时（
    ``resource_snapshot.timeout_sec``），用于校验 ``max_single_task_minutes``。
    不传或传 ``None`` 表示「调用方没有快照可用」，此时跳过这项校验——**不是**
    当作无限时长。
    """
    quota = await load_project_quota(db, project_id=project_id)
    if quota is None:
        return

    # 单任务时长上限：这是**唯一**执行 ``max_single_task_minutes`` 的地方。
    # 早期版本只把它存进库、在 GET 里返回，用户以为生效而实际没有任何校验——
    # 「看起来生效但其实没有」比不提供这个字段更糟。
    max_single_minutes = int(quota.max_single_task_minutes or 0)
    if max_single_minutes > 0 and timeout_sec is not None:
        requested_sec = _as_float(timeout_sec, 0.0)
        if requested_sec > max_single_minutes * 60:
            raise QuotaExceededException(
                f"单任务时长超过项目上限 {max_single_minutes} 分钟"
                f"（本次声明 {requested_sec / 60:.0f} 分钟）",
                detail={
                    "dimension": "maxSingleTaskMinutes",
                    "limitMinutes": max_single_minutes,
                    "requestedMinutes": round(requested_sec / 60.0, 4),
                    # 声明里被拒的是「这次请求的时长参数」，不是「已跑超时被 kill」：
                    # 后者需要 executor 侧的执行，本期不做。
                    "enforced": "admission",
                },
            )

    active = await project_active_counts(db, project_id=project_id)
    if requires_dcu:
        limit = int(quota.max_concurrent_dcu or 0)
        if limit > 0 and active["dcu"] >= limit:
            raise QuotaExceededException(
                f"项目并发 DCU 任务已达上限 {limit}（当前 {active['dcu']} 个在跑）",
                detail={
                    "dimension": "maxConcurrentDcu",
                    "limit": limit,
                    "active": active["dcu"],
                },
            )
    else:
        limit = int(quota.max_concurrent_cpu_tasks or 0)
        if limit > 0 and active["cpu"] >= limit:
            raise QuotaExceededException(
                f"项目并发 CPU 任务已达上限 {limit}（当前 {active['cpu']} 个在跑或排队）",
                detail={
                    "dimension": "maxConcurrentCpuTasks",
                    "limit": limit,
                    "active": active["cpu"],
                },
            )

    limit_minutes = int(quota.daily_quota_minutes or 0)
    if limit_minutes <= 0:
        return
    used = await project_usage_minutes(
        db, project_id=project_id, period=quota.quota_period
    )
    # 告警：跨过 **100%（`limit_minutes`）** 就打一条 WARNING，不管本次提交最终是否
    # 被拒。这是 docs/04:261「超额后告警」目前唯一落地的形态——只到日志，没有站内信/
    # 邮件/指标通道（那需要新建推送设施，超出本 PR）。注意告警线是 `limit` 本身，
    # 而拒绝线是 `limit × overdraft_ratio`，两者故意不同：`1.20` 表示「120% 才拒」，
    # 但 100%~120% 这段会告警、会放行，用户从此有信号。
    # 不去重/不限流：这里没有可持久化的告警状态，准入本身就是低频操作，
    # 多打几条也远好过「超额了完全没人知道」。
    if used >= limit_minutes:
        logger.warning(
            "项目 %s 算力分钟配额已超额：已用 %.2f / 上限 %s 分钟（%s，"
            "拒绝线 %s × %s = %.2f）",
            project_id,
            used,
            limit_minutes,
            quota.quota_period,
            limit_minutes,
            _as_float(quota.overdraft_ratio, 1.0),
            limit_minutes * _as_float(quota.overdraft_ratio, 1.0),
        )
    # 阈值用 overdraft_ratio 放宽：1.20 表示允许用到 120% 才开始拦新提交，
    # 这样「配额用完」与「完全不能提交」之间有缓冲，不会卡死在整数边界上。
    threshold = limit_minutes * _as_float(quota.overdraft_ratio, 1.0)
    if used >= threshold:
        raise QuotaExceededException(
            f"项目算力分钟配额已用尽（已用 {used:.0f} / 上限 {limit_minutes:.0f} 分钟）",
            detail={
                "dimension": "dailyQuotaMinutes",
                "limitMinutes": limit_minutes,
                "usedMinutes": round(used, 4),
                "period": quota.quota_period,
                "overdraftRatio": _as_float(quota.overdraft_ratio, 1.0),
            },
        )


# ---------------------------------------------------------------------------
# 核销
# ---------------------------------------------------------------------------


def _task_attempt_index(task: Task) -> int:
    """执行轮次：``retry_count`` 每次重新排队/重试都会 +1，正好当轮次序号用。"""
    value = getattr(task, "retry_count", 0)
    return int(value) if isinstance(value, int) else 0


def settle_task_cost_in_memory(task: Task) -> CostBreakdown | None:
    """把成本写进 ``task.extra_data["cost"]``，返回成本；非终态返回 ``None``。

    纯内存操作（不碰 db），给「手里没有 session 但马上就要提交」的调用方用——
    ``TaskStateMachine.transition`` 就是这种场景（它是同步纯函数模块）。

    幂等键是 ``(task.id, retry_count)``：

    * 同一轮次重复调用 → 直接返回已落账值，不双计；
    * 换了一轮（``retry_count`` 变了）→ 新成本累加进 ``history``，
      ``totalMinutes`` 是各轮之和。这样「失败三次才成功」的任务不会只算第一次。
    """
    status = task.status.value if isinstance(task.status, TaskStatus) else task.status
    if status not in SETTLED_STATUSES:
        return None

    extra_data = dict(task.extra_data or {})
    existing = _as_dict(extra_data.get(COST_METADATA_KEY))
    attempt = _task_attempt_index(task)
    existing_total = existing.get("totalMinutes")

    if isinstance(existing_total, (int, float)):
        settled_attempt = existing.get("settledAttempt")
        # 老数据没有 settledAttempt：保守地视为「已核销过」，宁可少计一轮也不能双计。
        if settled_attempt is None or int(settled_attempt) == attempt:
            return CostBreakdown(
                dcu_minutes=float(existing.get("dcuMinutes") or 0.0),
                cpu_minutes=float(existing.get("cpuMinutes") or 0.0),
                total_minutes=float(existing_total),
            )

    cost = cost_from_task(task)
    history = list(existing.get("history") or [])
    if isinstance(existing_total, (int, float)):
        history.append(
            {
                "attempt": existing.get("settledAttempt"),
                "dcuMinutes": float(existing.get("dcuMinutes") or 0.0),
                "cpuMinutes": float(existing.get("cpuMinutes") or 0.0),
                "totalMinutes": float(existing_total),
                "settledAt": existing.get("settledAt"),
            }
        )
        cost = CostBreakdown(
            dcu_minutes=float(existing.get("dcuMinutes") or 0.0) + cost.dcu_minutes,
            cpu_minutes=float(existing.get("cpuMinutes") or 0.0) + cost.cpu_minutes,
            total_minutes=float(existing_total) + cost.total_minutes,
        )

    extra_data[COST_METADATA_KEY] = {
        **cost.as_dict(),
        "settledAt": isoformat_utc(utcnow()),
        "settledAttempt": attempt,
        "history": history,
    }
    task.extra_data = extra_data
    # JSON 列原地改不会被 SQLAlchemy 感知；上面虽已整体赋值（会标记脏），但
    # 调用方（状态机）常常紧接着走 `update(Task).values(extra_data=...)` 的原生
    # UPDATE，保险起见显式标脏，避免「状态提交了、cost 没落库」。
    #
    # 只在真的是 ORM 实例时标脏：状态机是鸭子类型调用方，仓库里已有拿
    # `SimpleNamespace` 之类替身跑 `transition()` 的测试（见
    # `test/test_worker_queue_lifecycle.py` 的取消路径）。`instance_state()` 遇到
    # 非映射对象会抛 `AttributeError`，那会让「取消一个任务」直接 500——核销失败
    # 绝不能反过来打断状态迁移。
    if hasattr(task, "_sa_instance_state"):
        flag_modified(task, "extra_data")
    return cost


async def settle_finished_tasks(
    db: AsyncSession,
    *,
    limit: int = 200,
) -> int:
    """扫「终态但没有 cost」的任务批量补核销，返回本轮条数（给后台巡检用）。

    为什么需要它：状态机只管**经过它**的转换。历史上已经落在终态、或由其他路径
    （远端结果补回、直接改库修数据）变成终态的任务不会走 ``transition``，
    它们的算力就永远不入账——用量永久偏低，配额形同虚设。

    候选集**在 SQL 里就排掉已核销的行**（``extra_data["cost"]["totalMinutes"]
    IS NULL``），不是在 Python 里 ``continue``。这一点很关键：早期版本只按
    ``finished_at`` 取前 ``batch`` 条再在循环里跳过，一旦最早的 ``batch`` 条
    全部核销完，每轮都会取回同一批、全部跳过、返回 0，**游标永不推进**；
    升级前的存量任务超过 ``batch`` 时，后面的漏核销就永久不入账。加了 SQL 条件后
    已核销的行不再占位，``order_by(finished_at)`` 每次取到的都是真正的待办。

    Python 侧仍逐个走 ``settle_task_cost_in_memory`` 复核（非终态 / 轮次已核销
    时它会返回 ``None`` 或已落账值），两处判据同源，避免「粗筛通过但核销跳过」
    的行空占本轮的 ``limit``。
    """
    if limit <= 0:
        return 0

    # 多取一些：同一任务的多轮重试共用一行，「SQL 说没有 cost」与「本轮该不该
    # 再核销一轮」由 ``settle_task_cost_in_memory`` 按 ``retry_count`` 判定。
    batch = max(int(limit) * 4, int(limit))
    result = await db.execute(
        select(Task)
        .where(
            Task.status.in_(SETTLED_STATUSES),
            Task.extra_data[COST_METADATA_KEY]["totalMinutes"].as_string().is_(None),
        )
        .order_by(Task.finished_at.asc())
        .limit(batch)
    )
    settled = 0
    for task in result.scalars().all():
        if settled >= limit:
            break
        if _cost_total_from_extra_data(task.extra_data) is not None:
            continue
        cost = settle_task_cost_in_memory(task)
        if cost is not None:
            settled += 1
            # 全模块唯一一条核销日志：出问题时（用量对不上、某人说「任务早就跑完
            # 了却没扣」）这是唯一能定位到具体任务的线索。
            logger.info(
                "补核销任务 %s 算力成本 %.4f 分钟（%s，第 %s 轮）",
                getattr(task, "id", None),
                cost.total_minutes,
                task.status,
                _task_attempt_index(task),
            )
    if settled:
        await db.commit()
    return settled


# ---------------------------------------------------------------------------
# 汇总（``GET /api/v1/compute/quota``）
# ---------------------------------------------------------------------------


async def readable_project_ids(db: AsyncSession, *, user_id: str) -> list[str]:
    """当前用户能读的项目（成员身份即读权限）。"""
    result = await db.execute(
        select(ProjectMember.project_id).where(ProjectMember.user_id == str(user_id))
    )
    return [str(pid) for pid in result.scalars().all()]


async def user_quota_summary(db: AsyncSession, *, user_id: str) -> dict[str, Any]:
    """跨项目的配额汇总（docs/05 §9 ``GET /api/v1/compute/quota``）。

    口径说明：

    * **只统计有配额记录的项目**。没配 = 不限，把它们的用量算进分母为 0 的汇总里
      会让 ``exceeded`` 失去意义，而单独列出又超出该端点的规格字段；
    * ``limitMinutes`` 是各项目上限之和，``overdraftRatio`` 取**最严格**的那个
      （最小值），因为「有一个项目随时会拦提交」比「平均下来还行」更该被看见；
    * 周期不同的项目无法直接相加。这里按各项目自己的周期统计用量（各自准确），
      并在响应里给出 ``period`` = ``MIXED`` 提示前端不要用单一周期解释这个数。
    """
    project_ids = await readable_project_ids(db, user_id=user_id)
    if not project_ids:
        return _empty_summary()

    quotas = (
        await db.execute(
            select(ProjectQuota).where(ProjectQuota.project_id.in_(project_ids))
        )
    ).scalars().all()
    if not quotas:
        return _empty_summary()

    periods = {str(quota.quota_period or DEFAULT_QUOTA_PERIOD).upper() for quota in quotas}
    dcu = 0.0
    cpu = 0.0
    total = 0.0
    for quota in quotas:
        breakdown = await project_usage_breakdown(
            db,
            project_id=str(quota.project_id),
            period=quota.quota_period,
        )
        dcu += breakdown["dcuMinutes"]
        cpu += breakdown["cpuMinutes"]
        total += breakdown["totalMinutes"]

    limit_minutes = sum(
        int(quota.daily_quota_minutes or 0)
        for quota in quotas
        if int(quota.daily_quota_minutes or 0) > 0
    )
    ratio = min(
        (_as_float(quota.overdraft_ratio, 1.0) for quota in quotas),
        default=1.0,
    )
    exceeded = limit_minutes > 0 and total >= limit_minutes * ratio
    return {
        "projectCount": len(quotas),
        "usedDcuMinutes": round(dcu, 4),
        "usedCpuMinutes": round(cpu, 4),
        "usedTotalMinutes": round(total, 4),
        "limitMinutes": limit_minutes,
        "remainingMinutes": (
            None if limit_minutes <= 0 else max(round(limit_minutes - total, 4), 0.0)
        ),
        "period": periods.pop() if len(periods) == 1 else "MIXED",
        "overdraftRatio": ratio,
        "exceeded": exceeded,
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "projectCount": 0,
        "usedDcuMinutes": 0.0,
        "usedCpuMinutes": 0.0,
        "usedTotalMinutes": 0.0,
        "limitMinutes": 0,
        "remainingMinutes": None,
        "period": DEFAULT_QUOTA_PERIOD,
        "overdraftRatio": 1.0,
        "exceeded": False,
    }


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _build_quota_payload(
    *,
    project_id: str,
    max_concurrent_dcu: int,
    max_concurrent_cpu_tasks: int,
    daily_quota_minutes: int,
    max_single_task_minutes: int,
    quota_period: str,
    overdraft_ratio: Decimal | float,
    updated_at: datetime | None,
    updated_by: str | None,
    configured: bool,
    usage: float,
    active: dict[str, int],
) -> dict[str, Any]:
    """把「一组配额取值」拼成 docs/05 §3 的 camelCase 响应体。

    字段映射只此一处：``serialize_quota``（已落库）与 ``serialize_default_quota``
    （未落库的默认值）共用它，避免两条路径的字段名/换算逻辑漂移。
    """
    limit_minutes = int(daily_quota_minutes or 0)
    ratio = _as_float(overdraft_ratio, 1.0)
    exceeded = limit_minutes > 0 and usage >= limit_minutes * ratio
    remaining = None if limit_minutes <= 0 else max(round(limit_minutes - usage, 4), 0.0)
    return {
        "projectId": str(project_id),
        "maxConcurrentDcu": int(max_concurrent_dcu or 0),
        "maxConcurrentCpuTasks": int(max_concurrent_cpu_tasks or 0),
        "dailyQuotaMinutes": limit_minutes,
        "maxSingleTaskMinutes": int(max_single_task_minutes or 0),
        "quotaPeriod": quota_period,
        "overdraftRatio": ratio,
        "usedMinutes": round(usage, 4),
        "remainingMinutes": remaining,
        "activeDcuTasks": int(active.get("dcu", 0)),
        "activeCpuTasks": int(active.get("cpu", 0)),
        "exceeded": exceeded,
        "configured": configured,
        "updatedAt": isoformat_utc(updated_at),
        "updatedBy": updated_by,
    }


def serialize_quota(
    quota: ProjectQuota,
    *,
    usage: float,
    active: dict[str, int],
) -> dict[str, Any]:
    """序列化**已落库**的配额（``configured = True``）。

    ``remainingMinutes`` 在不限额（``daily_quota_minutes == 0``）时为 ``None``——
    返回 0 会被前端显示成「额度已用尽」，与「不限」正好相反。
    ``exceeded`` 用 ``overdraft_ratio`` 作阈值，与 ``check_submission_allowed``
    的拦截条件保持同一判据，避免「页面说没超、提交却被拒」。
    """
    return _build_quota_payload(
        project_id=str(quota.project_id),
        max_concurrent_dcu=quota.max_concurrent_dcu,
        max_concurrent_cpu_tasks=quota.max_concurrent_cpu_tasks,
        daily_quota_minutes=quota.daily_quota_minutes,
        max_single_task_minutes=quota.max_single_task_minutes,
        quota_period=quota.quota_period,
        overdraft_ratio=quota.overdraft_ratio,
        updated_at=quota.updated_at,
        updated_by=quota.updated_by,
        configured=True,
        usage=usage,
        active=active,
    )


def serialize_default_quota(
    *,
    project_id: str,
    usage: float,
    active: dict[str, int],
) -> dict[str, Any]:
    """序列化**未落库**的默认配额（``configured = False``）。

    给「这个项目还没配过」用：字段与已配置的响应体完全一致（前端一套渲染），
    但 ``configured=False`` + ``updatedAt=None`` 明确告诉前端「这不是管理员配的」。
    这里**绝不建记录**——见 ``load_project_quota`` 的说明：一旦 GET 顺手落一条
    ``max_concurrent_dcu=2`` 的记录，只要有人点开过配额页，这个项目就会从
    「不限」变成「并发 2 张 DCU」，而提交被拦的人无从知道是谁、什么时候改的。
    """
    return _build_quota_payload(
        project_id=str(project_id),
        max_concurrent_dcu=DEFAULT_MAX_CONCURRENT_DCU,
        max_concurrent_cpu_tasks=DEFAULT_MAX_CONCURRENT_CPU_TASKS,
        daily_quota_minutes=DEFAULT_DAILY_QUOTA_MINUTES,
        max_single_task_minutes=DEFAULT_MAX_SINGLE_TASK_MINUTES,
        quota_period=DEFAULT_QUOTA_PERIOD,
        overdraft_ratio=DEFAULT_OVERDRAFT_RATIO,
        updated_at=None,
        updated_by=None,
        configured=False,
        usage=usage,
        active=active,
    )


__all__ = [
    "COST_METADATA_KEY",
    "CPU_CORE_MINUTE_WEIGHT",
    "CostBreakdown",
    "DCU_MINUTE_WEIGHT",
    "MEMORY_GB_MINUTE_WEIGHT",
    "SETTLED_STATUSES",
    "check_submission_allowed",
    "compute_cost",
    "cost_from_task",
    "get_or_create_project_quota",
    "load_project_quota",
    "period_window",
    "project_active_counts",
    "project_usage_breakdown",
    "project_usage_minutes",
    "readable_project_ids",
    "serialize_default_quota",
    "serialize_quota",
    "settle_finished_tasks",
    "settle_task_cost_in_memory",
    "update_project_quota",
    "user_quota_summary",
    "validate_quota_changes",
]
