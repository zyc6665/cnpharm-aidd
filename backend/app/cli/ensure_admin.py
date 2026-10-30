"""确保存在一个可登录的管理员账号（幂等）。

用法::

    python -m app.cli.ensure_admin \
        --email admin@sciminer.com --password 'ChangeMe_123'

账号已存在时只校验/更新角色为 admin、状态为 active；密码仅在显式传
``--reset-password`` 时重写，避免误改正在使用的口令。
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.auth.password import hash_password
from app.database.session import async_session_factory, engine
from app.models.users import User, UserRole, UserStatus


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="管理员邮箱")
    parser.add_argument("--password", required=True, help="管理员密码（新建时使用）")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="账号已存在时也把密码重置为 --password",
    )
    return parser


async def _run(*, email: str, password: str, reset_password: bool) -> None:
    try:
        async with async_session_factory() as db:
            user = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    email=email,
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
                if reset_password:
                    user.password_hash = hash_password(password)
                    action = "updated(reset password)"
                else:
                    action = "updated(role/status only)"
            await db.commit()
            await db.refresh(user)
            print(f"ADMIN {action}: {user.email} id={user.id}", flush=True)
    finally:
        await engine.dispose()


def main() -> None:
    args = _parser().parse_args()
    asyncio.run(
        _run(
            email=args.email,
            password=args.password,
            reset_password=args.reset_password,
        )
    )


if __name__ == "__main__":
    main()
