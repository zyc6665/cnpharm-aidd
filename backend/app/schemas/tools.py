# backend/app/schemas/tools.py
"""工具相关Schema"""

from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.common import TimestampMixin
from app.schemas.statistics import ToolStatisticsResponse


# === 枚举类型定义 ===
ProviderType = Literal["platform", "user"]
ReviewStatus = Literal["not_required", "pending", "approved", "rejected"]


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
    changelog: Optional[str] = Field(None, description="版本更新日志")
    notes: Optional[str] = Field(None, description="版本说明")
    config: Dict[str, Any] = Field(..., description="工具配置")
    is_active: bool = Field(default=True, description="是否激活")
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
    changelog: Optional[str] = None
    notes: Optional[str] = None
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
    category: Optional[str] = Field(None, max_length=50, description="工具分类")
    icon: Optional[str] = Field(None, max_length=100, description="图标(emoji或名称)")
    icon_url: Optional[str] = Field(None, max_length=500, description="图标URL")
    is_public: bool = Field(default=True, description="是否公开")
    gpu_required: bool = Field(default=False, description="是否需要GPU")
    gpu_memory_mb: int = Field(default=0, ge=0, description="GPU显存需求(MB)")
    timeout_sec: int = Field(default=600, ge=60, le=3600, description="超时时间(秒)")
    tag_ids: List[str] = Field(default_factory=list, description="标签ID列表")
    # 新增：工具提供者类型（仅管理员可指定为 platform）
    provider_type: Optional[ProviderType] = Field(None, description="工具提供者类型（仅管理员可指定）")
    # 初始版本
    initial_version: Optional[ToolVersionCreate] = Field(None, description="初始版本")


class ToolUpdate(BaseModel):
    """更新工具"""
    name: Optional[str] = Field(None, max_length=100, description="工具名称")
    description: Optional[str] = Field(None, description="工具描述")
    category: Optional[str] = Field(None, max_length=50, description="工具分类")
    icon: Optional[str] = Field(None, max_length=100, description="图标")
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
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    icon_url: Optional[str] = None
    status: str
    is_public: bool
    # 新增字段
    provider_type: str = "user"
    review_status: str = "pending"
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    reject_reason: Optional[str] = None
    provider_label: Optional[str] = None  # 前端展示用：官方/社区
    # 原有字段
    current_version_id: Optional[str] = None
    gpu_required: bool = False
    gpu_memory_mb: int = 0
    timeout_sec: int = 600
    tags: List[TagResponse] = Field(default_factory=list)
    current_version: Optional[ToolVersionResponse] = None
    statistics: Optional[ToolStatisticsResponse] = None

    class Config:
        from_attributes = True


class ToolListResponse(BaseModel):
    """工具列表响应"""
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    icon_url: Optional[str] = None
    status: str
    is_public: bool = True
    # 新增字段
    provider_type: str = "user"
    review_status: str = "pending"
    provider_label: Optional[str] = None  # 前端展示用：官方/社区
    owner_id: Optional[str] = None
    # 原有字段
    gpu_required: bool = False
    tags: List[TagResponse] = Field(default_factory=list)
    current_version: Optional[ToolVersionResponse] = None
    statistics: Optional[ToolStatisticsResponse] = None
    created_at: datetime

    class Config:
        from_attributes = True


# === 新增：审核相关 Schema ===

class ToolReviewRequest(BaseModel):
    """审核工具请求"""
    action: Literal["approve", "reject"] = Field(..., description="审核动作")
    reject_reason: Optional[str] = Field(None, description="拒绝原因（拒绝时必填）")


class ToolReviewResponse(BaseModel):
    """审核工具响应"""
    id: str
    review_status: str
    reviewed_at: Optional[datetime] = None
    reject_reason: Optional[str] = None


class SetPlatformToolRequest(BaseModel):
    """设置为平台官方工具请求"""
    is_platform: bool = Field(..., description="是否设为官方工具")
