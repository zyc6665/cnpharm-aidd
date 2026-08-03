# backend/app/worker/tasks.py
"""Celery 任务定义"""

from typing import Dict, Any, Optional

from celery import shared_task
from celery.utils.log import get_task_logger

from app.common.async_runtime import run_coro_sync
from app.common.time import utcnow
from app.tasks.naming import _extract_file_ids_from_result
from app.tasks.state_machine import TaskStateMachine

logger = get_task_logger(__name__)


# ==================== WebSocket 通知辅助函数 ====================

async def _notify_websocket(method_name: str, *args: Any) -> None:
    """调用 WebSocket 管理器的通知方法，失败时不影响任务主流程。"""
    try:
        from app.websocket import ws_manager
        await getattr(ws_manager, method_name)(*args)
    except Exception as e:
        logger.debug(f"WebSocket 通知失败（可忽略）: {e}")


async def notify_task_status(task_id: str, status: str, message: Optional[str] = None):
    """通过 WebSocket 通知任务状态变更"""
    await _notify_websocket("send_task_status", task_id, status, message)


async def notify_task_progress(task_id: str, progress: float, message: Optional[str] = None):
    """通过 WebSocket 通知任务进度"""
    await _notify_websocket("send_task_progress", task_id, progress, message)


async def notify_task_log(task_id: str, level: str, log_message: str):
    """通过 WebSocket 通知任务日志"""
    await _notify_websocket("send_task_log", task_id, level, log_message)


async def notify_task_complete(task_id: str, result: Optional[Dict[str, Any]] = None):
    """通过 WebSocket 通知任务完成"""
    await _notify_websocket("send_task_complete", task_id, result)


async def notify_task_error(task_id: str, error: str):
    """通过 WebSocket 通知任务错误"""
    await _notify_websocket("send_task_error", task_id, error)


# ==================== 工具任务执行 ====================

def _extract_output_file_ids(output_result: Dict[str, Any]) -> list[str]:
    """从执行结果中提取输出文件ID列表"""
    return _extract_file_ids_from_result(output_result, dedupe=True, skip_empty=True)


def prepare_task_output(output_result: Dict[str, Any]) -> Dict[str, Any]:
    """规范化任务输出，供持久化与接口层统一消费"""
    file_ids = _extract_output_file_ids(output_result)

    return {
        "result": output_result,
        "file_ids": file_ids,
        "output_type": "visualization" if file_ids else "json",
    }


async def _persist_standard_artifacts_if_present(db, task, tool_version, output_result):
    """Delegate standard result persistence to the Artifact service."""
    from app.services.standard_artifacts import persist_standard_artifacts_from_task_output

    return await persist_standard_artifacts_from_task_output(
        db,
        task=task,
        tool_version_config=tool_version.config,
        output_result=output_result,
        output_file_ids=_extract_output_file_ids(output_result),
    )


def _attach_standard_artifact_summary(
    output_result: Dict[str, Any],
    persistence_result,
) -> Dict[str, Any]:
    from app.services.standard_artifacts import attach_standard_artifact_summary

    return attach_standard_artifact_summary(output_result, persistence_result)


@shared_task(
    bind=True,
    name="app.worker.tasks.execute_tool_task",
    max_retries=3,
    default_retry_delay=60
)
def execute_tool_task(self, task_id: str, tool_version_id: str):
    """
    执行工具任务

    Args:
        task_id: 任务ID
        tool_version_id: 工具版本ID

    Returns:
        执行结果
    """
    logger.info(f"开始执行任务: {task_id}, 工具版本: {tool_version_id}")

    try:
        result = run_coro_sync(_execute_tool_task_impl(task_id, tool_version_id))
        logger.info(f"任务完成: {task_id}")
        return result

    except Exception as exc:
        logger.error(f"任务失败: {task_id}, 错误: {exc}")
        # 重试
        raise self.retry(exc=exc)


