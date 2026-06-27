"""工具 AIDD 能力注册模型 —— 将能力从静态硬编码迁移到数据库驱动。"""

from sqlalchemy import Boolean, Column, ForeignKey, JSON, String
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class ToolCapability(Base, UUIDMixin, TimestampMixin):
    """工具对 AIDD Agent 暴露的语义能力注册记录。

    每条记录描述一个工具在 AIDD 工作流中的角色：
    - 它接受哪些语义类型的输入
    - 它产生哪些语义类型的输出
    - 它属于哪个能力阶段（pocket_exploration / docking_scoring / …）
    """

    __tablename__ = "tool_capabilities"

    # nullable=True 用于内置虚拟工具（is_builtin=True），它们没有对应的 Tool 行
    tool_id = Column(
        String(36), ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=True, unique=True, index=True,
    )

    capability = Column(String(100), nullable=False, index=True)
    stage = Column(String(100), nullable=False)

    inputs = Column(JSON, nullable=False, default=list)
    # 每项: {semantic_type, field, required, accepted_extensions}

    outputs = Column(JSON, nullable=False, default=list)
    # 每项: {semantic_type, source, match, path, required}

    defaults = Column(JSON, nullable=False, default=dict)

    is_builtin = Column(Boolean, default=False, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)

    tool = relationship("Tool")
