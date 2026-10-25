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
    # 卡位追溯字段（docs/09 §5.6、docs/13 §4.4「追溯元数据」）。
    # 只做观测与追溯：卡位的互斥仍由 slots.yaml 静态声明 + Agent 单队列 + 上面的
    # 活动租约唯一索引保证，数据库层不新增卡位互斥约束（docs/04 §4.1 明确无 slot 表）。
    slot_id = Column(String(64), nullable=True, index=True)
    accelerator_model = Column(String(64), nullable=True)
    accelerator_vendor = Column(String(32), nullable=True)
    device_ids = Column(String(128), nullable=True)
    agent_endpoint = Column(String(255), nullable=True)
    image_ref = Column(String(255), nullable=True)
    allocated_at = Column(DateTime, nullable=False, default=utcnow)
    heartbeat_at = Column(DateTime, nullable=False, default=utcnow)
    released_at = Column(DateTime, nullable=True)
