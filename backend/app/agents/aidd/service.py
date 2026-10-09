"""AIDD agent orchestration service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.time import utcnow
from app.agents.aidd.capabilities import AIDD_TOOL_CAPABILITIES, ToolCapability
from app.agents.aidd.input_classifier import classify_aidd_input_file
from app.agents.aidd.outputs import extract_semantic_outputs
from app.agents.aidd.payloads import build_agent_task_payload
from app.agents.aidd.graph import build_plan_with_langgraph
from app.agents.aidd.planner import AIDDPlan, infer_aidd_input_type
from app.agents.aidd.registry import (
    capability_from_tool,
    load_available_tool_summaries,
    load_tool_capability,
)
from app.config import settings
from app.common.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.models.agent import AgentRun, AgentRunStep
from app.models.files import File as FileModel
from app.models.statistics import FileStatistics
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolStatus
from app.models.users import User
from app.schemas.agent import AIDDRunCreate
from app.schemas.agent import AIDDWorkflowDraftResponse
from app.schemas.tasks import TaskCreate
from app.artifact_standards.types import normalize_platform_artifact_type
from app.services.semantic_types import CANONICAL_AGENT_INPUT_TYPES, normalize_semantic_type
from app.services.aidd_builtin_tools import ensure_aidd_builtin_tool
from app.files.writer import store_file_bytes
from app.files.file_records import delete_stored_content
from app.services.tool_contracts import build_tool_contract, tool_contract_to_agent_summary
from app.services.workflow_artifacts import (
    describe_missing_required_standard_artifacts,
    extract_standard_artifacts,
    format_missing_required_standard_artifacts_error,
    required_standard_artifacts_present,
    standard_artifact_file_ids,
    load_task_output_files,
)
from app.agents.aidd.workflow_drafts import build_workflow_definition_from_plan
from app.tasks.service import create_and_schedule_tool_task
from app.tasks.cancellation import cancel_platform_task


TERMINAL_RUN_STATUSES = {"success", "failure", "canceled"}
SUPPORTED_AGENT_INPUT_TYPES = CANONICAL_AGENT_INPUT_TYPES | frozenset(
    normalize_platform_artifact_type(input_type)
    for input_type in CANONICAL_AGENT_INPUT_TYPES
)


@dataclass(frozen=True)
class PreparedAgentPlan:
    """Side-effect-free inputs and contracts shared by run and draft creation."""

    plan: AIDDPlan
    input_files: dict[str, FileModel]
    input_file: FileModel
    input_type: str
    plan_data: dict[str, Any]


def _normalize_agent_input_type(value: str | None) -> str | None:
    if not value:
        return value
    return normalize_platform_artifact_type(normalize_semantic_type(value))


def _normalize_semantic_file_map(input_files: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for semantic_type, file_id in input_files.items():
        canonical_type = _normalize_agent_input_type(str(semantic_type)) or str(semantic_type)
        if canonical_type in normalized and normalized[canonical_type] != file_id:
            raise ValidationException(
                f"Duplicate AIDD input semantic type after normalization: {canonical_type}"
            )
        normalized[canonical_type] = file_id
    return normalized


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


def _run_input_files(run: AgentRun) -> dict[str, str]:
    plan = run.plan or {}
    input_files = plan.get("input_files")
    if isinstance(input_files, dict):
        return _normalize_semantic_file_map({
            str(semantic_type): str(file_id)
            for semantic_type, file_id in input_files.items()
            if isinstance(semantic_type, str) and file_id
        })
    if run.input_file_id and run.input_type:
        return {str(_normalize_agent_input_type(run.input_type)): str(run.input_file_id)}
    return {}


def _summary_slug(tool_summary: dict[str, Any]) -> str:
    return str(tool_summary.get("slug") or tool_summary.get("tool_slug") or "")


def _build_step_contract_traces(
    *,
    plan: AIDDPlan,
    available_tools: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    tools_by_slug = {
        slug: tool_summary
        for tool_summary in available_tools
        if (slug := _summary_slug(tool_summary))
    }
    traces: dict[str, dict[str, Any]] = {}

    for plan_step in plan.steps:
        tool_summary = tools_by_slug.get(plan_step.tool_slug)
        if not tool_summary:
            continue
        slug = _summary_slug(tool_summary)
        traces[plan_step.step_key] = {
            "id": tool_summary.get("id"),
            "slug": slug,
            "tool_slug": slug,
            "name": tool_summary.get("name") or slug,
            "capability": tool_summary.get("capability"),
            "stage": tool_summary.get("stage"),
            "contract_version": tool_summary.get("contract_version"),
            "tool_version": tool_summary.get("tool_version"),
            "semantic_inputs": dict(plan_step.inputs or {}),
            "input_bindings": list(tool_summary.get("input_bindings") or []),
            "output_rules": list(tool_summary.get("output_rules") or []),
            "executor": dict(tool_summary.get("executor") or {}),
            "virtual": bool(tool_summary.get("virtual")),
        }

    return traces


async def _create_agent_output_file(
    db: AsyncSession,
    *,
    owner_id: str,
    filename: str,
    content: bytes,
    content_type: str,
    source_file_id: str | None = None,
) -> FileModel:
    return await store_file_bytes(
        db,
        content=content,
        filename=filename,
        content_type=content_type,
        source_type="tool_output",
        owner_id=owner_id,
        file_meta={"generated_by": "aidd_agent", "source_file_id": source_file_id},
    )


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
    capability = AIDD_TOOL_CAPABILITIES.get(tool_slug)
    if capability and capability.virtual:
        if not settings.AIDD_SYSTEM_USER_ID:
            raise ValidationException("AIDD_SYSTEM_USER_ID 未配置，无法执行内置智能体工具")
        return await ensure_aidd_builtin_tool(
            db,
            owner_id=settings.AIDD_SYSTEM_USER_ID,
            tool_slug=tool_slug,
        )

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
    if tool.current_version.is_active is not True or tool.current_version.deprecated is True:
        raise ValidationException(f"智能体工具当前版本不可用: {tool_slug}")
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


async def _load_agent_input_files(
    db: AsyncSession,
    *,
    current_user: User,
    run_data: AIDDRunCreate,
) -> tuple[dict[str, FileModel], FileModel, str, dict[str, dict[str, Any]]]:
    requested_input_files = _normalize_semantic_file_map(dict(run_data.input_files or {}))
    input_file_ids = list(run_data.input_file_ids or [])
    primary_file: FileModel | None = None

    if run_data.input_file_id:
        primary_file = await _load_owned_file(
            db,
            file_id=run_data.input_file_id,
            current_user=current_user,
        )
        inferred_type = infer_aidd_input_type(
            message=run_data.message,
            filename=_input_filename(primary_file),
        )
        primary_type = (
            _normalize_agent_input_type(run_data.input_type)
            or _normalize_agent_input_type(inferred_type)
            or inferred_type
        )
        requested_input_files.setdefault(primary_type, run_data.input_file_id)
        if run_data.input_file_id not in input_file_ids:
            input_file_ids.insert(0, run_data.input_file_id)

    for file_id in input_file_ids:
        if file_id not in requested_input_files.values():
            await _load_owned_file(
                db,
                file_id=file_id,
                current_user=current_user,
            )

    if not requested_input_files:
        if not input_file_ids:
            raise ValidationException("请至少提供一个智能体输入文件")

    semantic_files: dict[str, FileModel] = {}
    for semantic_type, file_id in requested_input_files.items():
        if semantic_type not in SUPPORTED_AGENT_INPUT_TYPES:
            raise ValidationException(f"Unsupported AIDD input semantic type: {semantic_type}")
        semantic_files[semantic_type] = await _load_owned_file(
            db,
            file_id=file_id,
            current_user=current_user,
        )

    classified_files: dict[str, dict[str, Any]] = {}
    used_semantic_types = set(semantic_files.keys())
    for file_id in input_file_ids:
        if file_id in requested_input_files.values():
            continue
        file_record = await _load_owned_file(db, file_id=file_id, current_user=current_user)
        classified = await classify_aidd_input_file(
            file_record,
            message=run_data.message,
            used_semantic_types=used_semantic_types,
        )
        classified_semantic_type = (
            _normalize_agent_input_type(classified.semantic_type) or classified.semantic_type
        )
        semantic_files.setdefault(classified_semantic_type, file_record)
        used_semantic_types.add(classified_semantic_type)
        classified_files[file_record.id] = {
            "semantic_type": classified_semantic_type,
            "confidence": classified.confidence,
            "reason": classified.reason,
        }

    if primary_file is None:
        requested_input_type = _normalize_agent_input_type(run_data.input_type)
        primary_semantic_type = (
            requested_input_type
            if requested_input_type in semantic_files
            else next(iter(semantic_files.keys()))
        )
        primary_file = semantic_files[primary_semantic_type]
    else:
        fallback_type = infer_aidd_input_type(
            message=run_data.message,
            filename=_input_filename(primary_file),
        )
        primary_semantic_type = next(
            (
                semantic_type
                for semantic_type, file_record in semantic_files.items()
                if file_record.id == primary_file.id
            ),
            _normalize_agent_input_type(run_data.input_type)
            or _normalize_agent_input_type(fallback_type)
            or fallback_type,
        )

    return semantic_files, primary_file, str(primary_semantic_type), classified_files


async def create_agent_run(
    db: AsyncSession,
    *,
    current_user: User,
    run_data: AIDDRunCreate,
) -> AgentRun:
    prepared = await _prepare_agent_plan(
        db,
        current_user=current_user,
        run_data=run_data,
    )
    plan = prepared.plan

    run = AgentRun(
        user_id=current_user.id,
        message=run_data.message,
        intent=plan.intent,
        status="planning",
        input_type=prepared.input_type,
        input_file_id=prepared.input_file.id,
        requested_outputs=plan.requested_outputs,
        plan=prepared.plan_data,
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


async def _prepare_agent_plan(
    db: AsyncSession,
    *,
    current_user: User,
    run_data: AIDDRunCreate,
) -> PreparedAgentPlan:
    input_type = _normalize_agent_input_type(run_data.input_type)
    if input_type and input_type not in SUPPORTED_AGENT_INPUT_TYPES:
        raise ValidationException(f"Unsupported AIDD input_type: {run_data.input_type}")
    input_files, input_file, input_type, classified_files = await _load_agent_input_files(
        db,
        current_user=current_user,
        run_data=run_data,
    )
    plan_params = {
        **run_data.params,
        "available_inputs": sorted(input_files.keys()),
    }

    plan, input_type = await build_plan_with_langgraph(
        db,
        message=run_data.message,
        input_file=input_file,
        input_files=input_files,
        input_type=input_type,
        requested_outputs=[normalize_semantic_type(output) for output in run_data.requested_outputs],
        params=plan_params,
    )
    available_tool_summaries = await load_available_tool_summaries(db)
    plan_data = plan.model_dump()
    plan_data["input_files"] = {
        semantic_type: file_record.id for semantic_type, file_record in input_files.items()
    }
    plan_data["step_contracts"] = _build_step_contract_traces(
        plan=plan,
        available_tools=available_tool_summaries,
    )
    if classified_files:
        plan_data["classified_input_files"] = classified_files

    return PreparedAgentPlan(
        plan=plan,
        input_files=input_files,
        input_file=input_file,
        input_type=input_type,
        plan_data=plan_data,
    )


async def create_workflow_draft(
    db: AsyncSession,
    *,
    current_user: User,
    run_data: AIDDRunCreate,
) -> AIDDWorkflowDraftResponse:
    """Generate an editable workflow draft without creating a run or task."""
    prepared = await _prepare_agent_plan(
        db,
        current_user=current_user,
        run_data=run_data,
    )
    resolved_contracts: dict[str, dict[str, Any]] = {}
    for step in prepared.plan.steps:
        tool = await _load_available_tool(db, step.tool_slug)
        capability = await load_tool_capability(db, step.tool_slug)
        resolved_contracts[step.step_key] = tool_contract_to_agent_summary(
            build_tool_contract(tool, capability=capability)
        )

    input_file_ids = {
        semantic_type: str(file_record.id)
        for semantic_type, file_record in prepared.input_files.items()
    }
    definition = build_workflow_definition_from_plan(
        plan=prepared.plan,
        input_files=input_file_ids,
        step_contracts=resolved_contracts,
    )
    message = run_data.message.strip()
    return AIDDWorkflowDraftResponse(
        name=message[:160],
        description=prepared.plan.reasoning_summary or message,
        intent=prepared.plan.intent,
        definition=definition,
        input_files=input_file_ids,
        requested_outputs=list(prepared.plan.requested_outputs),
        reasoning_summary=prepared.plan.reasoning_summary,
        analysis_trace=list(prepared.plan.analysis_trace),
    )


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
    run_input_files = _run_input_files(run)

    for semantic_type, source in (step.semantic_inputs or {}).items():
        if source == "agent_input" or (
            isinstance(source, str) and source.startswith("agent_input:")
        ):
            semantic_key = semantic_type
            if isinstance(source, str) and source.startswith("agent_input:"):
                semantic_key = (
                    _normalize_agent_input_type(source.split(":", 1)[1] or semantic_type)
                    or semantic_type
                )
            file_id = run_input_files.get(semantic_key) or run.input_file_id
            if not file_id:
                raise ValidationException("智能体运行缺少输入文件")
            file_record = await db.get(FileModel, file_id)
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
                source_task = f", source_task={dependency.task_id}" if dependency.task_id else ""
                raise ValidationException(
                    "依赖步骤缺少产物: "
                    f"required={semantic_type}, source_step={dependency_key}, "
                    f"source_output={dependency_semantic_type}{source_task}"
                )
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
    tool = await _load_available_tool(db, step.tool_slug)
    capability = capability_from_tool(tool)
    if capability is None:
        raise ValidationException(f"智能体工具缺少 agent_capability 配置: {step.tool_slug}")
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
            project_id=run.project_id,
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
    step.started_at = utcnow()


async def claim_agent_step_for_dispatch(db: AsyncSession, step_id: str) -> bool:
    """Atomically reserve a ready step for one scheduler instance."""
    result = await db.execute(
        update(AgentRunStep)
        .where(
            AgentRunStep.id == step_id,
            AgentRunStep.status.in_(("pending", "ready")),
        )
        .values(status="dispatching")
    )
    await db.commit()
    return result.rowcount == 1


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
        if not await claim_agent_step_for_dispatch(db, step.id):
            continue
        await db.refresh(step)

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
            run.finished_at = utcnow()
            await db.commit()
            raise

        scheduled_count += 1
        steps_by_key[step.step_key] = step
        run.status = "waiting_task"
        # Platform tasks are scheduled one wave at a time.
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
    project_only: bool = False,
) -> list[AgentRun]:
    query = (
        select(AgentRun)
        .options(selectinload(AgentRun.steps))
        .order_by(AgentRun.created_at.desc())
    )
    if current_user.role != "admin":
        query = query.where(AgentRun.user_id == current_user.id)
    if project_only:
        query = query.where(AgentRun.project_id.is_not(None))
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
        for step in run.steps:
            if step.task_id:
                task = await db.get(Task, step.task_id)
                if task:
                    await cancel_platform_task(db, task=task, current_user=current_user)
        run.status = "canceled"
        run.finished_at = utcnow()
        for step in run.steps:
            if step.status in {"pending", "ready", "dispatching", "waiting_task", "running"}:
                step.status = "canceled"
                step.finished_at = utcnow()
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
            if file.storage_backend == "minio":
                await delete_stored_content(file)
            else:
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


def _required_outputs_present(
    *,
    capability: ToolCapability,
    semantic_outputs: dict[str, dict[str, Any]],
) -> bool:
    return all(
        output.semantic_type in semantic_outputs
        for output in capability.outputs
        if output.required and output.source != "artifact"
    )


def _format_output_rule(output: Any) -> str:
    parts = [
        f"semantic_type={getattr(output, 'semantic_type', '')}",
        f"source={getattr(output, 'source', '')}",
    ]
    if getattr(output, "path", None):
        parts.append(f"path={output.path}")

    match = getattr(output, "match", None)
    if match:
        match_parts: list[str] = []
        if getattr(match, "extension", None):
            match_parts.append(f"extension={match.extension}")
        if getattr(match, "filename_contains_any", None):
            tokens = ",".join(str(token) for token in match.filename_contains_any)
            match_parts.append(f"filename_contains_any={tokens}")
        if getattr(match, "content_type", None):
            match_parts.append(f"content_type={match.content_type}")
        if match_parts:
            parts.append("match=(" + "; ".join(match_parts) + ")")

    return ", ".join(parts)


def _missing_required_output_descriptions(
    *,
    capability: ToolCapability,
    semantic_outputs: dict[str, dict[str, Any]],
) -> list[str]:
    return [
        _format_output_rule(output)
        for output in capability.outputs
        if output.required
        and output.source != "artifact"
        and output.semantic_type not in semantic_outputs
    ]


def _declared_artifact_outputs(capability: ToolCapability) -> list[dict[str, Any]]:
    return [
        {
            "name": output.path or output.semantic_type,
            "type": output.semantic_type,
            "required": output.required,
        }
        for output in capability.outputs
        if output.source == "artifact"
    ]


def _missing_required_outputs_message(
    *,
    capability: ToolCapability,
    semantic_outputs: dict[str, dict[str, Any]],
    step: AgentRunStep,
) -> str:
    missing_rules = _missing_required_output_descriptions(
        capability=capability,
        semantic_outputs=semantic_outputs,
    )
    detail = "; ".join(missing_rules) if missing_rules else "未知必需输出"
    return (
        "任务成功但缺少智能体所需语义产物: "
        f"tool={step.tool_slug}, capability={capability.capability}, "
        f"step={step.step_key}, missing=[{detail}]"
    )


async def _mark_run_success_if_complete(db: AsyncSession, run: AgentRun) -> None:
    if run.steps and all(step.status == "success" for step in run.steps):
        run.status = "success"
        run.finished_at = utcnow()
        await db.commit()


async def _try_replan_failed_step_with_uploaded_inputs(
    db: AsyncSession,
    *,
    run: AgentRun,
    failed_step: AgentRunStep,
    error_message: str,
) -> bool:
    uploaded_inputs = _run_input_files(run)
    if not uploaded_inputs:
        return False

    changed = False
    for downstream in run.steps:
        if downstream.status not in {"pending", "ready"}:
            continue

        semantic_inputs = dict(downstream.semantic_inputs or {})
        rewritten_inputs: dict[str, str] = {}
        step_changed = False

        for semantic_type, source in semantic_inputs.items():
            if not isinstance(source, str) or not source.startswith("step:"):
                rewritten_inputs[semantic_type] = source
                continue

            _, dependency_key, _dependency_semantic_type = source.split(":", 2)
            normalized_semantic_type = _normalize_agent_input_type(semantic_type) or semantic_type
            if (
                dependency_key != failed_step.step_key
                or (
                    semantic_type not in uploaded_inputs
                    and normalized_semantic_type not in uploaded_inputs
                )
            ):
                rewritten_inputs[semantic_type] = source
                continue

            rewritten_inputs[semantic_type] = f"agent_input:{semantic_type}"
            step_changed = True

        if not step_changed:
            continue

        downstream.semantic_inputs = rewritten_inputs
        downstream.depends_on_step_ids = [
            dependency_key
            for dependency_key in (downstream.depends_on_step_ids or [])
            if dependency_key != failed_step.step_key
        ]
        downstream.status = "pending"
        changed = True

    if not changed:
        return False

    failed_step.status = "skipped"
    failed_step.error_message = f"上游任务失败，已改用上传文件继续: {error_message}"
    failed_step.finished_at = utcnow()
    run.status = "pending"
    run.error_message = None
    await db.commit()

    user = await db.get(User, run.user_id)
    if user:
        await start_ready_steps(db, current_user=user, run_id=run.id)
    return True


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
            run.finished_at = utcnow()
            processed_count += 1
            continue

        if task.status in {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}:
            continue

        processed_count += 1
        if task.status in {TaskStatus.FAILURE.value, TaskStatus.CANCELED.value}:
            error_message = task.error_message or "任务执行失败"
            if await _try_replan_failed_step_with_uploaded_inputs(
                db,
                run=run,
                failed_step=step,
                error_message=error_message,
            ):
                continue
            step.status = "failure"
            step.error_message = error_message
            step.finished_at = utcnow()
            run.status = "failure"
            run.error_message = step.error_message
            run.finished_at = utcnow()
            continue

        file_ids = [str(file_id) for file_id in (task.outputs.file_ids if task.outputs else [])]
        output_files = await load_task_output_files(db, file_ids)
        output_data = task.outputs.result if task.outputs else None
        capability = await load_tool_capability(db, step.tool_slug)
        semantic_outputs = extract_semantic_outputs(
            capability=capability,
            task_output_files=output_files,
            output_data=output_data,
        )
        standard_artifacts = extract_standard_artifacts(output_data)

        if not _required_outputs_present(capability=capability, semantic_outputs=semantic_outputs):
            error_message = _missing_required_outputs_message(
                capability=capability,
                semantic_outputs=semantic_outputs,
                step=step,
            )
            if await _try_replan_failed_step_with_uploaded_inputs(
                db,
                run=run,
                failed_step=step,
                error_message=error_message,
            ):
                continue
            step.status = "failure"
            step.error_message = error_message
            step.finished_at = utcnow()
            run.status = "failure"
            run.error_message = step.error_message
            run.finished_at = utcnow()
            continue

        declared_artifact_outputs = _declared_artifact_outputs(capability)
        if not required_standard_artifacts_present(
            declared_outputs=declared_artifact_outputs,
            standard_artifacts=standard_artifacts,
        ):
            missing_artifacts = describe_missing_required_standard_artifacts(
                declared_outputs=declared_artifact_outputs,
                standard_artifacts=standard_artifacts,
            )
            error_message = format_missing_required_standard_artifacts_error(missing_artifacts)
            if await _try_replan_failed_step_with_uploaded_inputs(
                db,
                run=run,
                failed_step=step,
                error_message=error_message,
            ):
                continue
            step.status = "failure"
            step.error_message = error_message
            step.finished_at = utcnow()
            run.status = "failure"
            run.error_message = step.error_message
            run.finished_at = utcnow()
            continue

        step.status = "success"
        step.semantic_outputs = semantic_outputs
        output_file_ids = [
            str(value["file_id"])
            for value in semantic_outputs.values()
            if value.get("source") == "output_files" and value.get("file_id")
        ]
        for declaration in declared_artifact_outputs:
            output_file_ids.extend(
                standard_artifact_file_ids(standard_artifacts, str(declaration["name"]))
            )
        step.output_file_ids = list(dict.fromkeys(output_file_ids))
        step.finished_at = utcnow()

        await db.commit()
        user = await db.get(User, run.user_id)
        if user:
            await start_ready_steps(db, current_user=user, run_id=run.id)
            refreshed_run = await _load_run_for_user(db, run_id=run.id, current_user=user)
            await _mark_run_success_if_complete(db, refreshed_run)

    await db.commit()
    return processed_count
