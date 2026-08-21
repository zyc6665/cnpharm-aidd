# backend/app/api/v1/tasks.py
"""任务管理API"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload, joinedload
from typing import Any, Optional

from app.config import use_direct_task_execution
from app.database.session import get_db
from app.models.files import File as FileModel
from app.models.users import User
from app.models.tools import Tool, ToolVersion
from app.models.tasks import Task, TaskLog, TaskStatus
from app.tasks.cancellation import cancel_platform_task
from app.tasks.direct_runner import direct_task_runner
from app.tasks.service import (
    create_and_schedule_tool_task,
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
    status: Optional[str] = None,
    tool_id: Optional[str] = None,
    keyword: Optional[str] = None,
    project_id: Optional[str] = Query(None, min_length=1, max_length=36),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取任务列表"""
    normalized_status = status.upper() if status else None
    query = select(Task).options(
        selectinload(Task.tool),
        joinedload(Task.user)
    )

    # 普通用户默认只能看自己的任务；项目上下文下按项目成员权限查看。
    is_admin = _is_admin(current_user)
    if project_id:
        if not is_admin:
            await load_project_membership(
                db,
                project_id=project_id,
                user_id=current_user.id,
            )
        query = query.where(Task.extra_data["project_id"].as_string() == project_id)
    elif not is_admin:
        query = query.where(Task.user_id == current_user.id)

    # 状态过滤
    if normalized_status:
        query = query.where(Task.status == normalized_status)

    # 工具过滤
    if tool_id:
        query = query.where(Task.tool_id == tool_id)

    # 关键词过滤
    if keyword:
        search_pattern = f"%{keyword}%"
        query = query.join(Tool, Task.tool_id == Tool.id, isouter=True).join(
            User,
            Task.user_id == User.id,
            isouter=True
        ).where(
            or_(
                Task.id.ilike(search_pattern),
                Task.name.ilike(search_pattern),
                Tool.name.ilike(search_pattern),
                Tool.slug.ilike(search_pattern),
                User.email.ilike(search_pattern),
                User.display_name.ilike(search_pattern)
            )
        )

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Task.created_at.desc())

    result = await db.execute(query)
    tasks = result.scalars().all()

    # 构建响应
    task_list = []
    for task in tasks:
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
        total=total,
        page=page,
        page_size=page_size,
    )


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

    try:
        if use_direct_task_execution():
            direct_task_runner.schedule_task(
                task_id=str(task.id),
                tool_version_id=str(task.tool_version_id),
            )
            logger.info("Task %s rescheduled in direct mode", task.id)
        else:
            from app.tasks.queue_manager import TaskQueueManager

            version_result = await db.execute(
                select(ToolVersion).where(ToolVersion.id == task.tool_version_id)
            )
            tool_version = version_result.scalar_one()

            user_result = await db.execute(
                select(User).where(User.id == task.user_id)
            )
            user = user_result.scalar_one()

            queue = TaskQueueManager.determine_queue(
                tool_config=tool_version.config,
                user_role=user.role,
                priority=task.priority
            )

            celery_task = TaskQueueManager.enqueue_task(
                task_id=str(task.id),
                tool_version_id=str(task.tool_version_id),
                queue=queue
            )

            task.celery_task_id = celery_task.id
            await db.commit()

            logger.info(f"Task {task.id} re-enqueued to {queue} (retry {task.retry_count})")

    except Exception as e:
        logger.error(f"Failed to re-enqueue task {task.id}: {e}")
        task.status = TaskStatus.FAILURE.value
        task.error_message = f"任务重新分发失败: {str(e)}"
        await db.commit()
        raise HTTPException(status_code=500, detail="任务重新分发失败")

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
