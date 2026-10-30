# backend/app/api/v1/users.py
"""用户管理接口"""

from typing import Optional, List, Literal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, or_, delete, update
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator

from app.common.time import utcnow
from app.common.exceptions import BusinessException
from app.database.session import get_db
from app.models.files import File, FileAccessLog
from app.models.statistics import FileStatistics, ToolStatistics, UserStatistics
from app.models.tasks import Task, TaskInput, TaskOutput, TaskLog
from app.models.tools import Tool, ToolFavorite, ToolVersion, tool_tag_association
from app.models.users import User, UserRole, UserStatus
from app.models.workflows import ResearchBoard, WorkflowDefinition, WorkflowRun
from app.auth.dependencies import get_current_user, get_admin_user
from app.auth.password import (
    MAX_BCRYPT_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    hash_password,
    validate_password_policy,
    verify_password,
)
from app.common.responses import success_response
from app.common.search import DEFAULT_KEYWORD_MAX_LENGTH, LIKE_ESCAPE, like_pattern
from app.logging.audit import AuditAction, ResourceType, get_audit_logger
from app.schemas.users import UserResponse

router = APIRouter()


# ==================== Schemas ====================

class UserUpdate(BaseModel):
    """用户信息更新"""
    email: Optional[str] = Field(None, description="邮箱")
    phone: Optional[str] = Field(None, description="手机号")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    bio: Optional[str] = Field(None, description="个人简介")

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email_to_none(cls, value):
        """前端清空邮箱会下发空串；归一为 None，避免触发唯一/格式校验。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value


class PasswordChange(BaseModel):
    """密码修改"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_BCRYPT_PASSWORD_BYTES,
        description="新密码",
    )

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, value: str) -> str:
        """沿用统一口令策略（最小 12 位 + bcrypt 72 字节）。"""
        return validate_password_policy(value)


