# backend/app/worker/tasks.py
"""Celery 任务定义"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


# ==================== WebSocket 通知辅助函数 ====================

async def notify_task_status(task_id: str, status: str, message: Optional[str] = None):
    """通过 WebSocket 通知任务状态变更"""
    try:
        from app.websocket import ws_manager
        await ws_manager.send_task_status(task_id, status, message)
    except Exception as e:
        logger.debug(f"WebSocket 通知失败（可忽略）: {e}")


async def notify_task_progress(task_id: str, progress: float, message: Optional[str] = None):
    """通过 WebSocket 通知任务进度"""
    try:
        from app.websocket import ws_manager
        await ws_manager.send_task_progress(task_id, progress, message)
    except Exception as e:
        logger.debug(f"WebSocket 通知失败（可忽略）: {e}")


async def notify_task_log(task_id: str, level: str, log_message: str):
    """通过 WebSocket 通知任务日志"""
    try:
        from app.websocket import ws_manager
        await ws_manager.send_task_log(task_id, level, log_message)
    except Exception as e:
        logger.debug(f"WebSocket 通知失败（可忽略）: {e}")


async def notify_task_complete(task_id: str, result: Optional[Dict[str, Any]] = None):
    """通过 WebSocket 通知任务完成"""
    try:
        from app.websocket import ws_manager
        await ws_manager.send_task_complete(task_id, result)
    except Exception as e:
        logger.debug(f"WebSocket 通知失败（可忽略）: {e}")


async def notify_task_error(task_id: str, error: str):
    """通过 WebSocket 通知任务错误"""
    try:
        from app.websocket import ws_manager
        await ws_manager.send_task_error(task_id, error)
    except Exception as e:
        logger.debug(f"WebSocket 通知失败（可忽略）: {e}")


# ==================== 工具任务执行 ====================

@shared_task(
    bind=True,
    name="app.worker.tasks.execute_tool_task",
    max_retries=3,
    default_retry_delay=60
)
def execute_tool_task(self, task_id: str, params: Dict[str, Any]):
    """
    执行工具任务

    Args:
        task_id: 任务ID
        params: 任务参数

    Returns:
        执行结果
    """
    logger.info(f"开始执行任务: {task_id}")

    try:
        # 在异步上下文中执行
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            _execute_tool_task_impl(task_id, params)
        )
        logger.info(f"任务完成: {task_id}")
        return result

    except Exception as exc:
        logger.error(f"任务失败: {task_id}, 错误: {exc}")
        # 重试
        raise self.retry(exc=exc)


async def _execute_tool_task_impl(task_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    任务执行实现

    这里是实际执行工具的逻辑，同时通过 WebSocket 推送实时进度
    """
    from sqlalchemy import select
    from app.database.session import async_session_factory
    from app.models.tasks import Task, TaskStatus, TaskOutput, TaskLog

    async with async_session_factory() as db:
        # 获取任务
        result = await db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()

        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        # 更新状态为运行中
        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.utcnow()
        task.progress = 0.0
        task.progress_message = "任务开始执行"

        # 添加日志
        log = TaskLog(
            task_id=task_id,
            level="INFO",
            message="任务开始执行"
        )
        db.add(log)
        await db.commit()

        # WebSocket 通知：任务开始
        await notify_task_status(task_id, TaskStatus.RUNNING.value, "任务开始执行")
        await notify_task_log(task_id, "INFO", "任务开始执行")

        try:
            # TODO: 实际的工具执行逻辑
            # 这里应该根据 tool_version 的 config 来决定执行方式：
            # 1. 调用远程 API
            # 2. 执行 Docker 容器
            # 3. 执行本地脚本

            # 模拟执行过程
            for progress in [0.2, 0.4, 0.6, 0.8, 1.0]:
                task.progress = progress
                progress_msg = f"执行进度: {int(progress * 100)}%"
                task.progress_message = progress_msg
                await db.commit()

                # WebSocket 通知：进度更新
                await notify_task_progress(task_id, progress, progress_msg)
                await asyncio.sleep(0.5)  # 模拟耗时操作

            # 模拟结果
            output_result = {
                "status": "success",
                "message": "工具执行完成",
                "data": params  # 实际应该是工具的输出
            }

            # 创建输出记录
            output = TaskOutput(
                task_id=task_id,
                result=output_result,
                output_type="json"
            )
            db.add(output)

            # 更新任务状态
            task.status = TaskStatus.SUCCESS.value
            task.finished_at = datetime.utcnow()
            task.execution_time_sec = int(
                (task.finished_at - task.started_at).total_seconds()
            )
            task.progress = 1.0
            task.progress_message = "任务执行成功"

            # 添加完成日志
            log = TaskLog(
                task_id=task_id,
                level="INFO",
                message="任务执行成功"
            )
            db.add(log)
            await db.commit()

            # WebSocket 通知：任务完成
            await notify_task_log(task_id, "INFO", "任务执行成功")
            await notify_task_complete(task_id, output_result)

            return output_result

        except Exception as e:
            # 更新失败状态
            task.status = TaskStatus.FAILURE.value
            task.finished_at = datetime.utcnow()
            task.error_message = str(e)
            task.progress_message = f"任务失败: {str(e)}"

            # 添加错误日志
            log = TaskLog(
                task_id=task_id,
                level="ERROR",
                message=f"任务执行失败: {str(e)}"
            )
            db.add(log)
            await db.commit()

            # WebSocket 通知：任务失败
            await notify_task_log(task_id, "ERROR", f"任务执行失败: {str(e)}")
            await notify_task_error(task_id, str(e))

            raise


