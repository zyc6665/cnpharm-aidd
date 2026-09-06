"""Reusable task creation and scheduling service."""

from __future__ import annotations

import logging
from typing import Any

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
from app.services.project_access import load_project_membership
from app.services.project_migration import ensure_migration_project_for_owner
from app.services.run_preparation import RunContext, RunPreparationInput, prepare_run
from app.tasks.direct_runner import direct_task_runner as default_direct_task_runner
from app.tasks.naming import (
    resolve_task_display_name,
)
from app.tasks.resource_profile import build_task_resource_snapshot
from app.tasks.state_machine import TaskStateMachine


logger = logging.getLogger(__name__)


def _is_standard_artifact_ref(value: object) -> bool:
    return isinstance(value, str) and "@" in value and bool(value.split("@", 1)[0])


def _tool_config_emits_standard_artifacts(config: object) -> bool:
    if not isinstance(config, dict):
        return False

    artifacts = config.get("artifacts")
    if isinstance(artifacts, dict):
        outputs = artifacts.get("outputs")
        if isinstance(outputs, list):
            for output in outputs:
                if isinstance(output, dict) and _is_standard_artifact_ref(output.get("type")):
                    return True

    capability = config.get("agent_capability")
    if isinstance(capability, dict):
        outputs = capability.get("outputs")
        if isinstance(outputs, list):
            for output in outputs:
                if not isinstance(output, dict):
                    continue
                if output.get("source") == "artifact":
                    return True
                if _is_standard_artifact_ref(output.get("semantic_type")):
                    return True

    return False


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

    version_result = await db.execute(
        select(ToolVersion).where(ToolVersion.id == version_id)
    )
    tool_version = version_result.scalar_one_or_none()
    if not tool_version:
        raise ValidationException("工具版本不存在")

    extra_data = dict(extra_data or {})
    extra_data["resource_snapshot"] = build_task_resource_snapshot(
        tool_version.config,
        gpu_required=tool.gpu_required,
        gpu_memory_mb=tool.gpu_memory_mb,
        params=task_data.params,
    )
    project_id = task_data.project_id
    if project_id:
        await load_project_membership(
            db,
            project_id=project_id,
            user_id=current_user.id,
        )
        extra_data["project_id"] = project_id
    elif _tool_config_emits_standard_artifacts(tool_version.config):
        project = await ensure_migration_project_for_owner(db, current_user)
        project_id = str(project.id)
        extra_data["project_id"] = project_id

    prepared = await prepare_run(
        db,
        input=RunPreparationInput(
            tool=tool,
            tool_version=tool_version,
            context=RunContext(
                surface="tool_detail",
                user_id=str(current_user.id),
                project_id=project_id,
            ),
            params=dict(task_data.params or {}),
            file_ids=list(task_data.file_ids or []),
            input_bindings=task_data.input_bindings,
            standard_input_uploads=task_data.standard_input_uploads,
        ),
    )
    if not prepared.ready:
        raise ValidationException(
            "标准 Artifact 输入尚未满足工具要求",
            detail={"binding_decisions": prepared.binding_decisions},
        )
    requested_input_bindings = {
        str(input_name): str(version_id)
        for input_name, version_id in (task_data.input_bindings or {}).items()
        if str(input_name).strip() and str(version_id).strip()
    }
    if requested_input_bindings:
        extra_data["input_bindings"] = requested_input_bindings
    if prepared.standard_input_uploads:
        extra_data["standard_input_uploads"] = prepared.standard_input_uploads
    if prepared.binding_decisions:
        extra_data["binding_decisions"] = prepared.binding_decisions
    params = prepared.params
    file_ids = prepared.file_ids

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
            params=params,
            file_ids=file_ids,
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
            task.extra_data = {
                **(task.extra_data or {}),
                "dispatch": {"mode": "direct", "queue": None},
            }
            await db.commit()
            logger.info("Task %s scheduled in direct mode", task.id)
        else:
            from app.tasks.queue_manager import TaskQueueManager

            queue = TaskQueueManager.determine_queue(
                tool_config=tool_version.config,
                user_role=current_user.role,
                priority=task_data.priority,
                gpu_required=bool(extra_data["resource_snapshot"].get("gpu_required")),
            )

            celery_task = TaskQueueManager.enqueue_task(
                task_id=str(task.id),
                tool_version_id=str(version_id),
                queue=queue,
            )

            task.celery_task_id = celery_task.id
            task.extra_data = {
                **(task.extra_data or {}),
                "dispatch": {
                    "mode": "celery",
                    "queue": queue,
                    "queue_priority": TaskQueueManager.get_queue_priority(queue),
                },
            }
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
