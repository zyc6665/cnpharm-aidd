"""Workflow task lookup helpers."""

from __future__ import annotations

from sqlalchemy import Text, cast, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tasks import Task, TaskInput, TaskStatus

# 这些状态下的节点任务仍代表一次有效调度；终态 FAILURE/CANCELED/TIMEOUT/REJECTED
# 允许同一节点重新建任务（数据库幂等键此时已随旧任务存在，故重试走「就地重试」
# 同一 task 行，而不是新建行）。
ACTIVE_WORKFLOW_TASK_STATUSES = frozenset(
    {
        TaskStatus.PENDING.value,
        TaskStatus.QUEUED.value,
        TaskStatus.RUNNING.value,
        TaskStatus.SUCCESS.value,
    }
)


async def find_existing_workflow_node_task(
    db: AsyncSession,
    *,
    run_id: str,
    node_id: str,
    attempt: int = 1,
) -> Task | None:
    """Return the task already scheduled for one workflow node attempt.

    查 ``(workflow_run_id, workflow_node_id, workflow_node_attempt)`` 三列
    （由迁移 20261030_06 落成真列 + 唯一索引），不再扫描「最近 20 条」再解析
    ``TaskInput.params``。
    """
    result = await db.execute(
        select(Task)
        .where(
            Task.workflow_run_id == str(run_id),
            Task.workflow_node_id == str(node_id),
            Task.workflow_node_attempt == int(attempt),
            Task.status.in_(ACTIVE_WORKFLOW_TASK_STATUSES),
        )
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(1)
    )
    found = result.scalar_one_or_none()
    if found is not None:
        return found

    legacy = await _find_legacy_task_by_params(db, run_id=str(run_id), node_id=str(node_id))
    if legacy is None:
        return None
    return await _claim_snapshot_columns(
        db,
        legacy,
        run_id=str(run_id),
        node_id=str(node_id),
        attempt=int(attempt),
    )


# ``TaskInput.params`` 里这两个键的历史写法（都见过 ``workflow_run_id``，兼容驼峰以防早期数据）
_SNAPSHOT_PARAM_KEYS = ("workflow_run_id", "workflowRunId")


async def _find_legacy_task_by_params(
    db: AsyncSession,
    *,
    run_id: str,
    node_id: str,
) -> Task | None:
    """回退按 ``TaskInput.params`` 找回没有快照列的历史任务。

    为什么需要：迁移 ``20261030_06`` 只给每组 ``(run, node)`` 里的一条历史行回填三列；
    同组若有多条非终态重复行，落选者三列留 NULL。没有这条回退，它们就再也查不到——
    调度器会另建一条新任务，而那条旧任务继续跑，重复占算力、重复写产物。这里查到即
    顺手认领（写回三列），下一个调度周期起就走精确三列查询。
    """
    result = await db.execute(
        select(Task)
        .join(TaskInput, TaskInput.task_id == Task.id)
        .where(
            Task.workflow_run_id.is_(None),
            Task.status.in_(ACTIVE_WORKFLOW_TASK_STATUSES),
            cast(TaskInput.params, Text).like(f"%{node_id}%"),
        )
        .order_by(Task.created_at.asc(), Task.id.asc())
    )
    for task in result.scalars().all():
        row = await db.execute(select(TaskInput.params).where(TaskInput.task_id == task.id))
        params = row.scalar_one_or_none()
        if not isinstance(params, dict):
            continue
        legacy_run = next((params.get(key) for key in _SNAPSHOT_PARAM_KEYS if params.get(key)), None)
        legacy_node = next((params.get(key) for key in ("workflow_node_id", "workflowNodeId") if params.get(key)), None)
        if str(legacy_run or "") == run_id and str(legacy_node or "") == node_id:
            return task
    return None


async def _claim_snapshot_columns(
    db: AsyncSession,
    task: Task,
    *,
    run_id: str,
    node_id: str,
    attempt: int,
) -> Task:
    """给回退查到的历史行补写三列；并发下只允许一个写入者成功。

    用 ``WHERE workflow_run_id IS NULL`` 保证「谁先认领谁生效」，撞唯一索引说明别人
    已经认领了另一行，此时重新精确查一次即可，不要把 ``IntegrityError`` 抛给调度器。
    """
    try:
        async with db.begin_nested():
            await db.execute(
                update(Task)
                .where(Task.id == task.id, Task.workflow_run_id.is_(None))
                .values(
                    workflow_run_id=run_id,
                    workflow_node_id=node_id,
                    workflow_node_attempt=attempt,
                )
            )
    except IntegrityError:
        claimed = await _find_by_snapshot(db, run_id=run_id, node_id=node_id, attempt=attempt)
        if claimed is not None:
            return claimed
    refreshed = await db.get(Task, task.id, populate_existing=True)
    return refreshed or task


async def _find_by_snapshot(
    db: AsyncSession,
    *,
    run_id: str,
    node_id: str,
    attempt: int,
) -> Task | None:
    result = await db.execute(
        select(Task).where(
            Task.workflow_run_id == run_id,
            Task.workflow_node_id == node_id,
            Task.workflow_node_attempt == attempt,
            Task.status.in_(ACTIVE_WORKFLOW_TASK_STATUSES),
        )
    )
    return result.scalars().first()
