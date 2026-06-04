"""Runtime system setting models."""

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.database.base import Base, TimestampMixin, UUIDMixin


class ModelService(Base, UUIDMixin, TimestampMixin):
    """Administrator-managed OpenAI-compatible model service."""

    __tablename__ = "model_services"

    name = Column(String(100), nullable=False)
    provider_type = Column(String(50), nullable=False, default="openai_compatible")
    base_url = Column(String(500), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)
    model_name = Column(String(200), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False, index=True)
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    timeout_seconds = Column(Integer, nullable=False, default=60)
    max_tokens = Column(Integer, nullable=False, default=2048)
    temperature = Column(Float, nullable=False, default=0.2)
    last_test_status = Column(String(32), nullable=True)
    last_test_message = Column(Text, nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