class AdminUserUpdate(BaseModel):
    """管理员更新用户信息"""
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = Field(None, description="角色: user, admin")
    status: Optional[str] = Field(None, description="状态: active, disabled, pending")

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email_to_none(cls, value):
        """前端清空邮箱会下发空串；归一为 None，避免触发唯一/格式校验。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value


class AdminUserCreate(BaseModel):
    """管理员创建用户"""
    username: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9._-]{1,64}$",
        description="登录用户名（大小写不敏感唯一）",
    )
    auth_source: Literal["local", "ldap"] = Field(
        default="local", description="认证源: local / ldap"
    )
    email: Optional[str] = Field(None, description="邮箱（可选；LDAP 用户可不落邮箱）")
    display_name: Optional[str] = Field(None, description="显示名称")
    password: Optional[str] = Field(
        None,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_BCRYPT_PASSWORD_BYTES,
        description="初始密码（local 必填；ldap 忽略）",
    )
    role: str = Field(default=UserRole.USER.value, description="角色: user, admin")
    status: str = Field(default=UserStatus.ACTIVE.value, description="状态: active, disabled, pending")

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: Optional[str]) -> Optional[str]:
        """仅 local 用户填写口令时校验；LDAP 用户传 None 直接放行。"""
        if value is None:
            return None
        return validate_password_policy(value)


class AdminPasswordReset(BaseModel):
    """管理员重置用户密码"""
    new_password: str = Field(
        ...,
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_BCRYPT_PASSWORD_BYTES,
        description="新密码",
    )

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, value: str) -> str:
        """管理员重置同样受统一口令策略约束。"""
        return validate_password_policy(value)


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
    admin_users: int
    new_users_today: int
    new_users_this_week: int


LEGACY_DISABLED_USER_STATUSES = ("inactive", "banned")


def normalize_user_status(status_value: Optional[str]) -> Optional[str]:
    """将旧状态值归一化为当前用户状态枚举。"""
    if status_value is None:
        return None

    legacy_status_map = {
        "inactive": UserStatus.DISABLED.value,
        "banned": UserStatus.DISABLED.value,
    }
    return legacy_status_map.get(status_value, status_value)


def validate_user_role(role_value: str) -> str:
    """校验用户角色。"""
    valid_roles = [role.value for role in UserRole]
    if role_value not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的角色，可选值: {valid_roles}"
        )
    return role_value


def validate_user_status(status_value: str) -> str:
    """校验并归一化用户状态。"""
    normalized_status = normalize_user_status(status_value)
    valid_statuses = [user_status.value for user_status in UserStatus]
    if normalized_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的状态，可选值: {valid_statuses}"
        )
    return normalized_status


async def load_user_with_statistics(db: AsyncSession, user_id: str) -> Optional[User]:
    """加载带统计信息的用户。"""
    result = await db.execute(
        select(User)
        .options(joinedload(User.statistics))
        .where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def ensure_user_email_unique(db: AsyncSession, email: str, exclude_user_id: Optional[str] = None) -> None:
    """确保用户邮箱唯一。"""
    filters = [User.email == email]
    if exclude_user_id:
        filters.append(User.id != exclude_user_id)

    result = await db.execute(select(User).where(*filters))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被使用"
        )


async def ensure_username_unique(
    db: AsyncSession, username: str, exclude_user_id: Optional[str] = None
) -> None:
    """确保用户名大小写不敏感唯一；冲突返回业务码 40002。"""
    filters = [func.lower(User.username) == username.lower()]
    if exclude_user_id:
        filters.append(User.id != exclude_user_id)

    result = await db.execute(select(User.id).where(*filters).limit(1))
    if result.first():
        raise BusinessException("该用户名已被使用", http_status=400, code=40002)


async def hard_delete_user_related_resources(db: AsyncSession, user_id: str) -> None:
    """彻底删除用户及其关联资源。"""
    await db.execute(
        update(Tool)
        .where(Tool.reviewed_by == user_id)
        .values(reviewed_by=None)
    )

    owned_tool_ids_result = await db.execute(select(Tool.id).where(Tool.owner_id == user_id))
    owned_tool_ids = owned_tool_ids_result.scalars().all()

    task_query = select(Task.id).where(Task.user_id == user_id)
    if owned_tool_ids:
        task_query = select(Task.id).where(
            or_(
                Task.user_id == user_id,
                Task.tool_id.in_(owned_tool_ids),
            )
        )
    task_ids_result = await db.execute(task_query)
    task_ids = task_ids_result.scalars().all()

    if task_ids:
        await db.execute(delete(TaskLog).where(TaskLog.task_id.in_(task_ids)))
        await db.execute(delete(TaskInput).where(TaskInput.task_id.in_(task_ids)))
        await db.execute(delete(TaskOutput).where(TaskOutput.task_id.in_(task_ids)))
        await db.execute(delete(Task).where(Task.id.in_(task_ids)))

    owned_file_ids_result = await db.execute(select(File.id).where(File.owner_id == user_id))
    owned_file_ids = owned_file_ids_result.scalars().all()

    file_access_log_filter = FileAccessLog.user_id == user_id
    if owned_file_ids:
        file_access_log_filter = or_(
            FileAccessLog.user_id == user_id,
            FileAccessLog.file_id.in_(owned_file_ids),
        )

    await db.execute(delete(FileAccessLog).where(file_access_log_filter))

    if owned_file_ids:
        await db.execute(delete(FileStatistics).where(FileStatistics.file_id.in_(owned_file_ids)))
        await db.execute(delete(File).where(File.id.in_(owned_file_ids)))

    await db.execute(delete(ToolFavorite).where(ToolFavorite.user_id == user_id))
    await db.execute(delete(WorkflowRun).where(WorkflowRun.owner_id == user_id))
    await db.execute(delete(WorkflowDefinition).where(WorkflowDefinition.user_id == user_id))
    await db.execute(delete(ResearchBoard).where(ResearchBoard.owner_id == user_id))

    if owned_tool_ids:
        await db.execute(delete(ToolFavorite).where(ToolFavorite.tool_id.in_(owned_tool_ids)))
        await db.execute(delete(tool_tag_association).where(tool_tag_association.c.tool_id.in_(owned_tool_ids)))
        await db.execute(delete(ToolStatistics).where(ToolStatistics.tool_id.in_(owned_tool_ids)))
        await db.execute(delete(ToolVersion).where(ToolVersion.tool_id.in_(owned_tool_ids)))
        await db.execute(delete(Tool).where(Tool.id.in_(owned_tool_ids)))

    await db.execute(delete(UserStatistics).where(UserStatistics.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))


# ==================== 当前用户接口 ====================

@router.get("/me", summary="获取当前用户信息")
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """获取当前登录用户的详细信息"""
    return success_response(UserResponse.model_validate(current_user).model_dump())


@router.patch("/me", summary="更新当前用户信息")
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
        await ensure_user_email_unique(db, update_data["email"], exclude_user_id=current_user.id)

    # 更新用户信息
    for key, value in update_data.items():
        setattr(current_user, key, value)

    current_user.updated_at = utcnow()
    await db.commit()
    await db.refresh(current_user)

    return success_response(UserResponse.model_validate(current_user).model_dump())


@router.put("/me/password", summary="修改密码")
async def change_password(
    password_change: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """修改当前用户的密码"""
    if current_user.auth_source == "ldap":
        raise BusinessException(
            "LDAP 用户的口令由企业目录管理，请在目录中修改",
            http_status=400,
            code=40002,
        )

    # 验证旧密码
    if not verify_password(password_change.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码不正确"
        )

    # 更新密码
    current_user.password_hash = hash_password(password_change.new_password)
    current_user.updated_at = utcnow()
    await db.commit()

    get_audit_logger().log_user_action(
        AuditAction.PASSWORD_CHANGE,
        user_id=str(current_user.id),
        resource_type=ResourceType.USER,
        resource_id=str(current_user.id),
    )

    return success_response(message="密码修改成功")


# ==================== 管理员接口 ====================

@router.post(
    "/admin",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="创建用户（管理员）"
)
async def admin_create_user(
    user_data: AdminUserCreate,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员直接创建用户。"""
    username = user_data.username.strip()
    await ensure_username_unique(db, username)
    if user_data.email:
        await ensure_user_email_unique(db, user_data.email)

    if user_data.auth_source == "local":
        if not user_data.password:
            raise BusinessException(
                "本地用户必须设置初始密码", http_status=400, code=40002
            )
        pwd_hash = hash_password(user_data.password)
    else:
        # LDAP 用户不保存本地口令
        pwd_hash = None

    created_user = User(
        username=username,
        auth_source=user_data.auth_source,
        email=user_data.email,
        display_name=user_data.display_name,
        password_hash=pwd_hash,
        role=validate_user_role(user_data.role),
        status=validate_user_status(user_data.status),
    )
    db.add(created_user)
    await db.commit()

    get_audit_logger().log_admin_operation(
        admin_id=str(admin_user.id),
        action=AuditAction.ADMIN_USER_CREATE,
        target_type=ResourceType.USER,
        target_id=str(created_user.id),
        changes={
            "username": created_user.username,
            "email": created_user.email,
            "auth_source": created_user.auth_source,
            "role": created_user.role,
            "status": created_user.status,
        },
    )

    loaded_user = await load_user_with_statistics(db, created_user.id)
    return success_response(
        data=UserResponse.model_validate(loaded_user).model_dump(),
        message="用户创建成功",
        code=status.HTTP_201_CREATED,
    )

