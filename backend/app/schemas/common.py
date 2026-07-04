# backend/app/schemas/common.py
"""通用Schema"""

from datetime import datetime
from typing import TypeVar, Generic, Optional, List, Any

from pydantic import BaseModel, ConfigDict, Field


class BaseResponse(BaseModel):
    """基础响应"""
    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="消息")
    data: Optional[Any] = Field(default=None, description="数据")


class PaginationParams(BaseModel):
    """分页参数"""
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


DataT = TypeVar("DataT")


class PaginatedResponse(BaseModel, Generic[DataT]):
    """分页响应"""
    items: List[DataT] = Field(default_factory=list, description="数据列表")
    total: int = Field(default=0, description="总数")
    page: int = Field(default=1, description="当前页")
    page_size: int = Field(default=20, description="每页数量")
    total_pages: int = Field(default=0, description="总页数")

    @classmethod
    def create(
        cls,
        items: List[DataT],
        total: int,
        page: int,
        page_size: int
    ) -> "PaginatedResponse[DataT]":
        total_pages = (total + page_size - 1) // page_size if total and page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )


class TimestampMixin(BaseModel):
    """时间戳Mixin"""
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
