# backend/app/schemas/verification.py
"""验证码相关Schema"""

from typing import Literal
from pydantic import BaseModel, Field, EmailStr


class SendCodeRequest(BaseModel):
    """发送验证码请求"""
    email: EmailStr = Field(..., description="邮箱地址")
    purpose: Literal["register", "reset_password"] = Field(
        ...,
        description="验证码用途: register(注册), reset_password(重置密码)"
    )


class SendCodeResponse(BaseModel):
    """发送验证码响应"""
    message: str = Field(..., description="响应消息")
    expires_in: int = Field(..., description="验证码有效期(秒)")


class VerifyCodeRequest(BaseModel):
    """验证验证码请求"""
    email: EmailStr = Field(..., description="邮箱地址")
    code: str = Field(..., min_length=6, max_length=6, description="验证码")
    purpose: Literal["register", "reset_password"] = Field(
        ...,
        description="验证码用途"
    )


class VerifyCodeResponse(BaseModel):
    """验证验证码响应"""
    valid: bool = Field(..., description="验证码是否有效")
    message: str = Field(..., description="响应消息")


class PasswordResetRequest(BaseModel):
    """密码重置请求"""
    email: EmailStr = Field(..., description="邮箱地址")
    code: str = Field(..., min_length=6, max_length=6, description="验证码")
    new_password: str = Field(
        ...,
        min_length=6,
        max_length=100,
        description="新密码"
    )
