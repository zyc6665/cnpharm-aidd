# backend/app/schemas/tools.py
"""工具相关Schema"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.common import TimestampMixin


class TagCreate(BaseModel):
    """创建标签"""
    name: str = Field(..., max_length=50, description="标签名称")
    description: Optional[str] = Field(None, max_length=200, description="描述")
    color: str = Field(default="#1890ff", description="颜色")


class TagResponse(TimestampMixin):
    """标签响应"""
    id: str
    name: str
    description: Optional[str]
    color: str
    sort_order: int

    class Config:
        from_attributes = True


class ToolVersionCreate(BaseModel):
    """创建工具版本"""
    version: str = Field(..., max_length=50, description="版本号")
    notes: Optional[str] = Field(None, description="版本说明")
    config: Dict[str, Any] = Field(..., description="工具配置")
    # config结构:
    # {
    #     "type": "remote_api|docker_image|python_script",
    #     "endpoint": "http://...",
    #     "method": "POST",
    #     "headers": {},
    #     "input_schema": {},
    #     "output_schema": {},
    # }


class ToolVersionResponse(TimestampMixin):
    """工具版本响应"""
    id: str
    tool_id: str
    version: str
    notes: Optional[str]
    config: Dict[str, Any]
    is_active: bool
    deprecated: bool

    class Config:
        from_attributes = True


class ToolCreate(BaseModel):
    """创建工具"""
    name: str = Field(..., max_length=100, description="工具名称")
    slug: str = Field(..., max_length=100, pattern="^[a-z0-9-]+$", description="工具标识")
    description: Optional[str] = Field(None, description="工具描述")
    icon_url: Optional[str] = Field(None, max_length=500, description="图标URL")
    is_public: bool = Field(default=True, description="是否公开")
    gpu_required: bool = Field(default=False, description="是否需要GPU")
    gpu_memory_mb: int = Field(default=0, ge=0, description="GPU显存需求(MB)")
    timeout_sec: int = Field(default=600, ge=60, le=3600, description="超时时间(秒)")
    tag_ids: List[str] = Field(default_factory=list, description="标签ID列表")
    # 初始版本
    initial_version: Optional[ToolVersionCreate] = Field(None, description="初始版本")


class ToolUpdate(BaseModel):
    """更新工具"""
    name: Optional[str] = Field(None, max_length=100, description="工具名称")
    description: Optional[str] = Field(None, description="工具描述")
    icon_url: Optional[str] = Field(None, max_length=500, description="图标URL")
    is_public: Optional[bool] = Field(None, description="是否公开")
    status: Optional[str] = Field(None, description="状态")
    gpu_required: Optional[bool] = Field(None, description="是否需要GPU")
    gpu_memory_mb: Optional[int] = Field(None, ge=0, description="GPU显存需求(MB)")
    timeout_sec: Optional[int] = Field(None, ge=60, le=3600, description="超时时间(秒)")
    tag_ids: Optional[List[str]] = Field(None, description="标签ID列表")


class ToolResponse(TimestampMixin):
    """工具响应"""
    id: str
    owner_id: str
    name: str
    slug: str
    description: Optional[str]
    icon_url: Optional[str]
    status: str
    is_public: bool
    current_version_id: Optional[str]
    usage_count: int
    favorite_count: int
    gpu_required: bool
    gpu_memory_mb: int
    timeout_sec: int
    tags: List[TagResponse] = Field(default_factory=list)
    current_version: Optional[ToolVersionResponse] = None

    class Config:
        from_attributes = True


class ToolListResponse(BaseModel):
    """工具列表响应"""
    id: str
    name: str
    slug: str
    description: Optional[str]
    icon_url: Optional[str]
    status: str
    usage_count: int
    favorite_count: int
    gpu_required: bool
    tags: List[TagResponse] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True
