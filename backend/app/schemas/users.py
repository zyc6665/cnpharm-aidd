# backend/app/schemas/users.py
"""用户相关Schema"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator
from app.schemas.common import TimestampMixin
from app.schemas.statistics import UserStatisticsResponse
from app.pwdpolicy import (
    MAX_BCRYPT_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    validate_password_policy,
)


class UserCreate(BaseModel):
    """用户注册"""
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_BCRYPT_PASSWORD_BYTES,
        description="密码",
    )
    display_name: Optional[str] = Field(None, max_length=100, description="显示名称")
    verification_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="邮箱验证码"
    )

    @field_validator("password")
    @classmethod
    def _validate_password_policy(cls, value: str) -> str:
        """最小长度 12 + bcrypt 72 字节上限，超限返回 422 而非 500。"""
        return validate_password_policy(value)


class UserLogin(BaseModel):
    """用户登录（登录标识为 username；email 不再作为凭证）"""
    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    password: str = Field(..., description="密码")


class UserUpdate(BaseModel):
    """用户更新"""
    display_name: Optional[str] = Field(None, max_length=100, description="显示名称")
    avatar_url: Optional[str] = Field(None, max_length=500, description="头像URL")


class UserResponse(TimestampMixin):
    """用户响应（email 可为空：LDAP 用户不落邮箱）"""
    id: str
    username: str
    auth_source: str
    email: Optional[str] = None
    last_login_at: Optional[datetime] = None
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


class PasswordChange(BaseModel):
    """修改密码"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_BCRYPT_PASSWORD_BYTES,
        description="新密码",
    )

    @field_validator("new_password")
    @classmethod
    def _validate_new_password_policy(cls, value: str) -> str:
        """新口令同样受 12 位 + 72 字节约束。"""
        return validate_password_policy(value)