@router.get(
    "/admin",
    response_model=dict,
    summary="获取用户列表（管理员）"
)
async def admin_get_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(
        None, max_length=DEFAULT_KEYWORD_MAX_LENGTH, description="搜索关键词（用户名/邮箱）"
    ),
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
        pattern = like_pattern(keyword)
        query = query.where(
            (User.display_name.ilike(pattern, escape=LIKE_ESCAPE)) |
            (User.username.ilike(pattern, escape=LIKE_ESCAPE)) |
            (User.email.ilike(pattern, escape=LIKE_ESCAPE))
        )

    # 角色筛选
    if role:
        query = query.where(User.role == role)

    # 状态筛选
    if status_filter:
        normalized_status = normalize_user_status(status_filter)
        if normalized_status == UserStatus.DISABLED.value:
            query = query.where(
                or_(
                    User.status == UserStatus.DISABLED.value,
                    User.status.in_(LEGACY_DISABLED_USER_STATUSES),
                )
            )
        else:
            query = query.where(User.status == normalized_status)

    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(User.created_at.desc())

    result = await db.execute(query)
    users = result.scalars().all()

    return success_response(
        data=UserListResponse(
            total=total,
            items=[UserResponse.model_validate(u) for u in users],
            page=page,
            page_size=page_size,
        ).model_dump()
    )


