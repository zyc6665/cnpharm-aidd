# backend/app/models/tasks.py
import enum

from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey, JSON, event
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin, utcnow


class TaskStatus(str, enum.Enum):
    """任务状态

    与《03-系统架构设计说明书》3.4 节状态机一致：
    CREATED -> REJECTED: 配额/参数校验失败
    CREATED -> QUEUED -> RUNNING -> SUCCESS / FAILURE / CANCELED / TIMEOUT

    - PENDING：已创建但尚未入队调度（对应文档里的 CREATED）
    - REJECTED：准入被拒（配额不足、参数校验失败），从未进入队列
    - QUEUED：已入队/资源不足重新排队，等待调度
    - RUNNING：执行中
    - SUCCESS / FAILURE / CANCELED / TIMEOUT：终态

    注意：``REJECTED`` 是终态，但**不核销算力占用**（docs/03 §7.3、
    docs/04 §6.2：终态（含 FAILED/CANCELLED/TIMEOUT）一律核销，REJECTED
    不核销）。它记的是「这次提交被拒过」，不是一个跑过又结束的作业。
    """
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    TIMEOUT = "TIMEOUT"
    CANCELED = "CANCELED"


class TaskPriority(str, enum.Enum):
    """任务优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Task(Base, UUIDMixin, TimestampMixin):
    """任务表"""
    __tablename__ = "tasks"

    # 关联
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    # 项目归属真列（plan §4）。历史上 project_id 只存在 extra_data JSON 里，
    # 导致项目过滤只能走 JSON 表达式、且没有外键约束。此列由迁移
    # 20261030_04 回填；一个版本周期内额外保留 extra_data 双写以防回滚丢数据。
    project_id = Column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tool_id = Column(String(36), ForeignKey("tools.id"), nullable=False, index=True)
    tool_version_id = Column(String(36), ForeignKey("tool_versions.id"), nullable=False)
    name = Column(String(120), nullable=True, index=True)

    # 状态
    status = Column(String(20), default=TaskStatus.PENDING.value, nullable=False, index=True)
    priority = Column(String(20), default=TaskPriority.NORMAL.value, nullable=False)

    # 时间
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    execution_time_sec = Column(Integer, nullable=True)

    # 进度
    progress = Column(Float, default=0.0)
    progress_message = Column(String(500), nullable=True)

    # 错误信息
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    # 重试来源：这条重试链的起点任务 id（G-4，docs/04 §615 ``retry_of``）。
    # 语义为什么不是「指向上一行任务」：本仓库的重提是**就地复用同一个 task 行**——
    # ``TaskStateMachine.retry`` 只把 status 改回 PENDING、retry_count+1，不新建行，
    # 因此没有「新行的 retry_of 指向旧行」可言；「上一次执行」其实是同一行上的一次
    # execution attempt（只存在于 ``extra_data["execution_attempt_id"]``，没有独立 attempt
    # 表，attempt id 还是 32 位 hex 字符串，与 uuid 列类型不符）。
    # 所以这里存「本次重试起源于哪个任务」，即重试链的第一个任务 id：首次重试时写入，
    # 之后**永不覆盖**。就地重试时链起点就是本行自身，``retry_of`` 退化为「本行是重试
    # 产物」的持久标记；若将来从别的任务派生出新行，它天然就是那条新行的旧任务来源。
    # 为什么可空：非重试产生的任务没有重试来源，为 NULL；它不是主键/外键，只是可选归属信息。
    retry_of = Column(String(36), nullable=True, index=True)

    # GPU分配
    gpu_node_id = Column(String(36), nullable=True)
    gpu_index = Column(Integer, nullable=True)
    gpu_memory_allocated_mb = Column(Integer, nullable=True)

    # 元数据
    extra_data = Column(JSON, default=dict)  # 原 metadata，避免保留字冲突

    @property
    def celery_task_id(self):
        """兼容旧代码，从 extra_data 中读取 Celery 任务 ID。"""
        data = self.extra_data or {}
        return data.get("celery_task_id")

    @celery_task_id.setter
    def celery_task_id(self, value):
        """兼容旧代码，将 Celery 任务 ID 写入 extra_data。"""
        data = dict(self.extra_data or {})
        if value:
            data["celery_task_id"] = value
        else:
            data.pop("celery_task_id", None)
        self.extra_data = data

    @classmethod
    def project_id_expression(cls):
        """Return the project id column used by task queries.

        Kept as a classmethod for call-site compatibility; it now returns the
        real column instead of a JSON expression.
        """
        return cls.project_id

    # 关系
    user = relationship("User", back_populates="tasks")
    tool = relationship("Tool", back_populates="tasks")
    tool_version = relationship("ToolVersion", back_populates="tasks")
    inputs = relationship("TaskInput", back_populates="task", uselist=False, cascade="all, delete-orphan")
    outputs = relationship("TaskOutput", back_populates="task", uselist=False, cascade="all, delete-orphan")
    logs = relationship("TaskLog", back_populates="task", cascade="all, delete-orphan")


class TaskInput(Base, UUIDMixin, TimestampMixin):
    """任务输入表"""
    __tablename__ = "task_inputs"

    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, unique=True)

    # 输入参数
    params = Column(JSON, nullable=False, default=dict)

    # 输入文件ID列表
    file_ids = Column(JSON, default=list)

    # 关系
    task = relationship("Task", back_populates="inputs")


class TaskOutput(Base, UUIDMixin, TimestampMixin):
    """任务输出表"""
    __tablename__ = "task_outputs"

    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, unique=True)

    # 输出数据
    result = Column(JSON, nullable=True)

    # 输出文件ID列表
    file_ids = Column(JSON, default=list)

    # 输出类型 (json, text, file, visualization)
    output_type = Column(String(50), default="json")

    # 关系
    task = relationship("Task", back_populates="outputs")


class TaskLog(Base, UUIDMixin):
    """任务日志表"""
    __tablename__ = "task_logs"

    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=utcnow, nullable=False)
    level = Column(String(20), default="INFO")  # DEBUG, INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    log_data = Column(JSON, default=dict)  # 原 metadata，避免保留字冲突

    # 关系
    task = relationship("Task", back_populates="logs")


@event.listens_for(Task, "before_insert")
def _mirror_project_id_from_extra_data(_mapper, _connection, target: Task) -> None:
    """One-cycle dual-write safety net (plan §4).

    New tasks historically carried their project only in ``extra_data``.
    ``set_task_project_id`` remains the compatibility writer for that JSON, but
    every insert must also populate the real ``tasks.project_id`` column. Doing
    it on the ORM event covers both explicit writers and direct ``Task(...)``
    constructions (tests, worker retries) without touching each call site.
    """
    if target.project_id:
        return
    legacy = (target.extra_data or {}).get("project_id")
    if legacy:
        target.project_id = str(legacy)
