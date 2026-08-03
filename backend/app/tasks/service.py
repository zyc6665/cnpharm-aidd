"""Reusable task creation and scheduling service."""

from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.config import use_direct_task_execution
from app.common.exceptions import NotFoundException, ValidationException
from app.database.base import utcnow
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.statistics import ToolStatistics
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.schemas.tasks import TaskCreate
from app.services.project_access import load_project_membership
from app.tasks.direct_runner import direct_task_runner as default_direct_task_runner
from app.tasks.naming import (
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


async def _validate_standard_input_bindings(
    db: AsyncSession,
    *,
    project_id: str | None,
    input_bindings: dict[str, str],
) -> dict[str, str]:
    """Validate task standard ArtifactVersion bindings and return a normalized mapping."""
    normalized = {
        str(input_name): str(version_id)
        for input_name, version_id in (input_bindings or {}).items()
        if str(input_name).strip() and str(version_id).strip()
    }
    if not normalized:
        return {}
    if not project_id:
        raise ValidationException("标准 ArtifactVersion 输入绑定必须提供 project_id")

    version_ids = set(normalized.values())
    result = await db.execute(
        select(ArtifactVersion.id, Artifact.project_id)
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
        .where(
            ArtifactVersion.id.in_(version_ids),
            ArtifactVersion.status == "available",
        )
    )
    projects_by_version = {
        str(version_id): str(owner_project_id)
        for version_id, owner_project_id in result.all()
    }
    missing = sorted(version_ids - set(projects_by_version))
    if missing:
        raise ValidationException(
            "输入绑定引用的 ArtifactVersion 不存在",
            detail={"missing_artifact_version_ids": missing},
        )
    mismatched = sorted(
        version_id
        for version_id, owner_project_id in projects_by_version.items()
        if owner_project_id != project_id
    )
    if mismatched:
        raise ValidationException(
            "输入绑定的 ArtifactVersion 必须属于任务关联项目",
            detail={"mismatched_artifact_version_ids": mismatched},
        )
    return normalized


async def create_and_schedule_tool_task(
    *,
    db: AsyncSession,
    current_user: User,
    task_data: TaskCreate,
    direct_runner=default_direct_task_runner,
    extra_data: dict[str, object] | None = None,
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

    extra_data = dict(extra_data or {})
    if task_data.project_id:
        await load_project_membership(
            db,
            project_id=task_data.project_id,
            user_id=current_user.id,
        )
        extra_data["project_id"] = task_data.project_id
    input_bindings = await _validate_standard_input_bindings(
        db,
        project_id=task_data.project_id,
        input_bindings=task_data.input_bindings,
    )
    if input_bindings:
        extra_data["input_bindings"] = input_bindings

    task = Task(
        user_id=current_user.id,
        tool_id=task_data.tool_id,
        tool_version_id=version_id,
        status=TaskStatus.PENDING.value,
        priority=task_data.priority,
        progress=0.0,
        extra_data=extra_data,
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
                gpu_required=tool.gpu_required,
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
