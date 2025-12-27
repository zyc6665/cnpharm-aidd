# backend/app/api/v1/tasks.py
"""任务管理API"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List

from app.database.session import get_db
from app.models.users import User
from app.models.tools import Tool, ToolVersion
from app.models.tasks import Task, TaskInput, TaskOutput, TaskLog, TaskStatus
from app.auth.dependencies import get_current_user, get_admin_user
from app.schemas.tasks import (
    TaskCreate, TaskResponse, TaskListResponse, TaskLogResponse
)
from app.common.responses import success_response, error_response
from app.common.exceptions import NotFoundException, ForbiddenException, ValidationException

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=dict)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    tool_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取任务列表"""
    query = select(Task).options(
        selectinload(Task.tool)
    )

    # 普通用户只能看自己的任务
    is_admin = current_user.role == "admin"
    if not is_admin:
        query = query.where(Task.user_id == current_user.id)

    # 状态过滤
    if status:
        query = query.where(Task.status == status)

    # 工具过滤
    if tool_id:
        query = query.where(Task.tool_id == tool_id)

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
        if task.tool:
            task_dict["tool_name"] = task.tool.name
            task_dict["tool_slug"] = task.tool.slug
        task_list.append(task_dict)

    return success_response(
        data={
            "items": task_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
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
            selectinload(Task.tool),
            selectinload(Task.inputs),
            selectinload(Task.outputs)
        )
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    # 权限检查
    is_admin = current_user.role == "admin"
    if not is_admin and task.user_id != current_user.id:
        raise ForbiddenException("无权访问此任务")

    task_data = TaskResponse.model_validate(task).model_dump()
    if task.tool:
        task_data["tool_name"] = task.tool.name
        task_data["tool_slug"] = task.tool.slug

    # 构建输入输出
    if task.inputs:
        task_data["inputs"] = {
            "params": task.inputs[0].params if task.inputs else {},
            "file_ids": [inp.file_id for inp in task.inputs if inp.file_id]
        }
    if task.outputs:
        task_data["outputs"] = {
            "result": task.outputs[0].result if task.outputs else None,
            "file_ids": task.outputs[0].file_ids if task.outputs else [],
            "output_type": task.outputs[0].output_type if task.outputs else "json"
        }

    return success_response(data=task_data)


@router.post("", response_model=dict)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建任务"""
    # 检查工具是否存在
    result = await db.execute(
        select(Tool).options(
            selectinload(Tool.current_version),
            joinedload(Tool.statistics)
        )
        .where(Tool.id == task_data.tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    # 确定使用的版本
    version_id = task_data.tool_version_id
    if not version_id:
        if not tool.current_version_id:
            raise ValidationException("工具没有可用版本")
        version_id = tool.current_version_id

    # 创建任务
    task = Task(
        user_id=current_user.id,
        tool_id=task_data.tool_id,
        tool_version_id=version_id,
        status=TaskStatus.PENDING.value,
        priority=task_data.priority,
        progress=0.0
    )

    db.add(task)
    await db.flush()

    # 创建任务输入
    task_input = TaskInput(
        task_id=task.id,
        params=task_data.params,
        file_id=task_data.file_ids[0] if task_data.file_ids else None
    )
    db.add(task_input)

    # 增加工具使用次数（通过statistics表）
    if not tool.statistics:
        from app.models.statistics import ToolStatistics
        tool.statistics = ToolStatistics(tool_id=tool.id)
        db.add(tool.statistics)
    tool.statistics.usage_count += 1
    tool.statistics.last_used_at = datetime.utcnow()

    await db.commit()
    await db.refresh(task)

    # ==================== 分发任务到Celery队列 ====================
    from app.tasks.queue_manager import TaskQueueManager

    # 获取工具版本配置（用于确定队列）
    version_result = await db.execute(
        select(ToolVersion).where(ToolVersion.id == version_id)
    )
    tool_version = version_result.scalar_one()

    # 确定任务队列
    queue = TaskQueueManager.determine_queue(
        tool_config=tool_version.config,
        user_role=current_user.role,
        priority=task_data.priority
    )

    # 分发任务到队列
    try:
        celery_task = TaskQueueManager.enqueue_task(
            task_id=str(task.id),
            tool_version_id=str(version_id),
            queue=queue
        )

        # 保存Celery任务ID
        task.celery_task_id = celery_task.id
        await db.commit()

        logger.info(f"Task {task.id} enqueued to {queue}")

    except Exception as e:
        logger.error(f"Failed to enqueue task {task.id}: {e}")
        task.status = TaskStatus.FAILURE.value
        task.error_message = f"任务分发失败: {str(e)}"
        await db.commit()
        raise HTTPException(status_code=500, detail="任务分发失败")

    return success_response(
        data=TaskResponse.model_validate(task).model_dump(),
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

    # 权限检查
    is_admin = current_user.role == "admin"
    if not is_admin and task.user_id != current_user.id:
        raise ForbiddenException("无权操作此任务")

    # 只能取消等待中或运行中的任务
    if task.status not in [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]:
        raise ValidationException("任务状态不允许取消")

    # 撤销Celery任务（如果有）
    if task.celery_task_id:
        from app.tasks.queue_manager import TaskQueueManager
        try:
            TaskQueueManager.revoke_task(task.celery_task_id)
            logger.info(f"Celery task {task.celery_task_id} revoked for task {task.id}")
        except Exception as e:
            logger.error(f"Failed to revoke Celery task {task.celery_task_id}: {e}")

    task.status = TaskStatus.CANCELED.value
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

    # 权限检查
    is_admin = current_user.role == "admin"
    if not is_admin and task.user_id != current_user.id:
        raise ForbiddenException("无权操作此任务")

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

    # ==================== 重新入队任务 ====================
    from app.tasks.queue_manager import TaskQueueManager

    # 获取工具版本配置
    version_result = await db.execute(
        select(ToolVersion).where(ToolVersion.id == task.tool_version_id)
    )
    tool_version = version_result.scalar_one()

    # 获取用户信息
    user_result = await db.execute(
        select(User).where(User.id == task.user_id)
    )
    user = user_result.scalar_one()

    # 确定任务队列（使用原始优先级）
    queue = TaskQueueManager.determine_queue(
        tool_config=tool_version.config,
        user_role=user.role,
        priority=task.priority
    )

    # 重新入队
    try:
        celery_task = TaskQueueManager.enqueue_task(
            task_id=str(task.id),
            tool_version_id=str(task.tool_version_id),
            queue=queue
        )

        # 更新Celery任务ID
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

    is_admin = current_user.role == "admin"
    if not is_admin and task.user_id != current_user.id:
        raise ForbiddenException("无权访问此任务")

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

    return success_response(
        data={
            "items": [TaskLogResponse.model_validate(log).model_dump() for log in logs],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
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
