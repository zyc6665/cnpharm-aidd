"""AIDD agent orchestration service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.aidd.capabilities import get_capability
from app.agents.aidd.outputs import extract_semantic_outputs
from app.agents.aidd.payloads import build_agent_task_payload
from app.agents.aidd.graph import build_plan_with_langgraph
from app.agents.aidd.planner import AIDDPlan, infer_aidd_input_type
from app.config import settings
from app.common.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.models.agent import AgentRun, AgentRunStep
from app.models.files import File as FileModel
from app.models.statistics import FileStatistics
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolStatus
from app.models.users import User
from app.schemas.agent import AIDDRunCreate
from app.schemas.tasks import TaskCreate
from app.tasks.service import create_and_schedule_tool_task


TERMINAL_RUN_STATUSES = {"success", "failure", "canceled"}


def _file_download_url(file_id: str) -> str:
    return f"/api/v1/files/{file_id}/download"


def _file_payload(file_record: FileModel) -> dict[str, str]:
    return {
        "file_id": str(file_record.id),
        "filename": file_record.filename,
        "download_url": _file_download_url(str(file_record.id)),
    }


def _input_filename(file_record: FileModel) -> str:
    metadata = file_record.file_meta or {}
    original_name = metadata.get("original_name")
    if isinstance(original_name, str) and original_name:
        return original_name
    return file_record.filename


async def _load_owned_file(
    db: AsyncSession,
    *,
    file_id: str,
    current_user: User,
) -> FileModel:
    file_record = await db.get(FileModel, file_id)
    if not file_record:
        raise NotFoundException("输入文件不存在")
    if file_record.owner_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException("无权使用此输入文件")
    return file_record


async def _load_available_tool(db: AsyncSession, tool_slug: str) -> Tool:
    result = await db.execute(
        select(Tool)
        .options(selectinload(Tool.current_version))
        .where(Tool.slug == tool_slug)
    )
    tool = result.scalar_one_or_none()
    if not tool:
        raise ValidationException(f"智能体工具未配置: {tool_slug}")
    if tool.status != ToolStatus.PUBLISHED.value or tool.is_public is not True:
        raise ValidationException(f"智能体工具不可用: {tool_slug}")
    if not tool.current_version:
        raise ValidationException(f"智能体工具没有可用版本: {tool_slug}")
    return tool


async def _load_run_for_user(
    db: AsyncSession,
    *,
    run_id: str,
    current_user: User,
) -> AgentRun:
    result = await db.execute(
        select(AgentRun)
        .options(selectinload(AgentRun.steps))
        .where(AgentRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise NotFoundException("智能体运行不存在")
    if run.user_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException("无权访问此智能体运行")
    return run


async def create_agent_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_data: AIDDRunCreate,
) -> AgentRun:
    input_file = await _load_owned_file(
        db,
        file_id=run_data.input_file_id,
        current_user=current_user,
    )
    if run_data.input_type and run_data.input_type not in {"protein_pdb", "pocket_pdb"}:
        raise ValidationException(f"Unsupported AIDD input_type: {run_data.input_type}")
    input_type = run_data.input_type or infer_aidd_input_type(
        message=run_data.message,
        filename=_input_filename(input_file),
    )

    plan, input_type = await build_plan_with_langgraph(
        db,
        message=run_data.message,
        input_file=input_file,
        requested_outputs=run_data.requested_outputs,
        params=run_data.params,
    )

    run = AgentRun(
        user_id=current_user.id,
        message=run_data.message,
        intent=plan.intent,
        status="planning",
        input_type=input_type,
        input_file_id=input_file.id,
        requested_outputs=plan.requested_outputs,
        plan=plan.model_dump(),
    )
    db.add(run)
    await db.flush()

    for index, plan_step in enumerate(plan.steps):
        db.add(
            AgentRunStep(
                agent_run_id=run.id,
                step_key=plan_step.step_key,
                tool_slug=plan_step.tool_slug,
                status="pending",
                sort_order=index,
                depends_on_step_ids=plan_step.depends_on,
                semantic_inputs=plan_step.inputs,
                params=plan_step.params,
            )
        )

    await db.commit()
    await start_ready_steps(db, current_user=current_user, run_id=run.id)
    return await _load_run_for_user(db, run_id=run.id, current_user=current_user)


def _dependencies_satisfied(step: AgentRunStep, steps_by_key: dict[str, AgentRunStep]) -> bool:
    for dependency_key in step.depends_on_step_ids or []:
        dependency = steps_by_key.get(dependency_key)
        if dependency is None or dependency.status != "success":
            return False
    return True


async def _resolve_semantic_files(
    db: AsyncSession,
    *,
    run: AgentRun,
    step: AgentRunStep,
    steps_by_key: dict[str, AgentRunStep],
) -> dict[str, dict[str, str]]:
    semantic_files: dict[str, dict[str, str]] = {}

    for semantic_type, source in (step.semantic_inputs or {}).items():
        if source == "agent_input":
            if not run.input_file_id:
                raise ValidationException("智能体运行缺少输入文件")
            file_record = await db.get(FileModel, run.input_file_id)
            if not file_record:
                raise NotFoundException("智能体输入文件不存在")
            semantic_files[semantic_type] = _file_payload(file_record)
            continue

        if isinstance(source, str) and source.startswith("step:"):
            _, dependency_key, dependency_semantic_type = source.split(":", 2)
            dependency = steps_by_key.get(dependency_key)
            if not dependency:
                raise ValidationException(f"依赖步骤不存在: {dependency_key}")
            dependency_output = (dependency.semantic_outputs or {}).get(dependency_semantic_type)
            if not dependency_output or not dependency_output.get("file_id"):
                raise ValidationException(f"依赖步骤缺少产物: {dependency_semantic_type}")
            semantic_files[semantic_type] = {
                "file_id": str(dependency_output["file_id"]),
                "filename": str(dependency_output.get("filename") or dependency_output["file_id"]),
                "download_url": str(
                    dependency_output.get("url")
                    or _file_download_url(str(dependency_output["file_id"]))
                ),
            }
            continue

        raise ValidationException(f"不支持的智能体输入来源: {source}")

    return semantic_files


async def _schedule_step(
    db: AsyncSession,
    *,
    current_user: User,
    run: AgentRun,
    step: AgentRunStep,
    steps_by_key: dict[str, AgentRunStep],
) -> None:
    capability = get_capability(step.tool_slug)
    tool = await _load_available_tool(db, step.tool_slug)
    semantic_files = await _resolve_semantic_files(
        db,
        run=run,
        step=step,
        steps_by_key=steps_by_key,
    )
    executor_type = str(tool.current_version.config.get("type", ""))
    payload = build_agent_task_payload(
        capability=capability,
        executor_type=executor_type,
        semantic_files=semantic_files,
        step_params=step.params or {},
    )

    task = await create_and_schedule_tool_task(
        db=db,
        current_user=current_user,
        task_data=TaskCreate(
            name=f"AIDD {run.intent} - {step.step_key}",
            tool_id=tool.id,
            params=payload.params,
            file_ids=payload.file_ids,
        ),
    )

    step.tool_id = tool.id
    step.task_id = task.id
    step.status = "waiting_task"
    step.input_file_ids = payload.file_ids
    step.params = payload.params
    step.started_at = datetime.utcnow()


async def start_ready_steps(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> int:
    run = await _load_run_for_user(db, run_id=run_id, current_user=current_user)
    steps_by_key = {step.step_key: step for step in run.steps}
    scheduled_count = 0

    for step in sorted(run.steps, key=lambda item: item.sort_order):
        if step.status not in {"pending", "ready"}:
            continue
        if not _dependencies_satisfied(step, steps_by_key):
            continue

        try:
            await _schedule_step(
                db,
                current_user=current_user,
                run=run,
                step=step,
                steps_by_key=steps_by_key,
            )
        except Exception as exc:
            step.status = "failure"
            step.error_message = str(exc)
            run.status = "failure"
            run.error_message = str(exc)
            run.finished_at = datetime.utcnow()
            await db.commit()
            raise

        scheduled_count += 1
        run.status = "waiting_task"
        # First version schedules newly ready work one wave at a time.
        break

    if scheduled_count == 0 and run.status == "planning":
        run.status = "pending"

    await db.commit()
    return scheduled_count


async def get_agent_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> AgentRun:
    return await _load_run_for_user(db, run_id=run_id, current_user=current_user)


async def list_agent_runs(
    db: AsyncSession,
    *,
    current_user: User,
) -> list[AgentRun]:
    query = (
        select(AgentRun)
        .options(selectinload(AgentRun.steps))
        .order_by(AgentRun.created_at.desc())
    )
    if current_user.role != "admin":
        query = query.where(AgentRun.user_id == current_user.id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def cancel_agent_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> AgentRun:
    run = await _load_run_for_user(db, run_id=run_id, current_user=current_user)
    if run.status not in TERMINAL_RUN_STATUSES:
        run.status = "canceled"
        run.finished_at = datetime.utcnow()
        for step in run.steps:
            if step.status in {"pending", "ready", "waiting_task", "running"}:
                step.status = "canceled"
                step.finished_at = datetime.utcnow()
        await db.commit()
    return await _load_run_for_user(db, run_id=run.id, current_user=current_user)


async def delete_agent_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> dict[str, Any]:
    run = await _load_run_for_user(db, run_id=run_id, current_user=current_user)
    deleted_id = run.id
    await db.delete(run)
    await db.commit()
    return {
        "id": deleted_id,
        "deleted_tasks": 0,
        "deleted_artifacts": 0,
    }


def _collect_file_ids_from_value(value: Any) -> set[str]:
    file_ids: set[str] = set()
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key in {"file_id", "id"} and isinstance(nested_value, str):
                file_ids.add(nested_value)
            elif key in {"file_ids", "files"} and isinstance(nested_value, list):
                for item in nested_value:
                    if isinstance(item, str):
                        file_ids.add(item)
                    else:
                        file_ids.update(_collect_file_ids_from_value(item))
            else:
                file_ids.update(_collect_file_ids_from_value(nested_value))
    elif isinstance(value, list):
        for item in value:
            file_ids.update(_collect_file_ids_from_value(item))
    return file_ids


async def _delete_file_records(db: AsyncSession, file_ids: set[str]) -> int:
    if not file_ids:
        return 0

    result = await db.execute(select(FileModel).where(FileModel.id.in_(file_ids)))
    files = list(result.scalars().all())
    if not files:
        return 0

    existing_ids = {file.id for file in files}
    await db.execute(delete(FileStatistics).where(FileStatistics.file_id.in_(existing_ids)))

    deleted_count = 0
    storage_root = Path(settings.STORAGE_PATH).resolve()
    for file in files:
        if file.storage_path:
            path = Path(file.storage_path)
            resolved_path = path.resolve()
            if (
                resolved_path.exists()
                and resolved_path.is_file()
                and resolved_path.is_relative_to(storage_root)
            ):
                resolved_path.unlink()
        await db.delete(file)
        deleted_count += 1

    return deleted_count


async def cascade_delete_agent_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_id: str,
) -> dict[str, Any]:
    run = await _load_run_for_user(db, run_id=run_id, current_user=current_user)
    deleted_id = run.id
    task_ids = {step.task_id for step in run.steps if step.task_id}
    artifact_file_ids: set[str] = set()

    for step in run.steps:
        artifact_file_ids.update(str(file_id) for file_id in (step.output_file_ids or []) if file_id)
        semantic_outputs = step.semantic_outputs or {}
        artifact_file_ids.update(_collect_file_ids_from_value(semantic_outputs))

    tasks: list[Task] = []
    if task_ids:
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.outputs))
            .where(Task.id.in_(task_ids))
        )
        tasks = list(result.scalars().all())
        for task in tasks:
            if task.outputs:
                artifact_file_ids.update(str(file_id) for file_id in (task.outputs.file_ids or []) if file_id)
                artifact_file_ids.update(_collect_file_ids_from_value(task.outputs.result or {}))

    await db.delete(run)
    for task in tasks:
        await db.delete(task)

    deleted_artifacts = await _delete_file_records(db, artifact_file_ids)
    await db.commit()

    return {
        "id": deleted_id,
        "deleted_tasks": len(tasks),
        "deleted_artifacts": deleted_artifacts,
    }


async def _load_task_output_files(
    db: AsyncSession,
    file_ids: list[str],
) -> list[dict[str, Any]]:
    if not file_ids:
        return []

    result = await db.execute(select(FileModel).where(FileModel.id.in_(file_ids)))
    files_by_id = {file.id: file for file in result.scalars().all()}
    output_files: list[dict[str, Any]] = []

    for file_id in file_ids:
        file_record = files_by_id.get(str(file_id))
        if not file_record:
            continue
        output_files.append(
            {
                "id": file_record.id,
                "filename": file_record.filename,
                "content_type": file_record.content_type,
                "url": _file_download_url(file_record.id),
            }
        )

    return output_files


def _required_outputs_present(
    *,
    tool_slug: str,
    semantic_outputs: dict[str, dict[str, Any]],
) -> bool:
    capability = get_capability(tool_slug)
    return all(output.semantic_type in semantic_outputs for output in capability.outputs)


async def _mark_run_success_if_complete(db: AsyncSession, run: AgentRun) -> None:
    if run.steps and all(step.status == "success" for step in run.steps):
        run.status = "success"
        run.finished_at = datetime.utcnow()
        await db.commit()


async def reconcile_waiting_agent_steps(
    db: AsyncSession,
    *,
    run_id: str | None = None,
) -> int:
    """Reconcile waiting agent steps with their linked platform task status."""
    query = (
        select(AgentRunStep)
        .options(
            selectinload(AgentRunStep.run).selectinload(AgentRun.steps),
            selectinload(AgentRunStep.task).selectinload(Task.outputs),
        )
        .where(AgentRunStep.status == "waiting_task")
    )
    if run_id:
        query = query.where(AgentRunStep.agent_run_id == run_id)

    result = await db.execute(query)
    steps = list(result.scalars().all())
    processed_count = 0

    for step in steps:
        task = step.task
        run = step.run
        if not task:
            step.status = "failure"
            step.error_message = "关联任务不存在"
            run.status = "failure"
            run.error_message = step.error_message
            run.finished_at = datetime.utcnow()
            processed_count += 1
            continue

        if task.status in {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}:
            continue

        processed_count += 1
        if task.status in {TaskStatus.FAILURE.value, TaskStatus.CANCELED.value}:
            step.status = "failure"
            step.error_message = task.error_message or "任务执行失败"
            step.finished_at = datetime.utcnow()
            run.status = "failure"
            run.error_message = step.error_message
            run.finished_at = datetime.utcnow()
            continue

        file_ids = [str(file_id) for file_id in (task.outputs.file_ids if task.outputs else [])]
        output_files = await _load_task_output_files(db, file_ids)
        output_data = task.outputs.result if task.outputs else None
        semantic_outputs = extract_semantic_outputs(
            capability=get_capability(step.tool_slug),
            task_output_files=output_files,
            output_data=output_data,
        )

        if not _required_outputs_present(tool_slug=step.tool_slug, semantic_outputs=semantic_outputs):
            step.status = "failure"
            step.error_message = "任务成功但缺少智能体所需语义产物"
            step.finished_at = datetime.utcnow()
            run.status = "failure"
            run.error_message = step.error_message
            run.finished_at = datetime.utcnow()
            continue

        step.status = "success"
        step.semantic_outputs = semantic_outputs
        step.output_file_ids = [
            str(value["file_id"])
            for value in semantic_outputs.values()
            if value.get("source") == "output_files" and value.get("file_id")
        ]
        step.finished_at = datetime.utcnow()

        await db.commit()
        user = await db.get(User, run.user_id)
        if user:
            await start_ready_steps(db, current_user=user, run_id=run.id)
            refreshed_run = await _load_run_for_user(db, run_id=run.id, current_user=user)
            await _mark_run_success_if_complete(db, refreshed_run)

    await db.commit()
    return processed_count
