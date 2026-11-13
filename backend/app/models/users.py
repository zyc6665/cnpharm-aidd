# backend/app/models/users.py
"""用户相关模型"""

import enum
import re
import uuid

from sqlalchemy import Column, DateTime, Index, Integer, String, event, func, select, text
from sqlalchemy.orm import object_session, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    """用户角色"""
    USER = "user"
    ADMIN = "admin"


class UserStatus(str, enum.Enum):
    """用户状态"""
    ACTIVE = "active"
    DISABLED = "disabled"
    PENDING = "pending"


class AuthSource(str, enum.Enum):
    """认证来源。

    * ``local``：平台本地口令；
    * ``ldap``：企业目录（LDAP）校验；
    * ``sso``：甲方统一身份认证（IAM）单点登录，平台不保存口令。
    """
    LOCAL = "local"
    LDAP = "ldap"
    SSO = "sso"


#: 用户名允许的字符集（其余替换为 ``_``）。
_USERNAME_INVALID_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def derive_username_from_email(email: str | None) -> str:
    """由 email 本地部分派生合法用户名：小写、``[A-Za-z0-9._-]``、截断到 56。

    与 Alembic 迁移的回填规则保持一致（迁移里不 import 应用模型，故两处各写一份）。
    """
    local = (email or "").split("@", 1)[0].strip().lower()
    local = _USERNAME_INVALID_CHARS.sub("_", local)
    return local[:56]


class User(Base, UUIDMixin, TimestampMixin):
    """用户表"""
    __tablename__ = "users"

    email = Column(String(255), nullable=True, index=True)
    password_hash = Column(String(255), nullable=True)
    username = Column(String(64), nullable=False, unique=False, index=True)
    auth_source = Column(
        String(16), nullable=False, default="local", server_default="local"
    )
    ldap_dn = Column(String(512), nullable=True)
    # 甲方统一身份认证的用户唯一标识（getUserInfo 的 userId）。单点登录用户用它
    # 做幂等匹配，避免改名/换部门后重复开户；本地与 LDAP 用户为 NULL。
    sso_uid = Column(String(128), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    display_name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    role = Column(String(20), default=UserRole.USER.value, nullable=False)
    status = Column(String(20), default=UserStatus.ACTIVE.value, nullable=False)

    # 配额相关
    daily_task_limit = Column(Integer, default=50)
    max_file_size_mb = Column(Integer, default=100)

    # 双真源收敛：下面两条唯一性此前只在迁移 20261031_07 的原生 SQL 里存在，
    # 模型不声明会导致 SQLite（测试/dev 的 create_all）没有任何唯一约束，且
    # ``alembic check`` 把它们误判为 "removed index"（autogenerate 会生成
    # drop_index 把生产唯一约束删掉）。这里补齐声明，让两方言与迁移一致。
    # （放在列定义之后，才能直接引用 username / ldap_dn 的 Column 对象。）
    __table_args__ = (
        # 用户名大小写不敏感唯一：PostgreSQL 用 lower(username) 表达式索引，
        # SQLite 同样支持表达式索引，故两方言可共用同一声明。
        Index("uq_users_username_lower", func.lower(username), unique=True),
        # ldap_dn 仅在非空时唯一（部分唯一索引）。本地账号（auth_source=local）
        # 的 ldap_dn 为 NULL，不能被当作重复值互相冲突。
        Index(
            "uq_users_ldap_dn",
            "ldap_dn",
            unique=True,
            postgresql_where=text("ldap_dn IS NOT NULL"),
            sqlite_where=text("ldap_dn IS NOT NULL"),
        ),
        # 统一身份（IAM）用户唯一：同一 userId 只能绑定一个平台账号。
        # 与 ldap_dn 同理用部分唯一索引，本地/LDAP 用户的 NULL 互不冲突。
        Index(
            "uq_users_sso_uid",
            "sso_uid",
            unique=True,
            postgresql_where=text("sso_uid IS NOT NULL"),
            sqlite_where=text("sso_uid IS NOT NULL"),
        ),
        # 注意：列上的 ``index=True`` 生成的是普通非唯一索引 ix_users_username，
        # 它与上面的 uq_users_username_lower 语义不同——前者服务于「按原始大小写
        # 精确匹配用户名」的点查，后者是「大小写不敏感唯一约束」。两者都保留。
    )

    # 关系
    tools = relationship("Tool", back_populates="owner", foreign_keys="Tool.owner_id")
    tasks = relationship("Task", back_populates="user")
    files = relationship("File", back_populates="owner")
    statistics = relationship("UserStatistics", back_populates="user", uselist=False)


def _username_taken(connection, target: "User", candidate: str) -> bool:
    """该用户名是否已被同 session 的待插入对象或库里已有行占用（大小写不敏感）。"""
    lowered = candidate.lower()

    session = object_session(target)
    if session is not None:
        for obj in session.new:
            if obj is target or not isinstance(obj, User):
                continue
            if (getattr(obj, "username", None) or "").lower() == lowered:
                return True

    row = connection.execute(
        select(User.id).where(func.lower(User.username) == lowered).limit(1)
    ).first()
    return row is not None


def _resolve_unique_username(connection, target: "User", base: str) -> str:
    """在 base 被占用时追加短随机后缀；仅在冲突时追加，保持真实用户名干净。"""
    if not _username_taken(connection, target, base):
        return base
    candidate = (base[:55] + "_" + uuid.uuid4().hex[:6])[:64]
    while _username_taken(connection, target, candidate):
        candidate = (base[:48] + "_" + uuid.uuid4().hex[:10])[:64]
    return candidate


@event.listens_for(User, "before_insert")
def _populate_username_on_insert(mapper, connection, target: "User") -> None:
    """ORM 插入时若 username 为空则从 email 本地部分派生，保证永不因空值失败。

    全仓大量历史测试夹具直接 ``User(email=...)`` 且不带 username，这个监听器是
    兼容它们的唯一保证；真实创建路径（管理员建号 / CLI）应显式传 username。
    """
    if getattr(target, "username", None):
        return
    base = derive_username_from_email(getattr(target, "email", None))
    if not base:
        base = f"user_{uuid.uuid4().hex[:8]}"
    target.username = _resolve_unique_username(connection, target, base)
