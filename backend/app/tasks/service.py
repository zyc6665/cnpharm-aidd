"""Reusable task creation and scheduling service."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.artifact_standards.registry import is_standard_artifact_ref
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
from app.services.run_preparation import PreparedRun, RunContext, RunPreparationInput, prepare_run
from app.services.standard_input_uploads import (
    accepts_materialized_standard_uploads,
    materialize_standard_input_uploads,
    standard_uploads_need_default_project,
    validate_standard_input_uploads,
)
from app.tasks.direct_runner import direct_task_runner as default_direct_task_runner
from app.tasks.naming import (
    resolve_task_display_name,
)
from app.tasks.resource_profile import build_task_resource_snapshot
from app.tasks.state_machine import TaskStateMachine
from app.tool_packages.config_resolver import tool_package_v2_manifest_data


logger = logging.getLogger(__name__)


def _is_known_standard_artifact_ref(value: object) -> bool:
    return isinstance(value, str) and is_standard_artifact_ref(value)


def _tool_config_emits_standard_artifacts(config: object) -> bool:
    if not isinstance(config, dict):
        return False

    manifest = tool_package_v2_manifest_data(config)
    if manifest is not None:
        artifacts = manifest.get("artifacts")
        outputs = artifacts.get("outputs") if isinstance(artifacts, dict) else None
        if isinstance(outputs, list):
            for output in outputs:
                if isinstance(output, dict) and _is_known_standard_artifact_ref(output.get("type")):
                    return True

    artifacts = config.get("artifacts")
    if isinstance(artifacts, dict):
        outputs = artifacts.get("outputs")
        if isinstance(outputs, list):
            for output in outputs:
                if isinstance(output, dict) and _is_known_standard_artifact_ref(output.get("type")):
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
                if _is_known_standard_artifact_ref(output.get("semantic_type")):
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


def _normalize_requested_input_bindings(values: dict[str, str] | None) -> dict[str, str]:
    return {
        str(input_name): str(version_id)
        for input_name, version_id in (values or {}).items()
        if str(input_name).strip() and str(version_id).strip()
    }


def _set_task_extra_data(task: Task, **values: object) -> None:
    base = task.extra_data if isinstance(task.extra_data, dict) else {}
    task.extra_data = {**base, **values}


async def dispatch_tool_task(
    *,
    db: AsyncSession,
    task: Task,
    tool_version: ToolVersion,
    user_role: str | None,
    direct_runner=default_direct_task_runner,
    resource_snapshot: dict[str, object] | None = None,
    failure_detail: str = "任务分发失败",
) -> None:
    """Dispatch a persisted task and keep dispatch metadata in sync."""
    try:
        if use_direct_task_execution():
            task.celery_task_id = None
            _set_task_extra_data(task, dispatch={"mode": "direct", "queue": None})
            direct_runner.schedule_task(
                task_id=str(task.id),
                tool_version_id=str(tool_version.id),
            )
            await db.commit()
            logger.info("Task %s scheduled in direct mode", task.id)
            return

        from app.tasks.queue_manager import TaskQueueManager

        snapshot = resource_snapshot if isinstance(resource_snapshot, dict) else {}
        gpu_required = snapshot.get("gpu_required")
        queue = TaskQueueManager.determine_queue(
            tool_config=tool_version.config,
            user_role=user_role,
            priority=task.priority,
            gpu_required=gpu_required if isinstance(gpu_required, bool) else None,
        )

        _set_task_extra_data(
            task,
            dispatch={
                "mode": "celery",
                "queue": queue,
                "queue_priority": TaskQueueManager.get_queue_priority(queue),
            },
        )
        celery_task = TaskQueueManager.enqueue_task(
            task_id=str(task.id),
            tool_version_id=str(tool_version.id),
            queue=queue,
        )

        task.celery_task_id = celery_task.id
        await db.commit()
        logger.info("Task %s enqueued to %s", task.id, queue)
    except Exception as exc:
        logger.error("Failed to dispatch task %s: %s", task.id, exc)
        TaskStateMachine.complete(
            task,
            success=False,
            error_message=f"{failure_detail}: {str(exc)}",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=failure_detail) from exc


async def _load_tool_and_version(
    db: AsyncSession,
    task_data: TaskCreate,
) -> tuple[Tool, ToolVersion, str]:
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

    return tool, tool_version, str(version_id)


async def _prepare_tool_task_run(
    *,
    db: AsyncSession,
    current_user: User,
    task_data: TaskCreate,
    extra_data: dict[str, object] | None = None,
    assign_default_project: bool,
) -> tuple[Tool, ToolVersion, str, PreparedRun, dict[str, object]]:
    tool, tool_version, version_id = await _load_tool_and_version(db, task_data)

    task_extra_data = dict(extra_data or {})
    task_extra_data["resource_snapshot"] = build_task_resource_snapshot(
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
        task_extra_data["project_id"] = project_id
    elif assign_default_project and (
        _tool_config_emits_standard_artifacts(tool_version.config)
        or standard_uploads_need_default_project(
            task_data.standard_input_uploads,
            tool_version.config,
        )
    ):
        project = await ensure_migration_project_for_owner(db, current_user)
        project_id = str(project.id)
        task_extra_data["project_id"] = project_id

    input_bindings = _normalize_requested_input_bindings(task_data.input_bindings)
    standard_input_uploads = _normalize_requested_input_bindings(task_data.standard_input_uploads)
    if (
        assign_default_project
        and project_id
        and standard_input_uploads
        and accepts_materialized_standard_uploads(tool_version.config)
    ):
        materialized_bindings = await materialize_standard_input_uploads(
            db,
            current_user=current_user,
            tool=tool,
            tool_version=tool_version,
            project_id=project_id,
            standard_input_uploads=standard_input_uploads,
        )
        input_bindings = {**input_bindings, **materialized_bindings}
        task_extra_data["standard_input_uploads"] = standard_input_uploads
        task_extra_data["materialized_standard_input_bindings"] = materialized_bindings
        standard_input_uploads = {}
    elif standard_input_uploads and accepts_materialized_standard_uploads(tool_version.config):
        await validate_standard_input_uploads(
            db,
            tool=tool,
            tool_version=tool_version,
            project_id=project_id,
            standard_input_uploads=standard_input_uploads,
        )

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
            input_bindings=input_bindings,
            standard_input_uploads=standard_input_uploads,
        ),
    )
    return tool, tool_version, version_id, prepared, task_extra_data


async def prepare_tool_task_preview(
    *,
    db: AsyncSession,
    current_user: User,
    task_data: TaskCreate,
) -> dict[str, object]:
    """Prepare task inputs and readiness decisions without creating a task."""
    tool, _tool_version, version_id, prepared, extra_data = await _prepare_tool_task_run(
        db=db,
        current_user=current_user,
        task_data=task_data,
        assign_default_project=False,
    )

    return {
        "ready": prepared.ready,
        "project_id": prepared.project_id,
        "tool_id": str(tool.id),
        "tool_version_id": version_id,
        "params": prepared.params,
        "file_ids": prepared.file_ids,
        "input_bindings": prepared.input_bindings,
        "requested_input_bindings": _normalize_requested_input_bindings(
            task_data.input_bindings,
        ),
        "standard_input_uploads": prepared.standard_input_uploads,
        "binding_decisions": prepared.binding_decisions,
        "blocked_reason": prepared.blocked_reason,
        "resource_snapshot": extra_data.get("resource_snapshot"),
    }


async def create_and_schedule_tool_task(
    *,
    db: AsyncSession,
    current_user: User,
    task_data: TaskCreate,
    direct_runner=default_direct_task_runner,
    extra_data: dict[str, object] | None = None,
) -> Task:
    """Create a normal platform task and schedule it through the configured backend."""
    tool, tool_version, version_id, prepared, extra_data = await _prepare_tool_task_run(
        db=db,
        current_user=current_user,
        task_data=task_data,
        extra_data=extra_data,
        assign_default_project=True,
    )
    if not prepared.ready:
        raise ValidationException(
            "标准 Artifact 输入尚未满足工具要求",
            detail={"binding_decisions": prepared.binding_decisions},
        )
    requested_input_bindings = _normalize_requested_input_bindings(task_data.input_bindings)
    if prepared.input_bindings:
        extra_data["input_bindings"] = prepared.input_bindings
    elif requested_input_bindings:
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

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=tool_version,
        user_role=current_user.role,
        direct_runner=direct_runner,
        resource_snapshot=extra_data.get("resource_snapshot"),
    )

    return task
