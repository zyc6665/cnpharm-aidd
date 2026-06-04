# backend/app/schemas/tools.py
"""工具相关Schema"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.common import TimestampMixin
from app.schemas.files import FileUploadResponse
from app.schemas.statistics import ToolStatisticsResponse


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
    #     "type": "remote_api|docker_image|python_script|ssh_job",
    #     "endpoint": "http://...",
    #     "method": "POST",
    #     "headers": {},
    #     "host": "gpu-node-01",  # ssh_job
    #     "entrypoint": "/app/platform_run.sh",  # ssh_job
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


class ToolCategoryCreate(BaseModel):
    """创建工具分类"""
    name: str = Field(..., max_length=100, description="分类名称")
    slug: str = Field(..., max_length=100, pattern="^[a-z0-9-]+$", description="分类标识")
    description: Optional[str] = Field(None, description="分类描述")
    sort_order: int = Field(default=0, description="排序值")
    is_enabled: bool = Field(default=True, description="是否启用")


class ToolCategoryUpdate(BaseModel):
    """更新工具分类"""
    name: Optional[str] = Field(None, max_length=100, description="分类名称")
    slug: Optional[str] = Field(None, max_length=100, pattern="^[a-z0-9-]+$", description="分类标识")
    description: Optional[str] = Field(None, description="分类描述")
    sort_order: Optional[int] = Field(None, description="排序值")


class ToolCategoryStatusUpdate(BaseModel):
    """更新工具分类状态"""
    is_enabled: bool = Field(..., description="是否启用")


class ToolCategoryReorderRequest(BaseModel):
    """工具分类重排请求"""
    category_ids: List[str] = Field(..., min_length=1, description="按顺序排列的分类ID列表")


class ToolCategoryResponse(TimestampMixin):
    """工具分类响应"""
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    sort_order: int
    is_enabled: bool
    tool_count: Optional[int] = None

    class Config:
        from_attributes = True


class ToolWorkbenchGroupCreate(BaseModel):
    """创建工具工作台分组"""
    name: str = Field(..., max_length=100, description="分组名称")
    slug: str = Field(..., max_length=100, pattern="^[a-z0-9-]+$", description="分组标识")
    description: Optional[str] = Field(None, description="分组描述")
    sort_order: int = Field(default=0, ge=0, description="排序值")
    is_enabled: bool = Field(default=True, description="是否启用")


class ToolWorkbenchGroupUpdate(BaseModel):
    """更新工具工作台分组"""
    name: Optional[str] = Field(None, max_length=100, description="分组名称")
    slug: Optional[str] = Field(None, max_length=100, pattern="^[a-z0-9-]+$", description="分组标识")
    description: Optional[str] = Field(None, description="分组描述")
    sort_order: Optional[int] = Field(None, ge=0, description="排序值")
    is_enabled: Optional[bool] = Field(None, description="是否启用")


class ToolWorkbenchGroupResponse(TimestampMixin):
    """工具工作台分组响应"""
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    sort_order: int
    is_enabled: bool

    class Config:
        from_attributes = True


class ToolWorkbenchGroupReorderRequest(BaseModel):
    """工具工作台分组重排请求"""
    group_ids: List[str] = Field(..., min_length=1, description="按顺序排列的分组ID列表")


class ToolWorkbenchGroupMappingCreate(BaseModel):
    """创建工具工作台分组映射"""
    tool_id: str = Field(..., description="工具ID")
    group_id: str = Field(..., description="工作台分组ID")
    sort_order: int = Field(default=0, ge=0, description="排序值")
    is_recommended: bool = Field(default=False, description="是否推荐")
    is_enabled: bool = Field(default=True, description="是否启用")


class ToolWorkbenchGroupMappingUpdate(BaseModel):
    """更新工具工作台分组映射"""
    tool_id: Optional[str] = Field(None, description="工具ID")
    group_id: Optional[str] = Field(None, description="工作台分组ID")
    sort_order: Optional[int] = Field(None, ge=0, description="排序值")
    is_recommended: Optional[bool] = Field(None, description="是否推荐")
    is_enabled: Optional[bool] = Field(None, description="是否启用")


class ToolWorkbenchGroupMappingResponse(TimestampMixin):
    """工具工作台分组映射响应"""
    id: str
    tool_id: str
    group_id: str
    sort_order: int
    is_recommended: bool
    is_enabled: bool

    class Config:
        from_attributes = True


class ToolWorkbenchGroupToolResponse(BaseModel):
    """工作台分组中的工具摘要响应"""
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    category_id: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    icon_url: Optional[str] = None
    status: str
    is_public: bool
    is_recommended: bool = False
    sort_order: int = 0


class ToolWorkbenchGroupPublicResponse(TimestampMixin):
    """公开工具工作台分组响应"""
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    sort_order: int
    tools: List[ToolWorkbenchGroupToolResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ToolCreate(BaseModel):
    """创建工具"""
    name: str = Field(..., max_length=100, description="工具名称")
    slug: str = Field(..., max_length=100, pattern="^[a-z0-9-]+$", description="工具标识")
    description: Optional[str] = Field(None, description="工具描述")
    category_id: str = Field(..., description="工具分类ID")
    category: Optional[str] = Field(None, max_length=50, description="工具分类")
    icon: Optional[str] = Field(None, max_length=100, description="图标(emoji或名称)")
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
    category_id: Optional[str] = Field(None, description="工具分类ID")
    category: Optional[str] = Field(None, max_length=50, description="工具分类")
    icon: Optional[str] = Field(None, max_length=100, description="图标")
    icon_url: Optional[str] = Field(None, max_length=500, description="图标URL")
    is_public: Optional[bool] = Field(None, description="是否公开")
    status: Optional[str] = Field(None, description="状态")
    gpu_required: Optional[bool] = Field(None, description="是否需要GPU")
    gpu_memory_mb: Optional[int] = Field(None, ge=0, description="GPU显存需求(MB)")
    timeout_sec: Optional[int] = Field(None, ge=60, le=3600, description="超时时间(秒)")
    tag_ids: Optional[List[str]] = Field(None, description="标签ID列表")


class ToolImportRequest(BaseModel):
    """导入平台工具配置。"""
    config: Dict[str, Any] = Field(..., description="platform_tool.json 内容")
    category_id: Optional[str] = Field(None, description="导入后绑定的工具分类ID")
    publish: bool = Field(default=False, description="导入后是否直接发布")


class ToolExampleFileResponse(BaseModel):
    """工具示例文件响应。"""
    field: str
    path: str
    filename: str
    size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    exists: bool = False
    previewable: bool = False


class ToolExampleResponse(BaseModel):
    """工具示例响应。"""
    name: str
    description: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    input_files: List[ToolExampleFileResponse] = Field(default_factory=list)


class ToolExampleApplyResponse(BaseModel):
    """工具示例应用响应。"""
    params: Dict[str, Any] = Field(default_factory=dict)
    files: Dict[str, FileUploadResponse] = Field(default_factory=dict)


class ToolExampleFilePreviewResponse(BaseModel):
    """工具示例文件预览响应。"""
    field: str
    filename: str
    content_type: Optional[str] = None
    content: Optional[str] = None
    truncated: bool = False
    previewable: bool = False


class ToolResponse(TimestampMixin):
    """工具响应"""
    id: str
    owner_id: str
    name: str
    slug: str
    description: Optional[str] = None
    category_id: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    icon_url: Optional[str] = None
    status: str
    is_public: bool
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
    category_id: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    icon_url: Optional[str] = None
    status: str
    is_public: bool = True
    owner_id: Optional[str] = None
    # 原有字段
    gpu_required: bool = False
    tags: List[TagResponse] = Field(default_factory=list)
    current_version: Optional[ToolVersionResponse] = None
    statistics: Optional[ToolStatisticsResponse] = None
    created_at: datetime

    class Config:
        from_attributes = True
