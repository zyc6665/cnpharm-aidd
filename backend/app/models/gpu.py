"""GPU资源租约模型。"""

import enum

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, text

from app.common.time import utcnow
from app.database.base import Base, UUIDMixin


class GPUAllocationStatus(str, enum.Enum):
    """GPU租约状态。"""

    ACTIVE = "active"
    RELEASED = "released"


class GPUAllocation(Base, UUIDMixin):
    """单次GPU占用租约，保留释放历史并限制活动租约冲突。"""

    __tablename__ = "gpu_allocations"
    __table_args__ = (
        Index(
            "uq_gpu_allocations_active_device",
            "gpu_node_id",
            "gpu_index",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    execution_attempt_id = Column(String(64), nullable=True, index=True)
    gpu_node_id = Column(String(36), nullable=False, index=True)
    gpu_index = Column(Integer, nullable=False)
    memory_allocated_mb = Column(Integer, nullable=False)
    status = Column(
        String(16),
        nullable=False,
        default=GPUAllocationStatus.ACTIVE.value,
        index=True,
    )
    allocated_at = Column(DateTime, nullable=False, default=utcnow)
    heartbeat_at = Column(DateTime, nullable=False, default=utcnow)
    released_at = Column(DateTime, nullable=True)
