"""Reusable task creation and scheduling service."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.config import use_direct_task_execution
from app.common.exceptions import NotFoundException, ValidationException
from app.database.base import utcnow
from app.models.statistics import ToolStatistics
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.schemas.tasks import TaskCreate
from app.tasks.direct_runner import direct_task_runner as default_direct_task_runner
from app.tasks.naming import (
    _sanitize_task_name,
    _build_default_task_name,
    resolve_task_display_name,
)
from app.tasks.state_machine import TaskStateMachine


logger = logging.getLogger(__name__)


async def record_tool_usage(db: AsyncSession, tool_id: str) -> None:
    """Ensure tool statistics exists, then record one use."""
    now = utcnow()

    update_result = await db.execute(
        update(ToolStatistics)
        .where(ToolStatistics.tool_id == tool_id)
        .values(
            usage_count=ToolStatistics.usage_count + 1,
            last_used_at=now,
            last_updated_at=now,
        )
    )
    if update_result.rowcount:
        return

    statistics = ToolStatistics(
        tool_id=tool_id,
        usage_count=1,
        last_used_at=now,
        last_updated_at=now,
    )
    db.add(statistics)
    await db.flush()


async def create_and_schedule_tool_task(
    *,
    db: AsyncSession,
    current_user: User,
    task_data: TaskCreate,
    direct_runner=default_direct_task_runner,
) -> Task:
    """Create a normal platform task and schedule it through the configured backend."""
    result = await db.execute(
        select(Tool)
        .options(
            selectinload(Tool.current_version),
            joinedload(Tool.statistics),
        )
        .where(Tool.id == task_data.tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    version_id = task_data.tool_version_id
    if not version_id:
        if not tool.current_version_id:
            raise ValidationException("工具没有可用版本")
        version_id = tool.current_version_id

    task = Task(
        user_id=current_user.id,
        tool_id=task_data.tool_id,
        tool_version_id=version_id,
        status=TaskStatus.PENDING.value,
        priority=task_data.priority,
        progress=0.0,
    )

    db.add(task)
    await db.flush()
    task.name = resolve_task_display_name(
        name=task_data.name,
        tool_name=tool.name,
        created_at=task.created_at,
        task_id=task.id,
    )

    db.add(
        TaskInput(
            task_id=task.id,
            params=task_data.params,
            file_ids=task_data.file_ids or [],
        )
    )

    await record_tool_usage(db, str(tool.id))

    await db.commit()
    await db.refresh(task)

    try:
        if use_direct_task_execution():
            direct_runner.schedule_task(
                task_id=str(task.id),
                tool_version_id=str(version_id),
            )
            logger.info("Task %s scheduled in direct mode", task.id)
        else:
            from app.tasks.queue_manager import TaskQueueManager

            version_result = await db.execute(
                select(ToolVersion).where(ToolVersion.id == version_id)
            )
            tool_version = version_result.scalar_one()

            queue = TaskQueueManager.determine_queue(
                tool_config=tool_version.config,
                user_role=current_user.role,
                priority=task_data.priority,
            )

            celery_task = TaskQueueManager.enqueue_task(
                task_id=str(task.id),
                tool_version_id=str(version_id),
                queue=queue,
            )

            task.celery_task_id = celery_task.id
            await db.commit()

            logger.info("Task %s enqueued to %s", task.id, queue)

    except Exception as exc:
        logger.error("Failed to enqueue task %s: %s", task.id, exc)
        TaskStateMachine.complete(
            task,
            success=False,
            error_message=f"任务分发失败: {str(exc)}",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail="任务分发失败") from exc

    return task
