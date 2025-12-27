# backend/app/schemas/files.py
"""文件相关Schema"""

from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.common import TimestampMixin
from app.schemas.statistics import FileStatisticsResponse


class FileResponse(TimestampMixin):
    """文件响应"""
    id: str
    filename: str
    content_type: Optional[str]
    size_bytes: int
    source_type: str
    is_public: bool
    expires_at: Optional[datetime]
    statistics: Optional[FileStatisticsResponse] = None

    class Config:
        from_attributes = True


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    id: str
    filename: str
    size_bytes: int
    content_type: Optional[str]
    sha256: str


class FileDownloadUrl(BaseModel):
    """文件下载URL"""
    url: str = Field(..., description="下载URL")
    expires_in: int = Field(..., description="过期时间(秒)")