@router.get(
    "/admin/stats",
    response_model=dict,
    summary="获取用户统计（管理员）"
)
async def admin_get_user_stats(
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户统计信息（仅管理员可访问）"""
    from datetime import timedelta

    now = utcnow()
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

    return success_response(
        data=UserStatsResponse(
            total_users=total_users,
            active_users=active_users,
            admin_users=admin_users,
            new_users_today=new_users_today,
            new_users_this_week=new_users_this_week,
        ).model_dump()
    )


@router.get(
    "/admin/{user_id}",
    summary="获取用户详情（管理员）"
)
async def admin_get_user(
    user_id: str,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """获取指定用户的详细信息（仅管理员可访问）"""
    result = await db.execute(
        select(User)
        .options(joinedload(User.statistics))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    return success_response(UserResponse.model_validate(user).model_dump())


@router.patch(
    "/admin/{user_id}",
    response_model=dict,
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
    """
    result = await db.execute(
        select(User)
        .options(joinedload(User.statistics))
        .where(User.id == user_id)
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
        update_data["role"] = validate_user_role(update_data["role"])

    # 验证状态
    if "status" in update_data:
        update_data["status"] = validate_user_status(update_data["status"])

    if "email" in update_data and update_data["email"]:
        await ensure_user_email_unique(db, update_data["email"], exclude_user_id=user_id)

    # 更新用户信息
    for key, value in update_data.items():
        setattr(user, key, value)

    user.updated_at = utcnow()
    await db.commit()

    get_audit_logger().log_admin_operation(
        admin_id=str(admin_user.id),
        action=AuditAction.ADMIN_USER_UPDATE,
        target_type=ResourceType.USER,
        target_id=user_id,
        changes=dict(update_data),
    )

    refreshed_result = await db.execute(
        select(User)
        .options(joinedload(User.statistics))
        .where(User.id == user_id)
    )
    refreshed_user = refreshed_result.scalar_one()
    return success_response(
        data=UserResponse.model_validate(refreshed_user).model_dump(),
        message="用户更新成功",
    )


@router.post(
    "/admin/{user_id}/reset-password",
    summary="重置用户密码（管理员）"
)
async def admin_reset_user_password(
    user_id: str,
    password_reset: AdminPasswordReset,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """管理员直接重置目标用户密码。"""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    if user.auth_source == "ldap":
        raise BusinessException(
            "LDAP 用户的口令由企业目录管理，不能在平台重置",
            http_status=400,
            code=40002,
        )

    user.password_hash = hash_password(password_reset.new_password)
    user.updated_at = utcnow()
    await db.commit()

    get_audit_logger().log_admin_operation(
        admin_id=str(admin_user.id),
        action=AuditAction.ADMIN_USER_UPDATE,
        target_type=ResourceType.USER,
        target_id=user_id,
        changes={"reset_password": True},
    )

    return success_response(
        data={"message": "密码重置成功"},
        message="密码重置成功",
    )


@router.delete(
    "/admin/{user_id}",
    summary="删除用户（管理员）"
)
async def admin_delete_user(
    user_id: str,
    hard: bool = Query(False, description="是否彻底删除"),
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    删除指定用户（仅管理员可访问）

    默认软删除，将用户状态设置为 disabled。
    传入 hard=true 时会级联清理关联数据并彻底删除用户。
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

    if hard:
        await hard_delete_user_related_resources(db, user_id)
        await db.commit()
        get_audit_logger().log_admin_operation(
            admin_id=str(admin_user.id),
            action=AuditAction.ADMIN_USER_DELETE,
            target_type=ResourceType.USER,
            target_id=user_id,
            changes={"hard": True},
        )
        return success_response(
            data={"message": "用户已彻底删除"},
            message="用户已彻底删除",
        )

    # 软删除：统一设置为 disabled
    user.status = UserStatus.DISABLED.value
    user.updated_at = utcnow()
    await db.commit()

    get_audit_logger().log_admin_operation(
        admin_id=str(admin_user.id),
        action=AuditAction.ADMIN_USER_DELETE,
        target_type=ResourceType.USER,
        target_id=user_id,
        changes={"hard": False},
    )

    return success_response(
        data={"message": "用户已删除"},
        message="用户已删除",
    )
