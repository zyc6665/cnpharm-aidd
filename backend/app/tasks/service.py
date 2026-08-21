"""Reusable task creation and scheduling service."""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.config import use_direct_task_execution
from app.common.exceptions import NotFoundException, ValidationException
from app.database.base import utcnow
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.files import File as FileModel
from app.models.statistics import ToolStatistics
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.schemas.tasks import TaskCreate
from app.services.artifact_binding_resolver import resolve_artifact_binding
from app.services.project_access import load_project_membership
from app.services.project_migration import ensure_migration_project_for_owner
from app.services.tool_contracts import build_tool_contract
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


async def _project_standard_input_bindings(
    db: AsyncSession,
    *,
    tool: Tool,
    tool_version: ToolVersion,
    input_bindings: dict[str, str],
    params: dict[str, Any],
    file_ids: list[str],
) -> dict[str, Any]:
    if not input_bindings:
        return {"params": params, "file_ids": _dedupe_ordered(file_ids), "binding_decisions": {}}

    contract = build_tool_contract(tool)
    artifact_inputs = (contract.get("artifacts") or {}).get("inputs")
    if not isinstance(artifact_inputs, list):
        return {"params": params, "file_ids": _dedupe_ordered(file_ids), "binding_decisions": {}}

    binding_decisions: dict[str, dict[str, Any]] = {}
    next_params = dict(params)
    next_file_ids = list(file_ids)
    for slot in artifact_inputs:
        if not isinstance(slot, dict):
            continue
        slot_name = str(slot.get("name") or "")
        version_id = input_bindings.get(slot_name)
        if not slot_name or not version_id or not _slot_needs_binding_resolution(slot):
            continue
        decision = await resolve_artifact_binding(
            db,
            input_slot=slot,
            candidate_artifact_version_id=version_id,
        )
        binding_decisions[slot_name] = asdict(decision)
        if decision.status != "ready":
            raise ValidationException(
                "标准 Artifact 输入尚未满足工具要求",
                detail={"binding_decisions": binding_decisions},
            )
        if not decision.selected_file_id:
            continue
        next_file_ids.append(decision.selected_file_id)
        await _project_selected_file_to_legacy_params(
            db,
            tool_version=tool_version,
            input_slot=slot,
            file_id=decision.selected_file_id,
            params=next_params,
        )

    return {
        "params": next_params,
        "file_ids": _dedupe_ordered(next_file_ids),
        "binding_decisions": binding_decisions,
    }


def _slot_needs_binding_resolution(slot: dict[str, Any]) -> bool:
    return any(
        key in slot and slot.get(key) not in (None, "", [])
        for key in (
            "role_preferences",
            "required_roles",
            "readiness_policy",
            "suggested_preparation_tool",
        )
    )


async def _project_selected_file_to_legacy_params(
    db: AsyncSession,
    *,
    tool_version: ToolVersion,
    input_slot: dict[str, Any],
    file_id: str,
    params: dict[str, Any],
) -> None:
    config = tool_version.config if isinstance(tool_version.config, dict) else {}
    executor_type = str(config.get("type") or "")
    if executor_type not in {"ssh_job", "builtin"}:
        return

    file_record = await db.get(FileModel, file_id)
    if not file_record:
        return

    if executor_type == "builtin":
        builtin_inputs = params.get("builtin_inputs") if isinstance(params.get("builtin_inputs"), dict) else {}
        params["builtin_inputs"] = {**builtin_inputs, str(input_slot.get("type") or input_slot.get("name")): file_id}
        return

    file_field = _legacy_file_field_for_slot(config, input_slot)
    if not file_field:
        return
    input_files = params.get("input_files") if isinstance(params.get("input_files"), dict) else {}
    runtime_path = f"input/{Path(str(file_record.filename)).name}"
    params["input_files"] = {**input_files, file_field: runtime_path}


def _legacy_file_field_for_slot(config: dict[str, Any], input_slot: dict[str, Any]) -> str | None:
    input_schema = config.get("input_schema") if isinstance(config.get("input_schema"), dict) else {}
    properties = input_schema.get("properties") if isinstance(input_schema.get("properties"), dict) else {}
    file_fields = [
        str(name)
        for name, schema in properties.items()
        if isinstance(schema, dict) and (schema.get("format") == "file" or schema.get("type") == "file")
    ]
    if not file_fields:
        return None
    slot_name = str(input_slot.get("name") or "")
    if slot_name in file_fields:
        return slot_name
    if len(file_fields) == 1:
        return file_fields[0]

    standard_type = str(input_slot.get("type") or "")
    if standard_type == "protein_structure@1":
        match = next((field for field in file_fields if "protein" in field or "receptor" in field), None)
        if match:
            return match
    if standard_type == "ligand_structure@1":
        match = next((field for field in file_fields if "ligand" in field), None)
        if match:
            return match
    return file_fields[0]


def _dedupe_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


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
    input_bindings = await _validate_standard_input_bindings(
        db,
        project_id=project_id,
        input_bindings=task_data.input_bindings,
    )
    if input_bindings:
        extra_data["input_bindings"] = input_bindings
    params = dict(task_data.params or {})
    file_ids = list(task_data.file_ids or [])
    binding_projection = await _project_standard_input_bindings(
        db,
        tool=tool,
        tool_version=tool_version,
        input_bindings=input_bindings,
        params=params,
        file_ids=file_ids,
    )
    params = binding_projection["params"]
    file_ids = binding_projection["file_ids"]
    if binding_projection["binding_decisions"]:
        extra_data["binding_decisions"] = binding_projection["binding_decisions"]

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