async def _execute_tool_task_impl(task_id: str, tool_version_id: str) -> Dict[str, Any]:
    """
    任务执行实现

    这里是实际执行工具的逻辑，同时通过 WebSocket 推送实时进度
    """
    from sqlalchemy import select
    from app.agents.aidd.task_events import (
        append_task_agent_event,
        notify_task_agent_event,
    )
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
        TaskStateMachine.start(task, progress_message="任务开始执行")

        # 添加日志
        log = TaskLog(
            task_id=task_id,
            level="INFO",
            message="任务开始执行"
        )
        db.add(log)
        agent_run_id = await append_task_agent_event(
            db,
            task=task,
            event_type="execution_started",
            payload={
                "status": "running",
                "progress": task.progress,
                "message": "任务开始执行",
            },
            run_status="running",
        )
        await db.commit()
        await notify_task_agent_event(agent_run_id)

        # WebSocket 通知：任务开始
        await notify_task_status(task_id, TaskStatus.RUNNING.value, "任务开始执行")
        await notify_task_log(task_id, "INFO", "任务开始执行")

        try:
            # ==================== 实际的工具执行逻辑 ====================
            from app.models.tools import Tool, ToolVersion
            from app.models.tasks import TaskInput
            from app.tasks.executor import TaskExecutor
            from app.tasks.molecule_scoring import append_molecule_scoring_artifacts

            # 获取工具版本配置
            version_result = await db.execute(
                select(ToolVersion).where(ToolVersion.id == tool_version_id)
            )
            tool_version = version_result.scalar_one()

            tool_result = await db.execute(select(Tool).where(Tool.id == task.tool_id))
            tool = tool_result.scalar_one_or_none()
            if tool is None:
                raise ValueError(f"任务关联的工具不存在: {task.tool_id}")

            # 获取任务输入参数
            input_result = await db.execute(
                select(TaskInput).where(TaskInput.task_id == task_id)
            )
            task_input = input_result.scalar_one_or_none()
            task.inputs = task_input
            params = task_input.params if task_input else {}

            logger.info(f"执行工具 {tool_version.tool_id}, 类型: {tool_version.config.get('executor_type')}")

            # 定义进度回调函数
            async def progress_callback(progress: float, message: str):
                """进度更新回调"""
                TaskStateMachine.update_progress(task, progress, message)
                db.add(
                    TaskLog(
                        task_id=task_id,
                        level="INFO",
                        message=message,
                        log_data={"progress": progress, "source": "executor"},
                    )
                )
                agent_run_id = await append_task_agent_event(
                    db,
                    task=task,
                    event_type="execution_progress",
                    payload={
                        "status": "running",
                        "progress": progress,
                        "message": message,
                    },
                    run_status="running",
                )
                await db.commit()
                await notify_task_agent_event(agent_run_id)

                # WebSocket 通知：进度更新
                await notify_task_progress(task_id, progress, message)
                await notify_task_log(task_id, "INFO", message)

            # 创建执行器并执行
            # 使用正确的构造函数签名：TaskExecutor(task, tool_version)
            executor = TaskExecutor(
                task,
                tool_version,
                tool=tool,
                progress_callback=progress_callback,
            )

            # 执行任务
            output_result = await executor.execute()
            logger.info(f"任务 {task_id} 执行成功")
            try:
                output_result = await append_molecule_scoring_artifacts(
                    db,
                    task,
                    tool_version,
                    output_result,
                )
            except Exception as scoring_exc:
                logger.warning(
                    "任务 %s 分子评分后处理失败，保留原始生成结果: %s",
                    task_id,
                    scoring_exc,
                )

            # 创建输出记录
            prepared_output = prepare_task_output(output_result)
            standard_persistence = await _persist_standard_artifacts_if_present(
                db,
                task,
                tool_version,
                output_result,
            )
            if standard_persistence is not None:
                prepared_output["result"] = _attach_standard_artifact_summary(
                    prepared_output["result"],
                    standard_persistence,
                )
            output = TaskOutput(
                task_id=task_id,
                result=prepared_output["result"],
                file_ids=prepared_output["file_ids"],
                output_type=prepared_output["output_type"]
            )
            db.add(output)

            # 更新任务状态
            TaskStateMachine.complete(
                task,
                success=True,
                progress_message="任务执行成功",
            )
            task.execution_time_sec = int(
                (task.finished_at - task.started_at).total_seconds()
            )

            # 添加完成日志
            log = TaskLog(
                task_id=task_id,
                level="INFO",
                message="任务执行成功"
            )
            db.add(log)
            completion_payload: dict[str, Any] = {
                "status": "success",
                "progress": task.progress,
                "message": "任务执行成功",
            }
            if isinstance(prepared_output["result"], dict):
                standard_artifacts = prepared_output["result"].get("standard_artifacts")
                if isinstance(standard_artifacts, dict):
                    completion_payload["standard_artifacts"] = standard_artifacts
            agent_run_id = await append_task_agent_event(
                db,
                task=task,
                event_type="execution_completed",
                payload=completion_payload,
                run_status="success",
            )
            await db.commit()
            await notify_task_agent_event(agent_run_id)

            # WebSocket 通知：任务完成
            await notify_task_log(task_id, "INFO", "任务执行成功")
            await notify_task_complete(task_id, output_result)

            return output_result

        except Exception as e:
            # 更新失败状态
            TaskStateMachine.complete(
                task,
                success=False,
                error_message=str(e),
                progress_message=f"任务失败: {str(e)}",
            )

            # 添加错误日志
            log = TaskLog(
                task_id=task_id,
                level="ERROR",
                message=f"任务执行失败: {str(e)}"
            )
            db.add(log)
            agent_run_id = await append_task_agent_event(
                db,
                task=task,
                event_type="execution_failed",
                payload={
                    "status": "failure",
                    "progress": task.progress,
                    "message": f"任务失败: {str(e)}",
                    "error": str(e),
                },
                run_status="failure",
                error_message=str(e),
            )
            await db.commit()
            await notify_task_agent_event(agent_run_id)

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

    count = run_coro_sync(_cleanup_expired_files_impl())

    logger.info(f"清理完成，删除 {count} 个过期文件")
    return {"deleted_count": count}


async def _cleanup_expired_files_impl() -> int:
    """清理过期文件实现"""
    from sqlalchemy import select
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
                File.expires_at < utcnow()
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
