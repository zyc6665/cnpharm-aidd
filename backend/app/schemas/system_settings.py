"""Runtime system setting schemas."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


ProviderType = Literal["openai_compatible"]


class ModelServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    provider_type: ProviderType = "openai_compatible"
    base_url: str = Field(..., min_length=1, max_length=500)
    api_key: Optional[str] = None
    model_name: str = Field(..., min_length=1, max_length=200)
    is_default: bool = False
    is_enabled: bool = True
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    max_tokens: int = Field(default=2048, ge=1, le=200000)
    temperature: float = Field(default=0.2, ge=0, le=2)


class ModelServiceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    provider_type: Optional[ProviderType] = None
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    api_key: Optional[str] = None
    model_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    is_default: Optional[bool] = None
    is_enabled: Optional[bool] = None
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=600)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=200000)
    temperature: Optional[float] = Field(default=None, ge=0, le=2)


class ModelServiceResponse(BaseModel):
    id: str
    name: str
    provider_type: str
    base_url: str
    model_name: str
    is_default: bool
    is_enabled: bool
    timeout_seconds: int
    max_tokens: int
    temperature: float
    has_api_key: bool
    api_key_masked: Optional[str] = None
    last_test_status: Optional[str] = None
    last_test_message: Optional[str] = None
    last_tested_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ModelServiceTestResponse(BaseModel):
    id: str
    success: bool
    message: str
    last_test_status: str
    last_tested_at: datetime
