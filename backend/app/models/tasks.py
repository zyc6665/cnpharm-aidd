# backend/app/models/tasks.py
import enum

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin, utcnow

#: 任务状态枚举的单一源在 ``app.common.enums``（供前端枚举 codegen 与 parity
#: 测试守护）。这里同名 re-export，保持 ``from app.models.tasks import
#: TaskStatus`` 这一对外导入路径与 ``TaskStatus.PENDING`` 等成员访问完全不变。
from app.common.enums import TASK_STATUS as TaskStatus


class TaskPriority(str, enum.Enum):
    """任务优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Task(Base, UUIDMixin, TimestampMixin):
    """任务表"""
    __tablename__ = "tasks"
    __table_args__ = (
        # 工作流节点任务幂等键（Task 4-5）：同一 (run, node, attempt) 只允许一条任务。
        # 非工作流任务三列均为 NULL；SQLite/MySQL/PostgreSQL 的唯一索引都允许
        # 多行含 NULL，因此不影响普通任务。
        Index(
            "uq_tasks_workflow_node_attempt",
            "workflow_run_id",
            "workflow_node_id",
            "workflow_node_attempt",
            unique=True,
        ),
        # 结果中心：project_id + status IN (...) + ORDER BY finished_at DESC, created_at DESC。
        # 等值列在前、排序列在后，才能消掉 ``results.py`` 的 USE TEMP B-TREE。
        # PG 侧建索引必须用 ``finished_at DESC NULLS LAST, created_at DESC``（见
        # 迁移 20261031_01）；普通升序索引反扫会得到 NULLS FIRST，与查询语义不符。
        # SQLite 不支持 NULLS LAST 索引语法，迁移里建普通升序即可（其 DESC 扫描天然
        # 把 NULL 放到最后）。
        Index(
            "ix_tasks_project_status_finished",
            "project_id",
            "status",
            "finished_at",
            "created_at",
        ),
        # 结果中心按状态筛选、不带 finished_at 排序时的降级路径 / 一般结果列表排序。
        Index("ix_tasks_project_status_created", "project_id", "status", "created_at"),
        # 任务列表：user_id + status + ORDER BY created_at DESC。
        Index("ix_tasks_user_status_created", "user_id", "status", "created_at"),
        # 调度侧按状态 + 完成时间检索（超时扫描 / 状态巡检）。
        Index("ix_tasks_status_finished", "status", "finished_at"),
        # 仅 QUEUED 任务按 updated_at 排序的调度队列；只索引排队中的行，其余状态不进索引。
        Index(
            "ix_tasks_queued_updated",
            "updated_at",
            sqlite_where=text("status = 'QUEUED'"),
            postgresql_where=text("status = 'QUEUED'"),
        ),
    )

    # 关联
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    # 项目归属真列（plan §4）。历史上 project_id 只存在 extra_data JSON 里，
    # 导致项目过滤只能走 JSON 表达式、且没有外键约束。此列由迁移
    # 20261030_04 回填；一个版本周期内额外保留 extra_data 双写以防回滚丢数据。
    project_id = Column(
        String(36),
        ForeignKey(
            "projects.id", name="fk_tasks_project_id", ondelete="SET NULL"
        ),
        nullable=True,
    )
    tool_id = Column(String(36), ForeignKey("tools.id"), nullable=False, index=True)
    tool_version_id = Column(String(36), ForeignKey("tool_versions.id"), nullable=False)
    name = Column(String(120), nullable=True, index=True)

    # 状态
    status = Column(String(20), default=TaskStatus.PENDING.value, nullable=False)
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

    # 工作流节点归属的唯一键（Task 4-5）。历史上 run/node 只写在 ``TaskInput.params``
    # 的 JSON 里，去重只能靠「最近 20 条里猜」。这里落成真列并加唯一索引，让
    # 「同一 run + node + attempt 只建一条任务」由数据库保证，而不是靠应用层先查后建
    # 的竞态窗口。非工作流任务三列均为 NULL。
    workflow_run_id = Column(String(36), nullable=True)
    workflow_node_id = Column(String(128), nullable=True)
    # 本列已预留：当前节点重试是就地复用同一 task 行（只改 status、retry_count+1，
    # 不新建行），因此 workflow_node_attempt 恒为 1，实际唯一键等价于
    # ``(run_id, node_id)``。若将来引入真正的 attempt 递增（每次重试新建一行），
    # 必须同时修改 ``TaskCommand`` 与 workflow_tool/loop/map 调度器，让它们按
    # 当前 attempt 写列，唯一约束才会真正按 attempt 区分。
    workflow_node_attempt = Column(Integer, nullable=True)

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
    __table_args__ = (
        # 日志回看：固定按 task_id 过滤、按 timestamp 顺序翻页，复合列避免回表排序。
        Index("ix_task_logs_task_timestamp", "task_id", "timestamp"),
    )

    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False)
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
