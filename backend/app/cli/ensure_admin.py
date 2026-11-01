"""确保存在一个可登录的管理员账号（幂等）。

用法::

    # 传统：按邮箱定位（用户名由邮箱本地部分自动派生）
    python -m app.cli.ensure_admin \
        --email admin@sciminer.com --password 'ChangeMe_123'

    # 内网 LDAP 场景：只给用户名（不落邮箱）
    python -m app.cli.ensure_admin \
        --username admin --password 'ChangeMe_123'

账号优先按 ``username``（大小写不敏感）定位；已存在时只校验/更新角色为 admin、
状态为 active，密码仅在显式传 ``--reset-password`` 时重写，避免误改正在使用的口令。
不存在则创建，写入 ``username`` 且 ``auth_source="local"``。
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, select

from app.auth.password import hash_password
from app.database.session import async_session_factory, engine
from app.models.users import User, UserRole, UserStatus, derive_username_from_email


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--email", default=None, help="管理员邮箱（可空；缺省用户名时从其本地部分派生）"
    )
    parser.add_argument(
        "--username", default=None, help="管理员用户名（可空；缺省时由 --email 本地部分派生）"
    )
    parser.add_argument("--password", required=True, help="管理员密码（新建时使用）")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="账号已存在时也把密码重置为 --password",
    )
    return parser


async def _run(
    *,
    username: str,
    email: str | None,
    password: str,
    reset_password: bool,
) -> None:
    try:
        async with async_session_factory() as db:
            user = (
                await db.execute(
                    select(User).where(func.lower(User.username) == username.lower())
                )
            ).scalar_one_or_none()

            if user is None and email:
                # 兼容历史「只有 email、尚未有该 username」的账号，避免重复建号。
                user = (
                    await db.execute(
                        select(User).where(func.lower(User.email) == email.lower())
                    )
                ).scalar_one_or_none()
                if user is not None and not user.username:
                    user.username = username

            if user is None:
                user = User(
                    email=email,
                    username=username,
                    auth_source="local",
                    password_hash=hash_password(password),
                    display_name="Platform Admin",
                    role=UserRole.ADMIN.value,
                    status=UserStatus.ACTIVE.value,
                )
                db.add(user)
                action = "created"
            else:
                user.role = UserRole.ADMIN.value
                user.status = UserStatus.ACTIVE.value
                if email and not user.email:
                    user.email = email
                if reset_password:
                    user.password_hash = hash_password(password)
                    action = "updated(reset password)"
                else:
                    action = "updated(role/status only)"
            await db.commit()
            await db.refresh(user)
            print(
                f"ADMIN {action}: username={user.username} "
                f"email={user.email} id={user.id}",
                flush=True,
            )
    finally:
        await engine.dispose()


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    username = (args.username or "").strip() or derive_username_from_email(args.email)
    if not username:
        parser.error("必须提供 --username 或 --email 之一")
    asyncio.run(
        _run(
            username=username,
            email=args.email,
            password=args.password,
            reset_password=args.reset_password,
        )
    )


if __name__ == "__main__":
    main()
