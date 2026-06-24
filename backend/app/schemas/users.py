# backend/app/schemas/users.py
"""用户相关Schema"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator
from app.schemas.common import TimestampMixin
from app.schemas.statistics import UserStatisticsResponse


class UserCreate(BaseModel):
    """用户注册"""
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    display_name: Optional[str] = Field(None, max_length=100, description="显示名称")
    verification_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="邮箱验证码"
    )


class UserLogin(BaseModel):
    """用户登录"""
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., description="密码")


class UserUpdate(BaseModel):
    """用户更新"""
    display_name: Optional[str] = Field(None, max_length=100, description="显示名称")
    avatar_url: Optional[str] = Field(None, max_length=500, description="头像URL")


class UserResponse(TimestampMixin):
    """用户响应"""
    id: str
    email: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    role: str
    status: str
    daily_task_limit: int
    max_file_size_mb: int
    statistics: Optional[UserStatisticsResponse] = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        """兼容旧状态值，统一对外返回当前枚举。"""
        legacy_status_map = {
            "inactive": "disabled",
            "banned": "disabled",
        }
        return legacy_status_map.get(value, value)

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Token响应"""
    access_token: str = Field(..., description="访问令牌")
    refresh_token: str = Field(..., description="刷新令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间(秒)")
    user: UserResponse = Field(..., description="用户信息")


class GuestSessionResponse(BaseModel):
    """游客会话响应"""
    session_id: str = Field(..., description="会话ID")
    expires_in: int = Field(..., description="过期时间(秒)")
    limitations: dict = Field(..., description="限制信息")


class PasswordChange(BaseModel):
    """修改密码"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")
