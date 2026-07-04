# backend/app/tasks/direct_runner.py
"""开发模式 direct 任务执行器。"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict

from sqlalchemy import select

from app.database.session import async_session_factory
from app.models.tasks import Task, TaskLog, TaskStatus
from app.tasks.state_machine import TaskStateMachine

logger = logging.getLogger(__name__)


class DirectTaskRunner:
    """当前 FastAPI 进程内的任务调度器。"""

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}
        self._shutdown_task_ids: set[str] = set()

    def schedule_task(self, task_id: str, tool_version_id: str) -> asyncio.Task:
        """注册并启动后台任务。"""
        existing_task = self._tasks.get(task_id)
        if existing_task and not existing_task.done():
            return existing_task

        background_task = asyncio.create_task(
            self._run_task(task_id, tool_version_id),
            name=f"direct-task:{task_id}",
        )
        self._tasks[task_id] = background_task
        background_task.add_done_callback(lambda _: self._tasks.pop(task_id, None))
        return background_task

    def cancel_task(self, task_id: str) -> bool:
        """取消已注册的后台任务。"""
        background_task = self._tasks.get(task_id)
        if not background_task or background_task.done():
            self._tasks.pop(task_id, None)
            return False

        background_task.cancel()
        return True

    async def shutdown(self) -> None:
        """应用关闭时中断当前进程内任务，但不把它们误标为用户取消。"""
        pending_items = [
            (task_id, task)
            for task_id, task in self._tasks.items()
            if not task.done()
        ]
        self._shutdown_task_ids = {task_id for task_id, _ in pending_items}

        for _, background_task in pending_items:
            background_task.cancel()

        if pending_items:
            await asyncio.gather(
                *(task for _, task in pending_items),
                return_exceptions=True,
            )

        self._shutdown_task_ids.clear()
        self._tasks.clear()

    async def _run_task(self, task_id: str, tool_version_id: str) -> None:
        """执行单个后台任务。"""
        from app.worker.tasks import _execute_tool_task_impl

        try:
            await _execute_tool_task_impl(task_id, tool_version_id)
        except asyncio.CancelledError:
            if task_id in self._shutdown_task_ids:
                logger.info(
                    "Direct task %s interrupted by process shutdown; leave state for reconciliation",
                    task_id,
                )
            else:
                await self._mark_task_canceled(task_id, "开发模式 direct 任务已取消")
                logger.info("Direct task %s cancelled", task_id)
            raise
        except Exception:
            logger.exception("Direct task %s failed", task_id)

    async def _mark_task_canceled(self, task_id: str, message: str) -> None:
        """将被取消的 direct 任务写回数据库。"""
        async with async_session_factory() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return

            if task.status == TaskStatus.CANCELED.value:
                return

            TaskStateMachine.cancel(task)
            task.progress_message = message

            db.add(
                TaskLog(
                    task_id=task_id,
                    level="INFO",
                    message=message,
                )
            )
            await db.commit()


direct_task_runner = DirectTaskRunner()
