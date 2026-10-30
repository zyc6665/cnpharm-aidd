"""任务工作台系统视图查询。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.common.exceptions import ValidationException
from app.common.keyset import apply_desc_keyset, encode_cursor, next_cursor
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.services.project_access import load_project_membership


TaskSystemView = Literal["all", "running", "history", "needs_attention", "recent_results"]

_VIEW_STATUSES: dict[str, tuple[str, ...]] = {
    # 「进行中」= 已创建但未出结果的任务，包含排队中（QUEUED）与运行中（RUNNING）。
    "running": (
        TaskStatus.PENDING.value,
        TaskStatus.QUEUED.value,
        TaskStatus.RUNNING.value,
    ),
    "history": (
        TaskStatus.SUCCESS.value,
        TaskStatus.FAILURE.value,
        TaskStatus.CANCELED.value,
        TaskStatus.TIMEOUT.value,
        # 被拒也是「已出结果」（结果是「没让你跑」）。漏在这里会让 REJECTED
        # 行只在 view=all 下可见——用户去「历史」找「我那次被拒的提交」会找不到，
        # 而它存在的唯一理由就是被找到。
        TaskStatus.REJECTED.value,
    ),
    "needs_attention": (
        TaskStatus.FAILURE.value,
        TaskStatus.TIMEOUT.value,
        # 刻意不含 REJECTED：这是「需要运维看一眼」的口径（执行侧炸了/超时了）。
        # 被拒是用户侧的输入问题，已经在提交那一刻用 429 明确告知过，
        # 混进来只会让值班的人去追一批「用户参数填大了」的历史记录。
    ),
    "recent_results": (TaskStatus.SUCCESS.value,),
}


@dataclass(frozen=True)
class TaskQueryInput:
    """任务查询输入，承载系统视图、权限上下文和基础筛选。"""

    current_user: User
    page: int = 1
    page_size: int = 20
    view: str | None = None
    status: str | None = None
    tool_id: str | None = None
    keyword: str | None = None
    project_id: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    workflow_run_id: str | None = None
    workflow_definition_id: str | None = None
    workflow_node_id: str | None = None
    resource_wait_category: str | None = None
    resource_wait_scope: str | None = None


@dataclass(frozen=True)
class TaskQueryPage:
    """任务分页查询结果。

    ``total`` 在游标模式下是 ``None``——算总数与深分页同代价，会把这轮优化的收益
    抵掉；调用方看到 ``next_cursor`` 就应该只用它翻页。
    """

    tasks: list[Task]
    total: int | None
    next_cursor: str | None = None
    has_more: bool = False


@dataclass(frozen=True)
class TaskViewCounts:
    """任务系统视图计数。"""

    all: int
    running: int
    history: int
    needs_attention: int
    recent_results: int


@dataclass(frozen=True)
class ResourceWaitStats:
    """当前可见 pending 任务的资源等待统计。"""

    total: int
    by_category: dict[str, int]
    by_reason: dict[str, int]


async def query_task_page(
    db: AsyncSession,
    query: TaskQueryInput,
    *,
    cursor: str | None = None,
) -> TaskQueryPage:
    """按系统视图和基础筛选查询当前用户可见任务。

    两种取页方式：

    * 不给 ``cursor``：保留 ``page``/``page_size`` 偏移分页与 ``total``，
      兼容既有调用方与前端「第 N 页」交互；
    * 给 ``cursor``：走 keyset，**不计算 total**，用「多取一条」判断 ``hasMore``。
      排序键 ``(created_at DESC, id DESC)`` 与 ``ix_tasks_created_at`` /
      主键配合，代价与页深无关。
    """
    statement = await _build_task_statement(
        db,
        query,
        include_view_filters=True,
        include_load_options=True,
    )
    page_size = max(query.page_size, 1)

    if cursor:
        statement, _last = apply_desc_keyset(
            statement,
            timestamp_column=Task.created_at,
            id_column=Task.id,
            cursor=cursor,
        )
        result = await db.execute(
            statement.order_by(Task.created_at.desc(), Task.id.desc()).limit(page_size + 1)
        )
        fetched = list(result.scalars().all())
        has_more = len(fetched) > page_size
        rows = fetched[:page_size]
        return TaskQueryPage(
            tasks=rows,
            total=None,
            # 游标取「本页最后一行」，且只在确实还有下一页时给，免得前端多跑一次空请求。
            next_cursor=next_cursor(
                fetched, timestamp_attr="created_at", id_attr="id", limit=page_size
            ),
            has_more=has_more,
        )

    total = await _count_tasks(db, statement)
    offset = (max(query.page, 1) - 1) * page_size
    result = await db.execute(
        statement.order_by(Task.created_at.desc(), Task.id.desc()).offset(offset).limit(page_size)
    )
    rows = list(result.scalars().all())
    # 偏移模式也给出 nextCursor：客户端翻到第 3 页想换成游标分页时不需要额外接口，
    # 直接拿这一页的 nextCursor 接着走即可。hasMore 用 total 判断，零额外查询。
    has_more = bool(rows) and (offset + len(rows)) < total
    return TaskQueryPage(
        tasks=rows,
        total=total,
        next_cursor=encode_cursor([rows[-1].created_at, rows[-1].id]) if has_more else None,
        has_more=has_more,
    )


async def query_task_view_counts(db: AsyncSession, query: TaskQueryInput) -> TaskViewCounts:
    """按同一权限和筛选条件返回各系统视图计数。"""
    statement = await _build_task_statement(
        db,
        query,
        include_view_filters=False,
        include_load_options=False,
    )
    status_subquery = statement.with_only_columns(Task.status.label("status")).subquery()
    result = await db.execute(
        select(status_subquery.c.status, func.count())
        .select_from(status_subquery)
        .group_by(status_subquery.c.status)
    )
    counts_by_status = {str(status): int(count) for status, count in result.all()}
    return TaskViewCounts(
        all=sum(counts_by_status.values()),
        running=_sum_status_counts(counts_by_status, _VIEW_STATUSES["running"]),
        history=_sum_status_counts(counts_by_status, _VIEW_STATUSES["history"]),
        needs_attention=_sum_status_counts(counts_by_status, _VIEW_STATUSES["needs_attention"]),
        recent_results=_sum_status_counts(counts_by_status, _VIEW_STATUSES["recent_results"]),
    )


async def query_resource_wait_stats(
    db: AsyncSession,
    query: TaskQueryInput,
) -> ResourceWaitStats:
    """统计当前可见的排队/待调度任务的资源等待分类和原因。"""
    statement = await _build_task_statement(
        db,
        query,
        include_view_filters=False,
        include_load_options=False,
    )
    statement = statement.where(
        Task.status.in_([TaskStatus.PENDING.value, TaskStatus.QUEUED.value])
    )
    statement = statement.where(
        or_(
            Task.extra_data["resource_wait_code"].as_string().is_not(None),
            Task.extra_data["resource_wait_reason"].as_string().is_not(None),
        )
    )
    wait_subquery = statement.with_only_columns(
        Task.extra_data["resource_wait_category"].as_string().label("category"),
        Task.extra_data["resource_wait_code"].as_string().label("reason"),
    ).subquery()
    result = await db.execute(
        select(wait_subquery.c.category, wait_subquery.c.reason)
    )

    by_category: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    total = 0
    for category, reason in result.all():
        total += 1
        category_key = str(category or "legacy")
        reason_key = str(reason or "resource_wait")
        by_category[category_key] = by_category.get(category_key, 0) + 1
        by_reason[reason_key] = by_reason.get(reason_key, 0) + 1

    return ResourceWaitStats(
        total=total,
        by_category=dict(sorted(by_category.items())),
        by_reason=dict(sorted(by_reason.items())),
    )


async def _build_task_statement(
    db: AsyncSession,
    query: TaskQueryInput,
    *,
    include_view_filters: bool,
    include_load_options: bool,
):
    statement = select(Task)
    if include_load_options:
        statement = statement.options(
            selectinload(Task.tool),
            joinedload(Task.user),
        )

    is_admin = query.current_user.role == "admin"
    if query.project_id:
        if not is_admin:
            await load_project_membership(
                db,
                project_id=query.project_id,
                user_id=query.current_user.id,
            )
        statement = statement.where(Task.project_id_expression() == query.project_id)
    elif not is_admin:
        statement = statement.where(Task.user_id == query.current_user.id)

    if include_view_filters:
        view_statuses = _statuses_for_view(query.view)
        if view_statuses:
            statement = statement.where(Task.status.in_(view_statuses))

        if query.status:
            statement = statement.where(Task.status == query.status.upper())

    if query.tool_id:
        statement = statement.where(Task.tool_id == query.tool_id)

    if query.resource_wait_category:
        statement = statement.where(
            Task.extra_data["resource_wait_category"].as_string()
            == query.resource_wait_category
        )
    if query.resource_wait_scope:
        statement = statement.where(
            Task.extra_data["resource_wait_scope"].as_string()
            == query.resource_wait_scope
        )

    if query.created_from:
        statement = statement.where(Task.created_at >= _naive_utc(query.created_from))
    if query.created_to:
        statement = statement.where(Task.created_at <= _naive_utc(query.created_to))

    if query.workflow_run_id or query.workflow_definition_id or query.workflow_node_id:
        # 这三项原先都从 ``TaskInput.params`` 的 JSON 里取，既要多 join 一张表，
        # 又让 `params->>'…'` 这种表达式挡在 WHERE 里用不上索引。`tasks` 上已有
        # 真列 `workflow_run_id` / `workflow_node_id`（迁移 20261030_06 已从 params
        # 回填），并且 `uq_tasks_workflow_node_attempt` 的前缀正好覆盖 run 维度。
        # `workflow_definition_id` 不在 tasks 上，改为按 run 反查（两表、两侧都有索引）。
        if query.workflow_definition_id:
            statement = statement.join(
                WorkflowRun, WorkflowRun.id == Task.workflow_run_id
            ).where(
                WorkflowRun.workflow_definition_id == query.workflow_definition_id
            )
        if query.workflow_run_id:
            statement = statement.where(Task.workflow_run_id == query.workflow_run_id)
        if query.workflow_node_id:
            statement = statement.where(Task.workflow_node_id == query.workflow_node_id)

    if query.keyword:
        keyword = query.keyword.strip()
        if keyword:
            search_pattern = f"%{keyword}%"
            # 关键字搜索只覆盖「标识类」短字段：任务名、工具名/别名、用户邮箱/显示名，
            # 外加任务 ID 的精确匹配。原来是 8 列 ilike('%kw%') 的 OR（含
            # error_message / progress_message 两个 Text 列）——前导通配无法走索引，
            # 两个长文本列又把每行要扫的字节放大一个量级，且会强制带上 Tool/User
            # 两个 outer join。长文本检索交给任务日志（task_logs）承担。
            statement = (
                statement.join(Tool, Task.tool_id == Tool.id, isouter=True)
                .join(User, Task.user_id == User.id, isouter=True)
                .where(
                    or_(
                        Task.id == keyword,
                        Task.name.ilike(search_pattern),
                        Tool.name.ilike(search_pattern),
                        Tool.slug.ilike(search_pattern),
                        User.email.ilike(search_pattern),
                        User.display_name.ilike(search_pattern),
                    )
                )
            )

    return statement


def _sum_status_counts(counts_by_status: dict[str, int], statuses: tuple[str, ...]) -> int:
    return sum(counts_by_status.get(status, 0) for status in statuses)


def _statuses_for_view(view: str | None) -> tuple[str, ...]:
    if not view or view == "all":
        return ()
    statuses = _VIEW_STATUSES.get(view)
    if statuses is None:
        raise ValidationException("未知任务系统视图", detail={"view": view})
    return statuses


async def _count_tasks(db: AsyncSession, statement) -> int:
    # 计数只需要 WHERE 条件（以及过滤用的 JOIN），ORDER BY 对 count 毫无意义。
    # 保留排序会让数据库在子查询里白排一遍全部命中行——任务列表默认按
    # created_at DESC + id DESC 排，几万行时这部分开销与真正返回 20 行同量级。
    result = await db.execute(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    return int(result.scalar() or 0)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
