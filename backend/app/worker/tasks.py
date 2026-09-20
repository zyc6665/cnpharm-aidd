# backend/app/worker/tasks.py
"""Celery 任务定义"""

from typing import Dict, Any, Optional

from celery import shared_task
from celery.utils.log import get_task_logger

from app.common.async_runtime import run_coro_sync
from app.common.time import utcnow
from app.config import use_direct_task_execution
from app.remote_tools.registration import build_remote_tool_smoke_result_update
from app.tasks.attempts import (
    commit_current_attempt,
    get_execution_attempt_id,
    invoke_with_optional_attempt,
    new_execution_attempt_id,
    set_execution_attempt_id,
)
from app.tasks.executors.errors import GPUAllocationFailed, TaskExecutionError
from app.tasks.output import extract_output_file_ids, prepare_task_output
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

def _json_safe_detail(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe_detail(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_detail(item) for item in value]
    return str(value)


def _task_execution_failure_result(exc: Exception) -> Dict[str, Any] | None:
    """保留执行器返回的失败诊断，供任务详情页定位 stderr/stdout。"""
    if not isinstance(exc, TaskExecutionError) or not exc.details:
        return None

    details = _json_safe_detail(exc.details)
    if not isinstance(details, dict) or not details:
        return None

    result: Dict[str, Any] = {
        "success": False,
        "error": str(exc),
        "details": details,
    }
    for key in ("stdout", "stderr"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value
    return result


def _gpu_retry_message(task, exc: GPUAllocationFailed) -> str:
    wait_position = (
        f"，队列位置 {exc.wait_position}"
        if exc.wait_position is not None
        else ""
    )
    return (
        f"GPU 分配失败: {exc.message}{wait_position}；"
        f"第 {(task.retry_count or 0) + 1}/{task.max_retries} 次重试"
    )


def _canceled_task_result() -> Dict[str, Any]:
    return {
        "success": False,
        "status": "CANCELED",
        "message": "任务已取消",
    }


def _stale_task_result(task) -> Dict[str, Any]:
    return {
        "success": False,
        "status": task.status,
        "stale": True,
        "message": "忽略过期执行结果",
    }


def _is_current_attempt(task, attempt_id: str | None) -> bool:
    return attempt_id is None or get_execution_attempt_id(task) == attempt_id


async def _reschedule_after_gpu_shortage(db, *, task, tool_version) -> None:
    if use_direct_task_execution():
        from app.tasks.direct_runner import direct_task_runner

        attempt_id = new_execution_attempt_id()
        set_execution_attempt_id(task, attempt_id)
        await db.commit()
        invoke_with_optional_attempt(
            direct_task_runner.schedule_task_after_current,
            task_id=str(task.id),
            tool_version_id=str(tool_version.id),
            attempt_id=attempt_id,
        )
        return

    from sqlalchemy import select
    from app.models.users import User
    from app.tasks.service import dispatch_tool_task

    user = await db.scalar(select(User).where(User.id == task.user_id))
    extra_data = task.extra_data if isinstance(task.extra_data, dict) else {}
    resource_snapshot = extra_data.get("resource_snapshot")
    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=tool_version,
        user_role=user.role if user else None,
        resource_snapshot=resource_snapshot if isinstance(resource_snapshot, dict) else None,
        failure_detail="GPU 资源不足，任务重新入队失败",
    )


async def _record_remote_tool_smoke_result_if_needed(
    db,
    *,
    task,
    tool,
    tool_version,
    status: str,
    output_result: Dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Record remote-tool.v1 smoke test outcomes on the active version config."""
    extra_data = dict(task.extra_data or {})
    update = build_remote_tool_smoke_result_update(
        config=dict(tool_version.config or {}),
        extra_data=extra_data,
        task_id=str(task.id),
        status=status,
        finished_at=task.finished_at,
        output_result=output_result,
        error_message=error_message,
    )
    if update is None:
        return

    if update.auto_publish:
        from app.models.tools import ToolStatus

        tool.status = ToolStatus.PUBLISHED.value
    tool_version.config = update.config


async def _record_remote_tool_smoke_success_if_needed(
    db,
    *,
    task,
    tool,
    tool_version,
    output_result: Dict[str, Any],
) -> None:
    """Record successful remote-tool.v1 smoke tests on the active version config."""
    await _record_remote_tool_smoke_result_if_needed(
        db,
        task=task,
        tool=tool,
        tool_version=tool_version,
        status="success",
        output_result=output_result,
    )


async def _persist_standard_artifacts_if_present(db, task, tool_version, output_result):
    """Delegate standard result persistence to the Artifact service."""
    from app.services.standard_artifacts import persist_standard_artifacts_from_task_output

    return await persist_standard_artifacts_from_task_output(
        db,
        task=task,
        tool_version_config=tool_version.config,
        output_result=output_result,
        output_file_ids=extract_output_file_ids(output_result),
    )


async def _append_legacy_standard_result_if_needed(db, task, tool_version, output_result):
    """Add result.v2 metadata for supported legacy executors before persistence."""
    from app.tasks.legacy_standardization import append_legacy_standard_result

    return await append_legacy_standard_result(
        db,
        task=task,
        tool_version_config=tool_version.config,
        output_result=output_result,
        output_file_ids=extract_output_file_ids(output_result),
    )


def _attach_standard_artifact_summary(
    output_result: Dict[str, Any],
    persistence_result,
) -> Dict[str, Any]:
    from app.services.standard_artifacts import attach_standard_artifact_summary

    return attach_standard_artifact_summary(output_result, persistence_result)


@shared_task(
    name="app.worker.tasks.execute_tool_task",
)
def execute_tool_task(
    task_id: str,
    tool_version_id: str,
    attempt_id: str | None = None,
):
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
        if attempt_id is None:
            coroutine = _execute_tool_task_impl(task_id, tool_version_id)
        else:
            coroutine = _execute_tool_task_impl(task_id, tool_version_id, attempt_id)
        result = run_coro_sync(coroutine)
        logger.info(f"任务完成: {task_id}")
        return result

    except Exception as exc:
        logger.error(f"任务失败: {task_id}, 错误: {exc}")
        # 平台状态机已负责失败落库与用户触发重试，避免再叠加 Celery 重试。
        raise


async def _execute_tool_task_impl(
    task_id: str,
    tool_version_id: str,
    attempt_id: str | None = None,
) -> Dict[str, Any]:
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

        if not _is_current_attempt(task, attempt_id):
            logger.info("任务 %s 的 attempt 已过期，跳过执行", task_id)
            return _stale_task_result(task)

        if task.status == TaskStatus.CANCELED.value:
            logger.info("任务 %s 已取消，跳过排队消息", task_id)
            return _canceled_task_result()

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
            flush=False,
        )
        if not await commit_current_attempt(
            db,
            task=task,
            attempt_id=attempt_id,
            expected_status=TaskStatus.PENDING,
        ):
            latest_task = (
                await db.execute(select(Task).where(Task.id == task_id))
            ).scalar_one_or_none()
            return _stale_task_result(latest_task or task)
        await notify_task_agent_event(agent_run_id)

        # WebSocket 通知：任务开始
        await notify_task_status(task_id, TaskStatus.RUNNING.value, "任务开始执行")
        await notify_task_log(task_id, "INFO", "任务开始执行")

        try:
            # ==================== 实际的工具执行逻辑 ====================
            from app.models.tools import Tool, ToolVersion
            from app.models.tasks import TaskInput
            from app.execution.records import (
                finish_task_execution_record,
                start_task_execution_record,
            )
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

            execution_record = await start_task_execution_record(
                db,
                task=task,
                tool_slug=str(tool.slug),
                tool_version_id=str(tool_version.id),
                tool_version=str(tool_version.version),
                tool_type=str((tool_version.config or {}).get("type") or ""),
                attempt_id=attempt_id,
                tool_config=tool_version.config,
            )
            if execution_record is not None:
                # 先持久化运行中记录和任务指针，后续执行失败 rollback 时仍可写回终态。
                await db.commit()

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
                await db.refresh(task)
                if not _is_current_attempt(task, attempt_id):
                    logger.info("任务 %s 的 attempt 已过期，忽略进度", task_id)
                    return
                if task.status == TaskStatus.CANCELED.value:
                    logger.info("任务 %s 已取消，忽略进度", task_id)
                    return
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
                    flush=False,
                )
                if not await commit_current_attempt(
                    db,
                    task=task,
                    attempt_id=attempt_id,
                    expected_status=TaskStatus.RUNNING,
                ):
                    logger.info("任务 %s 的 attempt 已过期，忽略进度提交", task_id)
                    return
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

            # 取消请求可能与执行结果同时到达，用户取消优先于迟到结果。
            await db.refresh(task)
            if not _is_current_attempt(task, attempt_id):
                logger.info("任务 %s 的 attempt 已过期，忽略迟到结果", task_id)
                return _stale_task_result(task)
            if task.status == TaskStatus.CANCELED.value:
                logger.info("任务 %s 已取消，忽略迟到的执行结果", task_id)
                return _canceled_task_result()

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
            output_result = await _append_legacy_standard_result_if_needed(
                db,
                task,
                tool_version,
                output_result,
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

            # 后处理期间也可能发生取消或重新调度，提交产物前再次校验。
            await db.refresh(task)
            if not _is_current_attempt(task, attempt_id):
                stale_result = _stale_task_result(task)
                await db.rollback()
                logger.info("任务 %s 的 attempt 已过期，回滚迟到产物", task_id)
                return stale_result
            if task.status == TaskStatus.CANCELED.value:
                await db.rollback()
                logger.info("任务 %s 已取消，回滚迟到产物", task_id)
                return _canceled_task_result()

            # 更新任务状态
            TaskStateMachine.complete(
                task,
                success=True,
                progress_message="任务执行成功",
            )
            await finish_task_execution_record(
                db,
                task=task,
                status="succeeded",
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
            await _record_remote_tool_smoke_success_if_needed(
                db,
                task=task,
                tool=tool,
                tool_version=tool_version,
                output_result=output_result,
            )
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
                flush=False,
            )
            if not await commit_current_attempt(
                db,
                task=task,
                attempt_id=attempt_id,
                expected_status=TaskStatus.RUNNING,
            ):
                latest_task = (
                    await db.execute(select(Task).where(Task.id == task_id))
                ).scalar_one_or_none()
                logger.info("任务 %s 的 attempt 已过期，忽略成功提交", task_id)
                return _stale_task_result(latest_task or task)
            await notify_task_agent_event(agent_run_id)

            # WebSocket 通知：任务完成
            await notify_task_log(task_id, "INFO", "任务执行成功")
            await notify_task_complete(task_id, output_result)

            return output_result

        except Exception as e:
            # 清掉本轮未提交的输出/标准 Artifact 写入，避免失败任务留下下游产物。
            await db.rollback()
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one_or_none()
            if task is None:
                raise ValueError(f"任务不存在: {task_id}") from e

            if not _is_current_attempt(task, attempt_id):
                logger.info("任务 %s 的 attempt 已过期，忽略执行异常", task_id)
                return _stale_task_result(task)

            if task.status == TaskStatus.CANCELED.value:
                logger.info("任务 %s 已取消，忽略执行异常回写", task_id)
                return _canceled_task_result()

            version_result = await db.execute(
                select(ToolVersion).where(ToolVersion.id == tool_version_id)
            )
            tool_version = version_result.scalar_one_or_none()
            tool = None
            if tool_version is not None:
                tool_result = await db.execute(select(Tool).where(Tool.id == task.tool_id))
                tool = tool_result.scalar_one_or_none()

            if (
                isinstance(e, GPUAllocationFailed)
                and (task.retry_count or 0) < task.max_retries
                and tool_version is not None
            ):
                retry_message = _gpu_retry_message(task, e)
                TaskStateMachine.transition(
                    task,
                    TaskStatus.PENDING,
                    progress_message=retry_message,
                )
                db.add(
                    TaskLog(
                        task_id=task_id,
                        level="WARNING",
                        message=retry_message,
                        log_data={
                            "source": "gpu_allocator",
                            "wait_position": e.wait_position,
                            "retry_count": task.retry_count,
                        },
                    )
                )
                await finish_task_execution_record(
                    db,
                    task=task,
                    status="failed",
                    error_message=str(e),
                )
                if not await commit_current_attempt(
                    db,
                    task=task,
                    attempt_id=attempt_id,
                    expected_status=TaskStatus.RUNNING,
                ):
                    latest_task = (
                        await db.execute(select(Task).where(Task.id == task_id))
                    ).scalar_one_or_none()
                    logger.info("任务 %s 的 attempt 已过期，忽略 GPU 重入队", task_id)
                    return _stale_task_result(latest_task or task)
                await _reschedule_after_gpu_shortage(
                    db,
                    task=task,
                    tool_version=tool_version,
                )
                await notify_task_status(
                    task_id,
                    TaskStatus.PENDING.value,
                    retry_message,
                )
                await notify_task_log(task_id, "WARNING", retry_message)
                return {
                    "success": False,
                    "status": TaskStatus.PENDING.value,
                    "requeued": True,
                    "message": retry_message,
                    "wait_position": e.wait_position,
                }

            # 更新失败状态
            TaskStateMachine.complete(
                task,
                success=False,
                error_message=str(e),
                progress_message=f"任务失败: {str(e)}",
            )
            await finish_task_execution_record(
                db,
                task=task,
                status="failed",
                error_message=str(e),
            )

            # 添加错误日志
            log = TaskLog(
                task_id=task_id,
                level="ERROR",
                message=f"任务执行失败: {str(e)}"
            )
            db.add(log)
            failure_result = _task_execution_failure_result(e)
            if failure_result is not None:
                existing_output = (
                    await db.execute(select(TaskOutput).where(TaskOutput.task_id == task_id))
                ).scalar_one_or_none()
                failure_file_ids = extract_output_file_ids(failure_result)
                if existing_output is None:
                    db.add(
                        TaskOutput(
                            task_id=task_id,
                            result=failure_result,
                            file_ids=failure_file_ids,
                            output_type="json",
                        )
                    )
                else:
                    existing_output.result = failure_result
                    existing_output.file_ids = failure_file_ids
                    existing_output.output_type = "json"
            if tool is not None and tool_version is not None:
                await _record_remote_tool_smoke_result_if_needed(
                    db,
                    task=task,
                    tool=tool,
                    tool_version=tool_version,
                    status="failure",
                    error_message=str(e),
                )
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
                flush=False,
            )
            if not await commit_current_attempt(
                db,
                task=task,
                attempt_id=attempt_id,
                expected_status=TaskStatus.RUNNING,
            ):
                latest_task = (
                    await db.execute(select(Task).where(Task.id == task_id))
                ).scalar_one_or_none()
                logger.info("任务 %s 的 attempt 已过期，忽略失败提交", task_id)
                return _stale_task_result(latest_task or task)
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


@shared_task(name="app.worker.tasks.reclaim_stale_gpu_leases")
def reclaim_stale_gpu_leases():
    """回收超时未更新心跳的 GPU 租约。"""
    logger.info("开始回收过期 GPU 租约")

    reclaimed_count = run_coro_sync(_reclaim_stale_gpu_leases_impl())

    logger.info("GPU 租约回收完成，回收 %s 条", reclaimed_count)
    return {"reclaimed_count": reclaimed_count}


async def _reclaim_stale_gpu_leases_impl() -> int:
    """使用独立会话回收过期 GPU 租约。"""
    from app.database.session import async_session_factory
    from app.gpu.allocator import GPUAllocator

    async with async_session_factory() as db:
        reclaimed_count = await GPUAllocator(db=db).reclaim_stale_allocations()
        await db.commit()
        return reclaimed_count


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
