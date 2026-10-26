# backend/app/tasks/state_machine.py
"""任务状态机

依据《03-系统架构设计说明书》3.4 节与《04-数据模型设计说明书》4.2 节实现。
规格八态 = CREATED / QUEUED / RUNNING / SUCCEEDED / FAILED / CANCELLED / TIMEOUT / REJECTED，
与内部枚举的对应关系是 PENDING=CREATED、SUCCESS=SUCCEEDED、FAILURE=FAILED、
CANCELED=CANCELLED；本次补齐 QUEUED 与 TIMEOUT 两态，共七态。
REJECTED（准入拒绝）尚未落库，仍是规格与实现的既有偏差，不在本次范围。

状态转换规则：
- PENDING -> QUEUED, RUNNING, CANCELED, FAILURE（入队 / 直接调度 / 取消 / 启动前校验失败）
- QUEUED  -> RUNNING, CANCELED, FAILURE, TIMEOUT（被调度 / 取消 / 准入失败 / 排队超时）
- RUNNING -> SUCCESS, FAILURE, CANCELED, TIMEOUT, QUEUED, PENDING
             （完成 / 失败 / 取消 / 执行超时 / GPU 不足重新入队 / 旧路径回退重排）
- SUCCESS -> (终态)
- FAILURE -> PENDING, QUEUED（重试）
- TIMEOUT -> PENDING, QUEUED（重试）
- CANCELED -> PENDING, QUEUED, SUCCESS, FAILURE（重新提交 / 远端结果补回）
"""

from typing import TYPE_CHECKING, Dict, Optional, Set
import logging

from app.common.time import utcnow
from app.models.tasks import TaskStatus
from app.tasks.attempts import clear_task_execution_control

if TYPE_CHECKING:
    from app.models.tasks import Task

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
# 排队起点（docs/18 §6.4 B-2b）：转入 QUEUED 时写入，排队超时巡检据此判定。
# 用它而不是 created_at：任务可能先 PENDING 停留（等上传物化、等前置校验），
# 那段时间不该算排队。离开 QUEUED 时清掉，避免重排后用旧锚点被误判超时。
QUEUED_AT_METADATA_KEY = "queued_at"
RESOURCE_WAIT_METADATA_KEYS = (
    "resource_wait_reason",
    "resource_wait_code",
    "resource_wait_category",
    "resource_wait_scope",
    "resource_wait_dimension",
    "resource_retry_count",
    "resource_retry_next_at",
)


def _retry_limits(task: "Task") -> tuple[int, int]:
    retry_count = task.retry_count if task.retry_count is not None else 0
    max_retries = (
        task.max_retries
        if task.max_retries is not None
        else DEFAULT_MAX_RETRIES
    )
    return retry_count, max_retries


def _set_queued_at(task: "Task", moment) -> None:
    """写入排队起点（naive UTC ISO 字符串，与 extra_data 里其它时间同口径）。"""
    extra_data = dict(task.extra_data or {})
    extra_data[QUEUED_AT_METADATA_KEY] = moment.isoformat()
    task.extra_data = extra_data


def _clear_queued_at(task: "Task") -> None:
    """离开 QUEUED 时清掉排队起点；没有该键则完全不碰 extra_data。"""
    extra_data = task.extra_data
    if not isinstance(extra_data, dict) or QUEUED_AT_METADATA_KEY not in extra_data:
        return
    updated = dict(extra_data)
    updated.pop(QUEUED_AT_METADATA_KEY, None)
    task.extra_data = updated


class TaskStateError(Exception):
    """任务状态转换错误"""

    def __init__(
        self,
        from_status: TaskStatus,
        to_status: TaskStatus,
        task_id: Optional[str] = None
    ):
        self.from_status = from_status
        self.to_status = to_status
        self.task_id = task_id
        message = f"Invalid transition: {from_status.value} -> {to_status.value}"
        if task_id:
            message = f"Task {task_id}: {message}"
        super().__init__(message)


