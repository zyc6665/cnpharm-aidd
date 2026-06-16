"""工作流定义模型"""

from sqlalchemy import Column, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class WorkflowDefinition(Base, UUIDMixin, TimestampMixin):
    """用户保存的工作流画布定义。"""

    __tablename__ = "workflow_definitions"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=True)
    template_id = Column(String(120), nullable=False, index=True)
    nodes = Column(JSON, nullable=False, default=list)
    edges = Column(JSON, nullable=False, default=list)
    selected_tool_by_node = Column(JSON, nullable=False, default=dict)
    artifact_bindings_by_node = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="draft", index=True)

    user = relationship("User")
