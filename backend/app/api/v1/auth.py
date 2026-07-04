# backend/app/api/v1/auth.py
"""认证API"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database.session import get_db
from app.models.users import User, UserRole, UserStatus
from app.auth.jwt_handler import JWTHandler
from app.auth.password import hash_password, verify_password
from app.auth.dependencies import get_current_user
from app.schemas.users import (
    UserCreate, UserLogin, UserResponse,
)
from app.schemas.verification import PasswordResetRequest
from app.services.verification.service import (
    get_verification_service,
    InvalidCodeError
)
from app.common.responses import success_response
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
    """
    用户注册

    需要先调用 /verification/send-code 获取验证码。

    - **email**: 邮箱地址
    - **password**: 密码（6-100 位）
    - **display_name**: 显示名称（可选）
    - **verification_code**: 邮箱验证码（6 位）
    """
    # 验证验证码
    verification_service = await get_verification_service(db)
    try:
        await verification_service.verify_code(
            email=user_data.email,
            code=user_data.verification_code,
            purpose="register",
            mark_used=True
        )
    except InvalidCodeError as e:
        raise ValidationException(str(e))

    # 检查邮箱是否已存在
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if result.scalar_one_or_none():
        raise ConflictException("邮箱已被注册")

    # 创建用户
    hashed_pwd = hash_password(user_data.password)
    user = User(
        email=user_data.email,
        password_hash=hashed_pwd,
        display_name=user_data.display_name,
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 生成令牌
    access_token = jwt_handler.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role
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
    """
    用户登录

    - **email**: 邮箱地址
    - **password**: 密码
    """
    # 查找用户
    result = await db.execute(
        select(User)
        .options(joinedload(User.statistics))
        .where(User.email == login_data.email)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException("用户不存在")

    if user.status != UserStatus.ACTIVE.value:
        raise UnauthorizedException("账户已被禁用")

    # 验证密码
    if not verify_password(login_data.password, user.password_hash):
        raise UnauthorizedException("密码错误")

    # 生成令牌
    access_token = jwt_handler.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role
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


@router.post("/reset-password", response_model=dict)
async def reset_password(
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    重置密码

    需要先调用 /verification/send-code 获取验证码（purpose=reset_password）。

    - **email**: 邮箱地址
    - **code**: 验证码
    - **new_password**: 新密码
    """
    # 验证验证码
    verification_service = await get_verification_service(db)
    try:
        await verification_service.verify_code(
            email=data.email,
            code=data.code,
            purpose="reset_password",
            mark_used=True
        )
    except InvalidCodeError as e:
        raise ValidationException(str(e))

    # 查找用户
    result = await db.execute(
        select(User).where(User.email == data.email)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise NotFoundException("用户不存在")

    # 更新密码
    user.password_hash = hash_password(data.new_password)
    await db.commit()

    return success_response(message="密码重置成功")


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

    if not user or user.status != UserStatus.ACTIVE.value:
        raise UnauthorizedException("用户不存在或已被禁用")

    # 生成新令牌
    new_access_token = jwt_handler.create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role
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


@router.post("/logout", response_model=dict)
async def logout(
    current_user: User = Depends(get_current_user)
):
    """登出（客户端清除令牌即可）"""
    return success_response(message="登出成功")
