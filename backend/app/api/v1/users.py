# backend/app/api/v1/users.py
"""用户管理接口"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, update
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database.session import get_db
from app.models.users import User, UserRole
from app.auth.dependencies import get_current_user, get_admin_user
from app.auth.password import hash_password, verify_password
from app.schemas.users import UserResponse

router = APIRouter()


# ==================== Schemas ====================

class UserUpdate(BaseModel):
    """用户信息更新"""
    email: Optional[str] = Field(None, description="邮箱")
    phone: Optional[str] = Field(None, description="手机号")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    bio: Optional[str] = Field(None, description="个人简介")


class PasswordChange(BaseModel):
    """密码修改"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=50, description="新密码")


class AdminUserUpdate(BaseModel):
    """管理员更新用户信息"""
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = Field(None, description="角色: user, vip, admin")
    status: Optional[str] = Field(None, description="状态: active, inactive, banned")
    credit_balance: Optional[int] = Field(None, ge=0, description="积分余额")


class UserListResponse(BaseModel):
    """用户列表响应"""
    total: int
    items: List[UserResponse]
    page: int
    page_size: int


class UserStatsResponse(BaseModel):
    """用户统计响应"""
    total_users: int
    active_users: int
    vip_users: int
    admin_users: int
    new_users_today: int
    new_users_this_week: int


# ==================== 当前用户接口 ====================

@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """获取当前登录用户的详细信息"""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse, summary="更新当前用户信息")
async def update_current_user_info(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新当前登录用户的信息

    可更新字段：
    - email: 邮箱
    - phone: 手机号
    - avatar_url: 头像URL
    - bio: 个人简介
    """
    update_data = user_update.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有提供需要更新的字段"
        )

    # 检查邮箱唯一性
    if "email" in update_data and update_data["email"]:
        result = await db.execute(
            select(User).where(
                User.email == update_data["email"],
                User.id != current_user.id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该邮箱已被使用"
            )

    # 更新用户信息
    for key, value in update_data.items():
        setattr(current_user, key, value)

    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)

    return UserResponse.model_validate(current_user)


@router.put("/me/password", summary="修改密码")
async def change_password(
    password_change: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """修改当前用户的密码"""
    # 验证旧密码
    if not verify_password(password_change.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码不正确"
        )

    # 更新密码
    current_user.password_hash = hash_password(password_change.new_password)
    current_user.updated_at = datetime.utcnow()
    await db.commit()

    return {"message": "密码修改成功"}


# ==================== 管理员接口 ====================

@router.get(
    "/admin",
    response_model=UserListResponse,
    summary="获取用户列表（管理员）"
)
async def admin_get_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(None, description="搜索关键词（用户名/邮箱）"),
    role: Optional[str] = Query(None, description="角色筛选"),
    status_filter: Optional[str] = Query(None, alias="status", description="状态筛选"),
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户列表（仅管理员可访问）

    支持：
    - 关键词搜索
    - 角色筛选
    - 状态筛选
    - 分页
    """
    # 构建查询
    query = select(User).options(joinedload(User.statistics))

    # 关键词搜索
    if keyword:
        query = query.where(
            (User.username.ilike(f"%{keyword}%")) |
            (User.email.ilike(f"%{keyword}%"))
        )

    # 角色筛选
    if role:
        query = query.where(User.role == role)

    # 状态筛选
    if status_filter:
        query = query.where(User.status == status_filter)

    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(User.created_at.desc())

    result = await db.execute(query)
    users = result.scalars().all()

    return UserListResponse(
        total=total,
        items=[UserResponse.model_validate(u) for u in users],
        page=page,
        page_size=page_size
    )


@router.get(
    "/admin/{user_id}",
    response_model=UserResponse,
    summary="获取用户详情（管理员）"
)
async def admin_get_user(
    user_id: str,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取指定用户的详细信息（仅管理员可访问）"""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    return UserResponse.model_validate(user)


@router.patch(
    "/admin/{user_id}",
    response_model=UserResponse,
    summary="更新用户信息（管理员）"
)
async def admin_update_user(
    user_id: str,
    user_update: AdminUserUpdate,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新指定用户的信息（仅管理员可访问）

    可更新字段：
    - email: 邮箱
    - phone: 手机号
    - role: 角色
    - status: 状态
    - credit_balance: 积分余额
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    # 不允许管理员修改自己的角色
    if user_id == admin_user.id and user_update.role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不允许修改自己的角色"
        )

    update_data = user_update.model_dump(exclude_unset=True)

    # 验证角色
    if "role" in update_data:
        valid_roles = [r.value for r in UserRole]
        if update_data["role"] not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的角色，可选值: {valid_roles}"
            )

    # 验证状态
    if "status" in update_data:
        valid_statuses = ["active", "inactive", "banned"]
        if update_data["status"] not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的状态，可选值: {valid_statuses}"
            )

    # 更新用户信息
    for key, value in update_data.items():
        setattr(user, key, value)

    user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.delete(
    "/admin/{user_id}",
    summary="删除用户（管理员）"
)
async def admin_delete_user(
    user_id: str,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    删除指定用户（仅管理员可访问）

    注意：实际上是将用户状态设置为 banned，而不是物理删除
    """
    if user_id == admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不允许删除自己的账号"
        )

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    # 软删除：设置状态为 banned
    user.status = "banned"
    user.updated_at = datetime.utcnow()
    await db.commit()

    return {"message": "用户已删除"}


@router.get(
    "/admin/stats",
    response_model=UserStatsResponse,
    summary="获取用户统计（管理员）"
)
async def admin_get_user_stats(
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户统计信息（仅管理员可访问）"""
    from datetime import timedelta

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    # 总用户数
    total_result = await db.execute(select(func.count(User.id)))
    total_users = total_result.scalar()

    # 活跃用户数
    active_result = await db.execute(
        select(func.count(User.id)).where(User.status == "active")
    )
    active_users = active_result.scalar()

    # VIP 用户数
    vip_result = await db.execute(
        select(func.count(User.id)).where(User.role == UserRole.VIP.value)
    )
    vip_users = vip_result.scalar()

    # 管理员数
    admin_result = await db.execute(
        select(func.count(User.id)).where(User.role == UserRole.ADMIN.value)
    )
    admin_users = admin_result.scalar()

    # 今日新增用户
    today_result = await db.execute(
        select(func.count(User.id)).where(User.created_at >= today_start)
    )
    new_users_today = today_result.scalar()

    # 本周新增用户
    week_result = await db.execute(
        select(func.count(User.id)).where(User.created_at >= week_start)
    )
    new_users_this_week = week_result.scalar()

    return UserStatsResponse(
        total_users=total_users,
        active_users=active_users,
        vip_users=vip_users,
        admin_users=admin_users,
        new_users_today=new_users_today,
        new_users_this_week=new_users_this_week
    )
