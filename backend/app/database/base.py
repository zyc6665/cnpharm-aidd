# backend/app/database/base.py
"""SQLAlchemy Base类和Mixin"""

import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import declarative_base, declared_attr


class CustomBase:
    """自定义Base类"""

    @declared_attr
    def __tablename__(cls) -> str:
        """自动生成表名（类名的蛇形命名）"""
        import re
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
        return name

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


Base = declarative_base(cls=CustomBase)


class TimestampMixin:
    """时间戳Mixin"""
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UUIDMixin:
    """UUID主键Mixin"""
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