# ==================== 定时维护任务 ====================

@shared_task(name="app.worker.tasks.cleanup_expired_files")
def cleanup_expired_files():
    """
    清理过期文件

    定时执行，删除已过期的临时文件
    """
    logger.info("开始清理过期文件")

    loop = asyncio.get_event_loop()
    count = loop.run_until_complete(_cleanup_expired_files_impl())

    logger.info(f"清理完成，删除 {count} 个过期文件")
    return {"deleted_count": count}


async def _cleanup_expired_files_impl() -> int:
    """清理过期文件实现"""
    from sqlalchemy import select, delete
    from app.database.session import async_session_factory
    from app.models.files import File
    from app.storage import get_storage_backend

    storage = get_storage_backend()
    deleted_count = 0

    async with async_session_factory() as db:
        # 查找过期文件
        result = await db.execute(
            select(File).where(
                File.expires_at.isnot(None),
                File.expires_at < datetime.utcnow()
            )
        )
        expired_files = result.scalars().all()

        for file in expired_files:
            try:
                # 删除存储文件
                if file.storage_path:
                    await storage.delete(file.storage_path)
                # 删除数据库记录
                await db.delete(file)
                deleted_count += 1
            except Exception as e:
                logger.error(f"删除文件失败: {file.id}, 错误: {e}")

        await db.commit()

    return deleted_count


@shared_task(name="app.worker.tasks.collect_gpu_stats")
def collect_gpu_stats():
    """
    收集 GPU 统计信息

    定时执行，记录 GPU 使用情况
    """
    logger.info("收集 GPU 统计信息")

    try:
        # 尝试导入 pynvml
        import pynvml
        pynvml.nvmlInit()

        device_count = pynvml.nvmlDeviceGetCount()
        stats = []

        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)

            stats.append({
                "index": i,
                "name": pynvml.nvmlDeviceGetName(handle),
                "memory_total": info.total,
                "memory_used": info.used,
                "memory_free": info.free,
                "gpu_util": util.gpu,
                "memory_util": util.memory,
            })

        pynvml.nvmlShutdown()

        logger.info(f"收集到 {len(stats)} 个 GPU 的统计信息")
        return {"gpu_stats": stats}

    except Exception as e:
        logger.warning(f"无法收集 GPU 统计: {e}")
        return {"gpu_stats": [], "error": str(e)}