class TaskStateMachine:
    """任务状态机

    负责管理任务状态转换，确保状态转换合法性，
    并在状态转换时执行相应的副作用操作。
    """

    # 状态转换规则表
    TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
        TaskStatus.PENDING: {
            TaskStatus.QUEUED,  # 入队等待调度
            TaskStatus.RUNNING,  # 直连执行模式下立即调度
            TaskStatus.CANCELED,
            TaskStatus.FAILURE  # 启动前校验或调度失败
        },
        TaskStatus.QUEUED: {
            TaskStatus.RUNNING,  # 被调度执行
            TaskStatus.CANCELED,
            TaskStatus.FAILURE,  # 准入失败
            TaskStatus.TIMEOUT  # 排队超时
        },
        TaskStatus.RUNNING: {
            TaskStatus.SUCCESS,
            TaskStatus.FAILURE,
            TaskStatus.CANCELED,
            TaskStatus.TIMEOUT,  # 执行超时（执行器 timeout_sec 到期）
            TaskStatus.QUEUED,  # GPU 不足重新排队
            TaskStatus.PENDING  # 兼容旧路径的重排重试
        },
        TaskStatus.SUCCESS: set(),  # 终态，不可转换
        TaskStatus.FAILURE: {
            TaskStatus.PENDING,  # 重试
            TaskStatus.QUEUED  # 重试后直接入队
        },
        TaskStatus.TIMEOUT: {
            TaskStatus.PENDING,  # 重试
            TaskStatus.QUEUED  # 重试后直接入队
        },
        TaskStatus.CANCELED: {
            TaskStatus.PENDING,  # 重新提交
            TaskStatus.QUEUED,  # 重新提交并直接入队
            TaskStatus.SUCCESS,  # 远端结果补回时发现实际成功
            TaskStatus.FAILURE,  # 远端结果补回时发现实际失败
        }
    }

    # 终态集合
    TERMINAL_STATES: Set[TaskStatus] = {
        TaskStatus.SUCCESS,
        TaskStatus.FAILURE,
        TaskStatus.CANCELED,
        TaskStatus.TIMEOUT
    }

    # 未开始（尚未进入执行）的状态集合
    PENDING_STATES: Set[TaskStatus] = {
        TaskStatus.PENDING,
        TaskStatus.QUEUED
    }

    @classmethod
    def can_transition(
        cls,
        from_status: TaskStatus,
        to_status: TaskStatus
    ) -> bool:
        """检查状态转换是否合法

        Args:
            from_status: 当前状态
            to_status: 目标状态

        Returns:
            bool: 状态转换是否合法
        """
        if isinstance(from_status, str):
            from_status = TaskStatus(from_status)
        if isinstance(to_status, str):
            to_status = TaskStatus(to_status)

        return to_status in cls.TRANSITIONS.get(from_status, set())

    @classmethod
    def is_terminal(cls, status: TaskStatus) -> bool:
        """检查是否为终态

        Args:
            status: 任务状态

        Returns:
            bool: 是否为终态
        """
        if isinstance(status, str):
            status = TaskStatus(status)
        return status in cls.TERMINAL_STATES

    @classmethod
    def get_available_transitions(cls, status: TaskStatus) -> Set[TaskStatus]:
        """获取当前状态可转换的目标状态集合

        Args:
            status: 当前状态

        Returns:
            Set[TaskStatus]: 可转换的目标状态集合
        """
        if isinstance(status, str):
            status = TaskStatus(status)
        return cls.TRANSITIONS.get(status, set()).copy()

    @classmethod
    def transition(
        cls,
        task: "Task",
        to_status: TaskStatus,
        error_message: Optional[str] = None,
        progress: Optional[float] = None,
        progress_message: Optional[str] = None
    ) -> None:
        """执行状态转换

        执行状态转换并应用相应的副作用，包括：
        - RUNNING: 设置开始时间
        - QUEUED: 清理上一轮执行信息并重新排队（非首次入队时累加重试次数）
        - SUCCESS/FAILURE/CANCELED/TIMEOUT: 设置结束时间和执行时长
        - FAILURE/TIMEOUT: 设置错误信息
        - PENDING (从FAILURE/CANCELED/TIMEOUT): 清理并准备重试

        Args:
            task: 任务对象
            to_status: 目标状态
            error_message: 错误信息（FAILURE状态时使用）
            progress: 进度值（0-100）
            progress_message: 进度消息

        Raises:
            TaskStateError: 当状态转换不合法时抛出
        """
        if isinstance(to_status, str):
            to_status = TaskStatus(to_status)

        current_status = TaskStatus(task.status) if isinstance(task.status, str) else task.status

        if not cls.can_transition(current_status, to_status):
            raise TaskStateError(current_status, to_status, task.id)

        old_status = current_status
        task.status = to_status.value

        # 状态转换副作用
        now = utcnow()

        if to_status == TaskStatus.RUNNING:
            # 开始执行
            task.started_at = now
            task.progress = progress if progress is not None else 0.0
            task.progress_message = progress_message or "任务开始执行"
            extra_data = dict(task.extra_data or {})
            for key in RESOURCE_WAIT_METADATA_KEYS:
                extra_data.pop(key, None)
            task.extra_data = extra_data

        elif to_status == TaskStatus.SUCCESS:
            # 执行成功
            task.finished_at = now
            task.progress = 100.0
            task.progress_message = progress_message or "任务执行成功"
            cls._calculate_execution_time(task)

        elif to_status == TaskStatus.FAILURE:
            # 执行失败
            task.finished_at = now
            task.error_message = error_message
            task.progress_message = progress_message or "任务执行失败"
            cls._calculate_execution_time(task)

        elif to_status == TaskStatus.TIMEOUT:
            # 执行/排队超时（终态之一，可重试）
            task.finished_at = now
            task.error_message = error_message
            task.progress_message = progress_message or "任务执行超时"
            cls._calculate_execution_time(task)

        elif to_status == TaskStatus.CANCELED:
            # 取消任务
            task.finished_at = now
            task.progress_message = progress_message or "任务已取消"
            cls._calculate_execution_time(task)

        elif to_status == TaskStatus.PENDING and old_status in {
            TaskStatus.FAILURE,
            TaskStatus.CANCELED,
            TaskStatus.TIMEOUT,
        }:
            # 重试/重新提交
            task.retry_count = (task.retry_count or 0) + 1
            task.error_message = None
            task.started_at = None
            task.finished_at = None
            task.execution_time_sec = None
            task.progress = 0.0
            task.progress_message = progress_message or "任务等待重新执行"

        elif to_status == TaskStatus.PENDING and old_status == TaskStatus.RUNNING:
            # 资源不足重新入队（旧路径，仍保留 PENDING 作为重排目标以兼容既有调用）
            task.retry_count = (task.retry_count or 0) + 1
            task.progress_message = progress_message or "资源不足，重新入队等待"
            task.started_at = None

        elif to_status == TaskStatus.QUEUED:
            if old_status == TaskStatus.PENDING:
                # 首次入队：仍属「未开始」，不算一次重试
                task.progress = 0.0
                task.progress_message = progress_message or "任务已入队等待调度"
            else:
                # RUNNING/FAILURE/CANCELED/TIMEOUT -> QUEUED：重新排队，计一次重试
                task.retry_count = (task.retry_count or 0) + 1
                task.error_message = None
                task.started_at = None
                task.finished_at = None
                task.execution_time_sec = None
                task.progress = 0.0
                task.progress_message = progress_message or "资源不足，重新排队等待"
            # 记排队起点：排队超时巡检（app.services.queue_timeout）据此判定
            _set_queued_at(task, now)

        # 离开 QUEUED 时清掉排队锚点，否则重排任务会带着旧时间被立刻判超时
        if old_status == TaskStatus.QUEUED and to_status != TaskStatus.QUEUED:
            _clear_queued_at(task)

        # 更新进度（如果提供）
        if progress is not None and to_status not in {TaskStatus.SUCCESS}:
            task.progress = min(max(progress, 0.0), 100.0)
        if progress_message is not None:
            task.progress_message = progress_message

        # 记录状态变更日志
        logger.info(
            f"Task {task.id} state transition: {old_status.value} -> {to_status.value}",
            extra={
                "task_id": task.id,
                "old_status": old_status.value,
                "new_status": to_status.value,
                "error_message": error_message,
                "progress": task.progress
            }
        )

    @classmethod
    def _calculate_execution_time(cls, task: "Task") -> None:
        """计算执行时长"""
        if task.started_at and task.finished_at:
            task.execution_time_sec = int(
                (task.finished_at - task.started_at).total_seconds()
            )

    @classmethod
    def can_retry(cls, task: "Task") -> bool:
        """检查任务是否可以重试

        Args:
            task: 任务对象

        Returns:
            bool: 是否可以重试
        """
        current_status = TaskStatus(task.status) if isinstance(task.status, str) else task.status

        # 失败、取消或超时状态可以重试
        if current_status not in {
            TaskStatus.FAILURE,
            TaskStatus.CANCELED,
            TaskStatus.TIMEOUT,
        }:
            return False

        retry_count, max_retries = _retry_limits(task)

        # 检查重试次数
        if retry_count >= max_retries:
            return False

        return True

    @classmethod
    def can_cancel(cls, task: "Task") -> bool:
        """检查任务是否可以取消

        Args:
            task: 任务对象

        Returns:
            bool: 是否可以取消
        """
        current_status = TaskStatus(task.status) if isinstance(task.status, str) else task.status
        return cls.can_transition(current_status, TaskStatus.CANCELED)

    @classmethod
    def retry(cls, task: "Task") -> None:
        """重试任务

        Args:
            task: 任务对象

        Raises:
            TaskStateError: 当任务不可重试时抛出
            ValueError: 当任务达到最大重试次数时抛出
        """
        if not cls.can_retry(task):
            current_status = TaskStatus(task.status) if isinstance(task.status, str) else task.status
            retry_count, max_retries = _retry_limits(task)
            if retry_count >= max_retries:
                raise ValueError(
                    f"Task {task.id} has reached maximum retry count ({max_retries})"
                )
            raise TaskStateError(current_status, TaskStatus.PENDING, task.id)

        cls.transition(task, TaskStatus.PENDING, progress_message="任务重试")
        clear_task_execution_control(task)

    @classmethod
    def cancel(cls, task: "Task") -> None:
        """取消任务

        Args:
            task: 任务对象

        Raises:
            TaskStateError: 当任务不可取消时抛出
        """
        if not cls.can_cancel(task):
            current_status = TaskStatus(task.status) if isinstance(task.status, str) else task.status
            raise TaskStateError(current_status, TaskStatus.CANCELED, task.id)

        cls.transition(task, TaskStatus.CANCELED)

    @classmethod
    def start(cls, task: "Task", progress_message: Optional[str] = None) -> None:
        """开始执行任务

        Args:
            task: 任务对象
            progress_message: 进度消息

        Raises:
            TaskStateError: 当任务无法开始执行时抛出
        """
        cls.transition(task, TaskStatus.RUNNING, progress_message=progress_message)

    @classmethod
    def complete(
        cls,
        task: "Task",
        success: bool = True,
        error_message: Optional[str] = None,
        progress_message: Optional[str] = None
    ) -> None:
        """完成任务

        Args:
            task: 任务对象
            success: 是否成功
            error_message: 错误信息（失败时使用）
            progress_message: 进度消息

        Raises:
            TaskStateError: 当状态转换不合法时抛出
        """
        if success:
            cls.transition(task, TaskStatus.SUCCESS, progress_message=progress_message)
        else:
            cls.transition(
                task, TaskStatus.FAILURE,
                error_message=error_message,
                progress_message=progress_message
            )

    @classmethod
    def mark_timeout(
        cls,
        task: "Task",
        error_message: Optional[str] = None,
        progress_message: Optional[str] = None
    ) -> None:
        """标记任务超时

        执行器 timeout_sec 到期或排队超时时使用，落 TIMEOUT 终态（可重试）。

        Args:
            task: 任务对象
            error_message: 错误信息
            progress_message: 进度消息

        Raises:
            TaskStateError: 当当前状态不允许转换到 TIMEOUT 时抛出
        """
        cls.transition(
            task, TaskStatus.TIMEOUT,
            error_message=error_message,
            progress_message=progress_message or "任务执行超时"
        )

    @classmethod
    def enqueue(
        cls,
        task: "Task",
        progress_message: Optional[str] = None
    ) -> None:
        """把任务放入调度队列

        Args:
            task: 任务对象
            progress_message: 进度消息

        Raises:
            TaskStateError: 当当前状态不允许入队时抛出
        """
        cls.transition(
            task, TaskStatus.QUEUED,
            progress_message=progress_message or "任务已入队等待调度"
        )

    @classmethod
    def update_progress(
        cls,
        task: "Task",
        progress: float,
        message: Optional[str] = None
    ) -> None:
        """更新任务进度

        只有RUNNING状态的任务可以更新进度。

        Args:
            task: 任务对象
            progress: 进度值（0-100）
            message: 进度消息

        Raises:
            ValueError: 当任务不在RUNNING状态时抛出
        """
        current_status = TaskStatus(task.status) if isinstance(task.status, str) else task.status
        if current_status != TaskStatus.RUNNING:
            raise ValueError(
                f"Cannot update progress for task in {current_status.value} state"
            )

        task.progress = min(max(progress, 0.0), 100.0)
        if message:
            task.progress_message = message

        logger.debug(
            f"Task {task.id} progress updated: {progress:.1f}%",
            extra={"task_id": task.id, "progress": progress, "message": message}
        )
