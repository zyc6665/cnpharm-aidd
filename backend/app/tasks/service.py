"""Reusable task creation and scheduling service."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.config import settings, use_direct_task_execution
from app.common.exceptions import NotFoundException, ValidationException
from app.database.base import utcnow
from app.models.statistics import ToolStatistics
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.schemas.tasks import TaskCreate
from app.services.project_access import load_project_membership
from app.services.project_migration import ensure_migration_project_for_owner
from app.services.run_input_normalization import normalize_string_mapping
from app.services.run_preparation import PreparedRun, RunContext, RunPreparationInput, prepare_run
from app.services.tool_contracts import (
    build_tool_contract,
    contract_emits_standard_artifacts,
    tool_emits_standard_artifacts,
)
from app.services.standard_input_uploads import (
    accepts_materialized_standard_uploads,
    materialize_standard_input_uploads,
    standard_uploads_need_default_project,
    validate_standard_input_uploads,
)
from app.tasks.attempts import (
    invoke_with_optional_attempt,
    new_execution_attempt_id,
    set_execution_attempt_id,
)
from app.tasks.commands import TaskCommand
from app.common.task_context import set_task_project_id
from app.tasks.direct_runner import direct_task_runner as default_direct_task_runner
from app.tasks.naming import (
    resolve_task_display_name,
)
from app.tasks.resource_profile import (
    ResourceRequest,
    build_resource_request,
    build_task_resource_snapshot,
)
from app.tasks.resource_admission import ResourceAdmissionPolicy
from app.tasks.worker_capability_registry import WorkerCapabilityRegistry
from app.tasks.state_machine import TaskStateMachine


logger = logging.getLogger(__name__)


def _tool_config_emits_standard_artifacts(config: object) -> bool:
    if not isinstance(config, dict):
        return False
    tool = SimpleNamespace(
        slug=config.get("builtin_slug"),
        current_version=SimpleNamespace(config=config),
    )
    return contract_emits_standard_artifacts(build_tool_contract(tool))


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


def _set_task_extra_data(task: Task, **values: object) -> None:
    base = task.extra_data if isinstance(task.extra_data, dict) else {}
    task.extra_data = {**base, **values}


def _resource_request_from_snapshot(
    *,
    tool_version: ToolVersion,
    resource_snapshot: dict[str, object],
) -> ResourceRequest:
    payload = resource_snapshot.get("resource_request")
    required_fields = {
        "executor_type",
        "tier",
        "cpu",
        "memory_gb",
        "cpu_limit",
        "memory_limit",
        "gpu_required",
        "gpu_count",
        "gpu_memory_mb",
        "timeout_sec",
        "parallelism",
    }
    if isinstance(payload, dict) and required_fields.issubset(payload):
        try:
            return ResourceRequest(
                executor_type=payload.get("executor_type"),
                tier=payload.get("tier"),
                cpu=float(payload["cpu"]) if payload["cpu"] is not None else None,
                memory_gb=(
                    float(payload["memory_gb"])
                    if payload["memory_gb"] is not None
                    else None
                ),
                cpu_limit=(
                    float(payload["cpu_limit"])
                    if payload["cpu_limit"] is not None
                    else None
                ),
                memory_limit=payload.get("memory_limit"),
                gpu_required=bool(payload["gpu_required"]),
                gpu_count=int(payload["gpu_count"]),
                gpu_memory_mb=int(payload["gpu_memory_mb"]),
                timeout_sec=int(payload["timeout_sec"]),
                parallelism=int(payload["parallelism"]),
            )
        except (TypeError, ValueError):
            pass

    fallback_kwargs: dict[str, object] = {}
    gpu_required = resource_snapshot.get("gpu_required")
    gpu_memory_mb = resource_snapshot.get("gpu_memory_mb")
    if isinstance(gpu_required, bool):
        fallback_kwargs["gpu_required"] = gpu_required
    if isinstance(gpu_memory_mb, (int, float)):
        fallback_kwargs["gpu_memory_mb"] = int(gpu_memory_mb)
    return build_resource_request(tool_version.config, **fallback_kwargs)


async def _resource_admission_metadata(
    *,
    tool_version: ToolVersion,
    resource_snapshot: dict[str, object],
) -> dict[str, object] | None:
    """评估当前在线 Worker，但只记录结果，不阻断任务入队。"""
    if not settings.WORKER_CAPABILITY_ADMISSION_ENABLED:
        return None

    try:
        from app.cache import get_cache

        request = _resource_request_from_snapshot(
            tool_version=tool_version,
            resource_snapshot=resource_snapshot,
        )
        registry = WorkerCapabilityRegistry(
            cache=get_cache(),
            ttl_seconds=settings.WORKER_CAPABILITY_TTL_SECONDS,
        )
        capabilities = await registry.list_active()
        if not capabilities:
            return {
                "status": "unknown",
                "worker_id": None,
                "reason": "no_registered_workers",
            }

        decision = ResourceAdmissionPolicy.select_worker(request, capabilities)
        if decision.admitted:
            return {
                "status": "admitted",
                "worker_id": decision.worker_id,
                "reason": None,
            }

        return {
            "status": "rejected",
            "worker_id": None,
            "reason": decision.reason,
        }
    except Exception as exc:
        logger.warning(
            "Resource admission observation unavailable for task tool version %s: %s",
            tool_version.id,
            exc,
        )
        return {
            "status": "unknown",
            "worker_id": None,
            "reason": "admission_check_unavailable",
        }


async def dispatch_tool_task(
    *,
    db: AsyncSession,
    task: Task,
    tool_version: ToolVersion,
    user_role: str | None,
    direct_runner=default_direct_task_runner,
    resource_snapshot: dict[str, object] | None = None,
    failure_detail: str = "任务分发失败",
    countdown: int = 0,
) -> None:
    """Dispatch a persisted task and keep dispatch metadata in sync."""
    try:
        attempt_id = new_execution_attempt_id()
        set_execution_attempt_id(task, attempt_id)

        if use_direct_task_execution():
            task.celery_task_id = None
            _set_task_extra_data(task, dispatch={"mode": "direct", "queue": None})
            await db.commit()
            invoke_with_optional_attempt(
                direct_runner.schedule_task,
                task_id=str(task.id),
                tool_version_id=str(tool_version.id),
                attempt_id=attempt_id,
            )
            logger.info("Task %s scheduled in direct mode", task.id)
            return

        from app.tasks.queue_manager import TaskQueueManager

        snapshot = resource_snapshot if isinstance(resource_snapshot, dict) else {}
        if not snapshot and isinstance(task.extra_data, dict):
            task_snapshot = task.extra_data.get("resource_snapshot")
            if isinstance(task_snapshot, dict):
                snapshot = task_snapshot
        gpu_required = snapshot.get("gpu_required")
        queue = TaskQueueManager.determine_queue(
            tool_config=tool_version.config,
            user_role=user_role,
            priority=task.priority,
            gpu_required=gpu_required if isinstance(gpu_required, bool) else None,
        )

        dispatch_metadata: dict[str, object] = {
            "mode": "celery",
            "queue": queue,
            "queue_priority": TaskQueueManager.get_queue_priority(queue),
        }
        admission_metadata = await _resource_admission_metadata(
            tool_version=tool_version,
            resource_snapshot=snapshot,
        )
        if admission_metadata is not None:
            dispatch_metadata["resource_admission"] = admission_metadata
        _set_task_extra_data(task, dispatch=dispatch_metadata)
        await db.commit()
        enqueue_kwargs = {
            "task_id": str(task.id),
            "tool_version_id": str(tool_version.id),
            "queue": queue,
        }
        if countdown > 0:
            enqueue_kwargs["countdown"] = int(countdown)
        celery_task = invoke_with_optional_attempt(
            TaskQueueManager.enqueue_task,
            **enqueue_kwargs,
            attempt_id=attempt_id,
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
        task_extra_data = set_task_project_id(task_extra_data, project_id)
    elif assign_default_project and (
        tool_emits_standard_artifacts(tool)
        or standard_uploads_need_default_project(
            task_data.standard_input_uploads,
            tool_version.config,
        )
    ):
        project = await ensure_migration_project_for_owner(db, current_user)
        project_id = str(project.id)
        task_extra_data = set_task_project_id(task_extra_data, project_id)

    input_bindings = normalize_string_mapping(task_data.input_bindings)
    standard_input_uploads = normalize_string_mapping(task_data.standard_input_uploads)
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
        "requested_input_bindings": normalize_string_mapping(
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
    command = TaskCommand.from_prepared_run(
        user_id=str(current_user.id),
        tool_id=str(task_data.tool_id),
        tool_version_id=version_id,
        name=task_data.name,
        priority=task_data.priority,
        prepared_run=prepared,
        requested_input_bindings=task_data.input_bindings,
        extra_data=extra_data,
    )
    task_input = command.task_input

    task = Task(
        user_id=command.user_id,
        tool_id=command.tool_id,
        tool_version_id=command.tool_version_id,
        status=TaskStatus.PENDING.value,
        priority=command.priority,
        progress=0.0,
        extra_data=command.extra_data,
    )

    db.add(task)
    await db.flush()
    task.name = resolve_task_display_name(
        name=command.name,
        tool_name=tool.name,
        created_at=task.created_at,
        task_id=task.id,
    )

    db.add(
        TaskInput(
            task_id=task.id,
            params=task_input["params"],
            file_ids=task_input["file_ids"],
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
        resource_snapshot=command.extra_data.get("resource_snapshot"),
    )

    return task
