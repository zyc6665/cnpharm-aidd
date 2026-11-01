"""Workflow node scheduling service."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.models.users import User
from app.models.workflows import WorkflowRun
from app.services.workflow_condition_scheduler import schedule_condition_node
from app.services.workflow_dependencies import dependencies_satisfied
from app.services.workflow_loop_scheduler import schedule_loop_node
from app.services.workflow_map_scheduler import schedule_map_node
from app.services.workflow_tool_scheduler import schedule_workflow_node
from app.services.workflow_validation import (
    is_condition_node,
    is_loop_node,
    is_map_node,
    is_tool_node,
    nodes_by_id,
)


ScheduleTaskFn = Callable[..., Awaitable[Any]]

# 节点进入这些状态即视为已终结，不再参与调度；run 收口时据此判定是否收敛。
TERMINAL_NODE_STATUSES = frozenset({"success", "failure", "skipped", "blocked"})
# 其中这两种表示「未成功」：任一出现即把 run 收敛为 failure。
FAILED_NODE_STATUSES = frozenset({"failure", "blocked"})


async def start_ready_workflow_nodes(
    db: AsyncSession,
    *,
    current_user: User,
    run: WorkflowRun,
    schedule_task_fn: ScheduleTaskFn,
) -> int:
    definition = dict(run.definition or {})
    node_states = dict(run.node_states or {})
    indexed_nodes = nodes_by_id(definition)
    scheduled_count = 0

    for current_node_id in run.execution_order or []:
        state = dict(node_states.get(current_node_id) or {})
        if state.get("status") not in {None, "pending", "ready"}:
            continue
        if not dependencies_satisfied(
            definition=definition,
            node_states=node_states,
            node_id=current_node_id,
        ):
            continue

        node = indexed_nodes[current_node_id]
        if is_condition_node(node):
            if await schedule_condition_node(
                run=run,
                node_id=current_node_id,
                node=node,
                node_states=node_states,
            ):
                scheduled_count += 1
        elif is_map_node(node):
            if await schedule_map_node(
                db,
                current_user=current_user,
                run=run,
                node_id=current_node_id,
                node=node,
                node_states=node_states,
                schedule_task_fn=schedule_task_fn,
            ):
                scheduled_count += 1
        elif is_tool_node(node):
            if await schedule_workflow_node(
                db,
                current_user=current_user,
                run=run,
                node_id=current_node_id,
                node=node,
                node_states=node_states,
                schedule_task_fn=schedule_task_fn,
            ):
                scheduled_count += 1
        elif is_loop_node(node):
            if await schedule_loop_node(
                db,
                current_user=current_user,
                run=run,
                node_id=current_node_id,
                node=node,
                node_states=node_states,
                schedule_task_fn=schedule_task_fn,
            ):
                scheduled_count += 1

    run.node_states = node_states
    if scheduled_count > 0:
        run.status = "waiting_task"
        run.started_at = run.started_at or utcnow()
    elif run.execution_order and all(
        (node_states.get(current_node_id) or {}).get("status")
        in TERMINAL_NODE_STATUSES
        for current_node_id in run.execution_order
    ):
        failed_node_ids = [
            current_node_id
            for current_node_id in run.execution_order
            if (node_states.get(current_node_id) or {}).get("status")
            in FAILED_NODE_STATUSES
        ]
        run.status = "failure" if failed_node_ids else "success"
        run.finished_at = utcnow()
        if failed_node_ids and not run.error_message:
            run.error_message = (
                "Workflow run stopped because node(s) failed or blocked: "
                + ", ".join(failed_node_ids)
            )
    elif run.status == "pending":
        run.status = "pending"

    await db.commit()
    await db.refresh(run)
    return scheduled_count
