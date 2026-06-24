# backend/app/models/tasks.py
import enum

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin, utcnow


class TaskStatus(str, enum.Enum):
    """任务状态"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
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
    session_id = Column(String(36), nullable=True, index=True)  # 游客session
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
