# backend/app/api/v1/auth.py
"""认证API"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.database.session import get_db
from app.models.users import User, UserRole, UserSession
from app.auth.jwt_handler import JWTHandler
from app.auth.password import hash_password, verify_password
from app.auth.dependencies import get_current_user
from app.schemas.users import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    UserUpdate, PasswordChange
)
from app.common.responses import success_response, error_response
from app.common.exceptions import (
    UnauthorizedException, ValidationException,
    ConflictException, NotFoundException
)

router = APIRouter()
jwt_handler = JWTHandler()


@router.post("/register", response_model=dict)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """用户注册"""
    # 检查邮箱是否已存在
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise ConflictException("邮箱已被注册")

    # 检查用户名是否已存在
    result = await db.execute(
        select(User).where(User.username == user_data.username)
    )
    if result.scalar_one_or_none():
        raise ConflictException("用户名已被使用")

    # 创建用户
    hashed_pwd = hash_password(user_data.password)
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_pwd,
        nickname=user_data.nickname or user_data.username,
        role=UserRole.USER
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 生成令牌
    access_token = jwt_handler.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value
    )
    refresh_token = jwt_handler.create_refresh_token(user_id=user.id)

    return success_response(
        data={
            "user": UserResponse.model_validate(user).model_dump(),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        },
        message="注册成功"
    )


@router.post("/login", response_model=dict)
async def login(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """用户登录"""
    # 查找用户（支持邮箱或用户名登录）
    result = await db.execute(
        select(User).where(
            (User.email == login_data.email_or_username) |
            (User.username == login_data.email_or_username)
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException("用户不存在")

    if not user.is_active:
        raise UnauthorizedException("账户已被禁用")

    # 验证密码
    if not verify_password(login_data.password, user.hashed_password):
        raise UnauthorizedException("密码错误")

    # 生成令牌
    access_token = jwt_handler.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value
    )
    refresh_token = jwt_handler.create_refresh_token(user_id=user.id)

    return success_response(
        data={
            "user": UserResponse.model_validate(user).model_dump(),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        },
        message="登录成功"
    )


@router.post("/refresh", response_model=dict)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """刷新令牌"""
    try:
        payload = jwt_handler.verify_token(refresh_token, token_type="refresh")
    except Exception:
        raise UnauthorizedException("无效的刷新令牌")

    user_id = payload.get("sub")

    # 查找用户
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise UnauthorizedException("用户不存在或已被禁用")

    # 生成新令牌
    new_access_token = jwt_handler.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value
    )
    new_refresh_token = jwt_handler.create_refresh_token(user_id=user.id)

    return success_response(
        data={
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        },
        message="令牌刷新成功"
    )


@router.get("/me", response_model=dict)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """获取当前用户信息"""
    return success_response(
        data=UserResponse.model_validate(current_user).model_dump()
    )


@router.put("/me", response_model=dict)
async def update_current_user(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新当前用户信息"""
    update_data = user_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return success_response(
        data=UserResponse.model_validate(current_user).model_dump(),
        message="更新成功"
    )


@router.post("/change-password", response_model=dict)
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """修改密码"""
    # 验证旧密码
    if not verify_password(
        password_data.old_password,
        current_user.hashed_password
    ):
        raise ValidationException("旧密码错误")

    # 更新密码
    current_user.hashed_password = hash_password(
        password_data.new_password
    )

    await db.commit()

    return success_response(message="密码修改成功")


@router.post("/logout", response_model=dict)
async def logout(
    current_user: User = Depends(get_current_user)
):
    """登出（客户端清除令牌即可）"""
    return success_response(message="登出成功")
