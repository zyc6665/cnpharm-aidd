# backend/app/api/v1/tasks.py
"""任务管理API"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Any, Optional

from app.database.session import get_db
from app.models.files import File as FileModel
from app.models.users import User
from app.models.tools import Tool, ToolVersion
from app.models.tasks import Task, TaskLog, TaskStatus
from app.tasks.cancellation import cancel_platform_task
from app.tasks.direct_runner import direct_task_runner
from app.tasks.service import (
    create_and_schedule_tool_task,
    dispatch_tool_task,
    prepare_tool_task_preview,
    record_tool_usage,
)
from app.tasks.naming import (
    resolve_task_display_name as _resolve_task_display_name,
    _dedupe_file_ids,
    _extract_file_ids_from_result,
)
from app.auth.dependencies import get_current_user, get_admin_user
from app.schemas.tasks import (
    TaskCreate, TaskListResponse
)
from app.common.responses import paginated_response, success_response
from app.common.exceptions import NotFoundException, ForbiddenException, ValidationException
from app.services.project_access import load_project_membership, require_project_role
from app.services.task_views import TaskQueryInput, query_task_page, query_task_view_counts

logger = logging.getLogger(__name__)
router = APIRouter()
TASK_OPERATION_PROJECT_ROLES = {"owner", "editor", "runner"}


def _normalize_task_status(status: Optional[str]) -> Optional[str]:
    if not status:
        return status
    return status.lower()


def _extract_primary_output_data(result: Any) -> Any:
    if not isinstance(result, dict):
        return result

    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        return nested_result

    return result


_MAX_FAILURE_STREAM_LENGTH = 4000
_STANDARD_ARTIFACT_ERROR_MARKERS = (
    "required standard artifacts",
    "missing required output artifact",
    "result manifest",
    "standard artifact persistence",
)


def _normalize_diagnostic_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if len(text) <= _MAX_FAILURE_STREAM_LENGTH:
        return text
    return f"{text[:_MAX_FAILURE_STREAM_LENGTH]}..."


def _read_diagnostic_field(source: Any, key: str, *, depth: int = 0) -> str:
    if not isinstance(source, dict) or depth > 2:
        return ""

    direct = _normalize_diagnostic_text(source.get(key))
    if direct:
        return direct

    from_details = _read_diagnostic_field(source.get("details"), key, depth=depth + 1)
    if from_details:
        return from_details

    return _read_diagnostic_field(source.get("result"), key, depth=depth + 1)


def _standard_artifact_failure_message(messages: list[str]) -> str:
    for message in messages:
        lowered = message.lower()
        if any(marker in lowered for marker in _STANDARD_ARTIFACT_ERROR_MARKERS):
            return message
        if "standard artifact" in lowered and ("missing" in lowered or "required" in lowered):
            return message
    return ""


def _task_failure_diagnostics(task: Task) -> dict[str, str] | None:
    if _normalize_task_status(task.status) != "failure":
        return None

    result = task.outputs.result if task.outputs else None
    output_data = _extract_primary_output_data(result)
    error_message = _normalize_diagnostic_text(task.error_message)
    stdout = _read_diagnostic_field(result, "stdout") or _read_diagnostic_field(output_data, "stdout")
    stderr = _read_diagnostic_field(result, "stderr") or _read_diagnostic_field(output_data, "stderr")
    standard_artifact_message = _standard_artifact_failure_message(
        [error_message, stderr, stdout]
    )

    if not any([error_message, stdout, stderr, standard_artifact_message]):
        return None

    return {
        "error_message": error_message,
        "stdout": stdout,
        "stderr": stderr,
        "standard_artifact_message": standard_artifact_message,
    }


def _task_project_id(task: Task) -> Optional[str]:
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    project_id = data.get("project_id")
    return str(project_id) if project_id else None


def _task_input_bindings(task: Task) -> dict[str, str]:
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    bindings = data.get("input_bindings")
    if not isinstance(bindings, dict):
        return {}
    return {
        str(input_name): str(version_id)
        for input_name, version_id in bindings.items()
        if input_name and version_id
    }


def _task_binding_decisions(task: Task) -> dict[str, Any]:
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    decisions = data.get("binding_decisions")
    return decisions if isinstance(decisions, dict) else {}


def _serialize_task_log(log: TaskLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "task_id": log.task_id,
        "timestamp": log.timestamp,
        "level": (log.level or "INFO").lower(),
        "message": log.message,
        "metadata": log.log_data or {},
    }


async def _load_files(db: AsyncSession, file_ids: list[str]) -> list[dict[str, Any]]:
    if not file_ids:
        return []

    result = await db.execute(
        select(FileModel).where(FileModel.id.in_(file_ids))
    )
    files = {file.id: file for file in result.scalars().all()}

    serialized: list[dict[str, Any]] = []
    for file_id in file_ids:
        file = files.get(file_id)
        if not file:
            logger.warning("Task detail references missing file id %s", file_id)
            continue

        original_name = file.file_meta.get("original_name") if isinstance(file.file_meta, dict) else None
        relative_path = file.file_meta.get("relative_path") if isinstance(file.file_meta, dict) else None
        serialized.append({
            "id": file.id,
            "filename": file.filename,
            "original_name": original_name or file.filename,
            "relative_path": relative_path,
            "size": file.size_bytes,
            "content_type": file.content_type,
            "sha256": file.sha256,
            "url": f"/api/v1/files/{file.id}/download",
        })

    return serialized


def _serialize_task_tool(tool: Optional[Tool]) -> Optional[dict[str, Any]]:
    if not tool:
        return None

    current_version = None
    if tool.current_version:
        current_version = {
            "id": tool.current_version.id,
            "tool_id": tool.current_version.tool_id,
            "version": tool.current_version.version,
            "config": tool.current_version.config,
            "is_active": tool.current_version.is_active,
            "deprecated": tool.current_version.deprecated,
        }

    return {
        "id": tool.id,
        "name": tool.name,
        "slug": tool.slug,
        "description": tool.description,
        "icon": tool.icon,
        "status": tool.status,
        "version": tool.current_version.version if tool.current_version else None,
        "run_count": tool.statistics.usage_count if tool.statistics else 0,
        "current_version": current_version,
    }


async def _record_tool_usage(db: AsyncSession, tool_id: str) -> None:
    """确保工具统计存在，并记录一次使用。"""
    await record_tool_usage(db, tool_id)


def _is_admin(user: User) -> bool:
    return user.role == "admin"


async def _ensure_task_read_access(
    db: AsyncSession,
    *,
    task: Task,
    current_user: User,
) -> None:
    if _is_admin(current_user) or task.user_id == current_user.id:
        return
    project_id = _task_project_id(task)
    if project_id:
        await load_project_membership(
            db,
            project_id=project_id,
            user_id=current_user.id,
        )
        return
    raise ForbiddenException("无权访问此任务")


async def _ensure_task_operation_access(
    db: AsyncSession,
    *,
    task: Task,
    current_user: User,
) -> None:
    if _is_admin(current_user) or task.user_id == current_user.id:
        return
    project_id = _task_project_id(task)
    if project_id:
        await require_project_role(
            db,
            project_id=project_id,
            user=current_user,
            allowed_roles=TASK_OPERATION_PROJECT_ROLES,
        )
        return
    raise ForbiddenException("无权操作此任务")


@router.get("", response_model=dict)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    view: Optional[str] = Query(
        None,
        description="系统任务视图: all/running/history/needs_attention/recent_results",
    ),
    status: Optional[str] = None,
    tool_id: Optional[str] = None,
    keyword: Optional[str] = None,
    project_id: Optional[str] = Query(None, min_length=1, max_length=36),
    created_from: Optional[datetime] = Query(None, description="创建时间起点"),
    created_to: Optional[datetime] = Query(None, description="创建时间终点"),
    workflow_run_id: Optional[str] = Query(None, description="工作流运行 ID"),
    workflow_definition_id: Optional[str] = Query(None, description="工作流定义 ID"),
    workflow_node_id: Optional[str] = Query(None, description="工作流节点 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取任务列表"""
    page_result = await query_task_page(
        db,
        TaskQueryInput(
            current_user=current_user,
            page=page,
            page_size=page_size,
            view=view,
            status=status,
            tool_id=tool_id,
            keyword=keyword,
            project_id=project_id,
            created_from=created_from,
            created_to=created_to,
            workflow_run_id=workflow_run_id,
            workflow_definition_id=workflow_definition_id,
            workflow_node_id=workflow_node_id,
        ),
    )

    # 构建响应
    task_list = []
    for task in page_result.tasks:
        task_dict = TaskListResponse.model_validate(task).model_dump()
        task_dict["status"] = _normalize_task_status(task.status)
        if task.tool:
            task_dict["tool_name"] = task.tool.name
            task_dict["tool_slug"] = task.tool.slug
        task_dict["name"] = _resolve_task_display_name(
            name=task.name,
            tool_name=task.tool.name if task.tool else None,
            created_at=task.created_at,
            task_id=task.id,
        )
        task_dict["project_id"] = _task_project_id(task)
        task_dict["input_bindings"] = _task_input_bindings(task)
        task_dict["binding_decisions"] = _task_binding_decisions(task)
        task_dict["user_id"] = task.user_id
        if task.user:
            task_dict["user_name"] = task.user.display_name or task.user.email.split("@")[0]
            task_dict["user_email"] = task.user.email
        task_list.append(task_dict)

    return paginated_response(
        items=task_list,
        total=page_result.total,
        page=page,
        page_size=page_size,
    )


@router.get("/counts", response_model=dict)
async def get_task_counts(
    tool_id: Optional[str] = None,
    keyword: Optional[str] = None,
    project_id: Optional[str] = Query(None, min_length=1, max_length=36),
    created_from: Optional[datetime] = Query(None, description="创建时间起点"),
    created_to: Optional[datetime] = Query(None, description="创建时间终点"),
    workflow_run_id: Optional[str] = Query(None, description="工作流运行 ID"),
    workflow_definition_id: Optional[str] = Query(None, description="工作流定义 ID"),
    workflow_node_id: Optional[str] = Query(None, description="工作流节点 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务系统视图计数。"""
    counts = await query_task_view_counts(
        db,
        TaskQueryInput(
            current_user=current_user,
            tool_id=tool_id,
            keyword=keyword,
            project_id=project_id,
            created_from=created_from,
            created_to=created_to,
            workflow_run_id=workflow_run_id,
            workflow_definition_id=workflow_definition_id,
            workflow_node_id=workflow_node_id,
        ),
    )

    return success_response(counts.__dict__)


@router.post("/prepare-preview", response_model=dict)
async def prepare_task_preview(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """预览任务输入准备和标准 Artifact readiness，不创建任务。"""
    preview = await prepare_tool_task_preview(
        db=db,
        current_user=current_user,
        task_data=task_data,
    )
    return success_response(data=preview)


@router.get("/{task_id}", response_model=dict)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取任务详情"""
    result = await db.execute(
        select(Task)
        .options(
            selectinload(Task.tool).selectinload(Tool.current_version),
            selectinload(Task.tool).selectinload(Tool.statistics),
            selectinload(Task.inputs),
            selectinload(Task.outputs)
        )
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    await _ensure_task_read_access(db, task=task, current_user=current_user)

    input_file_ids = task.inputs.file_ids if task.inputs and task.inputs.file_ids else []
    output_file_ids = []
    if task.outputs:
        output_file_ids = task.outputs.file_ids or _extract_file_ids_from_result(task.outputs.result)
    output_file_ids = _dedupe_file_ids([str(file_id) for file_id in output_file_ids])

    task_data = {
        "id": task.id,
        "name": _resolve_task_display_name(
            name=task.name,
            tool_name=task.tool.name if task.tool else None,
            created_at=task.created_at,
            task_id=task.id,
        ),
        "project_id": _task_project_id(task),
        "input_bindings": _task_input_bindings(task),
        "binding_decisions": _task_binding_decisions(task),
        "user_id": task.user_id,
        "tool_id": task.tool_id,
        "tool_version_id": task.tool_version_id,
        "tool_name": task.tool.name if task.tool else None,
        "tool_slug": task.tool.slug if task.tool else None,
        "tool": _serialize_task_tool(task.tool),
        "resource_snapshot": (task.extra_data or {}).get("resource_snapshot"),
        "dispatch": (task.extra_data or {}).get("dispatch"),
        "status": _normalize_task_status(task.status),
        "priority": task.priority,
        "progress": task.progress,
        "progress_message": task.progress_message,
        "error_message": task.error_message,
        "failure_diagnostics": _task_failure_diagnostics(task),
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "completed_at": task.finished_at,
        "execution_time_sec": task.execution_time_sec,
        "retry_count": task.retry_count,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "inputs": {
            "params": task.inputs.params if task.inputs else {},
            "file_ids": input_file_ids,
            "input_bindings": _task_input_bindings(task),
        },
        "outputs": {
            "result": task.outputs.result if task.outputs else None,
            "file_ids": output_file_ids,
            "output_type": task.outputs.output_type if task.outputs else "json",
        },
        "output_data": _extract_primary_output_data(task.outputs.result) if task.outputs else None,
        "input_files": await _load_files(db, input_file_ids),
        "output_files": await _load_files(db, output_file_ids),
    }

    return success_response(data=task_data)


@router.post("", response_model=dict)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建任务"""
    task = await create_and_schedule_tool_task(
        db=db,
        current_user=current_user,
        task_data=task_data,
        direct_runner=direct_task_runner,
    )
    task_result = await db.execute(
        select(Task)
        .options(
            selectinload(Task.tool).selectinload(Tool.current_version),
            selectinload(Task.tool).selectinload(Tool.statistics),
        )
        .where(Task.id == task.id)
    )
    task = task_result.scalar_one()

    return success_response(
        data={
            "id": task.id,
            "name": task.name,
            "project_id": _task_project_id(task),
            "input_bindings": _task_input_bindings(task),
            "binding_decisions": _task_binding_decisions(task),
            "user_id": task.user_id,
            "tool_id": task.tool_id,
            "tool_version_id": task.tool_version_id,
            "tool_name": task.tool.name if task.tool else None,
            "tool_slug": task.tool.slug if task.tool else None,
            "tool": _serialize_task_tool(task.tool),
            "resource_snapshot": (task.extra_data or {}).get("resource_snapshot"),
            "dispatch": (task.extra_data or {}).get("dispatch"),
            "status": _normalize_task_status(task.status),
            "priority": task.priority,
            "progress": task.progress,
            "progress_message": task.progress_message,
            "error_message": task.error_message,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "execution_time_sec": task.execution_time_sec,
            "retry_count": task.retry_count,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        },
        message="任务创建成功"
    )


@router.post("/{task_id}/cancel", response_model=dict)
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """取消任务"""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    await _ensure_task_operation_access(db, task=task, current_user=current_user)

    # 只能取消等待中或运行中的任务
    if task.status not in [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]:
        raise ValidationException("任务状态不允许取消")

    await cancel_platform_task(
        db,
        task=task,
        current_user=current_user,
        direct_runner=direct_task_runner,
    )
    await db.commit()

    return success_response(message="任务已取消")


@router.post("/{task_id}/retry", response_model=dict)
async def retry_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """重试任务"""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    await _ensure_task_operation_access(db, task=task, current_user=current_user)

    # 只能重试失败或取消的任务
    if task.status not in [TaskStatus.FAILURE.value, TaskStatus.CANCELED.value]:
        raise ValidationException("任务状态不允许重试")

    version_result = await db.execute(
        select(ToolVersion).where(ToolVersion.id == task.tool_version_id)
    )
    tool_version = version_result.scalar_one()

    user_result = await db.execute(
        select(User).where(User.id == task.user_id)
    )
    task_user = user_result.scalar_one()

    # 重置任务状态
    task.status = TaskStatus.PENDING.value
    task.progress = 0.0
    task.progress_message = None
    task.error_message = None
    task.retry_count += 1
    task.started_at = None
    task.finished_at = None
    task.execution_time_sec = None

    await db.commit()
    extra_data = task.extra_data if isinstance(task.extra_data, dict) else {}
    resource_snapshot = extra_data.get("resource_snapshot")
    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=tool_version,
        user_role=task_user.role,
        direct_runner=direct_task_runner,
        resource_snapshot=resource_snapshot if isinstance(resource_snapshot, dict) else None,
        failure_detail="任务重新分发失败",
    )

    return success_response(message="任务已重新提交")


@router.get("/{task_id}/logs", response_model=dict)
async def get_task_logs(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    level: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取任务日志"""
    # 检查任务是否存在和权限
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    await _ensure_task_read_access(db, task=task, current_user=current_user)

    # 查询日志
    query = select(TaskLog).where(TaskLog.task_id == task_id)

    if level:
        query = query.where(TaskLog.level == level)

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(TaskLog.timestamp.asc())

    result = await db.execute(query)
    logs = result.scalars().all()

    return paginated_response(
        items=[_serialize_task_log(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/{task_id}", response_model=dict)
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """删除任务（管理员）"""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    await db.delete(task)
    await db.commit()

    return success_response(message="任务删除成功")
