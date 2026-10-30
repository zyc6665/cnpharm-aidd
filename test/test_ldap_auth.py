"""LDAP 认证任务 2+3+4 的集成测试。

覆盖设计 §7 的 7 项：
1. 本地登录成功 / 失败；
2. LDAP 登录成功并回填 ``ldap_dn`` / ``last_login_at``；
3. LDAP 未启用时 LDAP 用户登录失败、本地用户不受影响；
4. 注册接口已下线（404/405）；
5. username 大小写不敏感唯一；
6. LDAP 用户重置/改密返回业务码 40002 且不写本地 hash；
7. 管理员创建 LDAP 用户不保存口令。

另验证 email 不再能作为登录凭证。
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models as _models  # noqa: F401,E402  注册全部表
from app.auth.password import hash_password  # noqa: E402
from app.auth.dependencies import get_admin_user, get_current_user  # noqa: E402
from app.auth.ldap_provider import LdapAuthResult, get_ldap_authenticator  # noqa: E402
from app.auth.jwt_handler import jwt_handler  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402


LOCAL_PASSWORD = "LocalPass123"
LDAP_PASSWORD = "LdapPass123"
ADMIN_PASSWORD = "AdminPass123"


class FakeAuthenticator:
    """内存字典版 LdapAuthenticator，避免真实目录依赖。"""

    def __init__(self, directory: dict):
        self.directory = directory
        self.calls: list[tuple[str, str]] = []

    def authenticate(self, username: str, password: str):
        self.calls.append((username, password))
        record = self.directory.get((username or "").lower())
        if not record or record["password"] != password:
            return None
        return LdapAuthResult(
            dn=record["dn"],
            username=username,
            email=record.get("email"),
            display_name=record.get("display_name"),
        )


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def accounts(db_session: AsyncSession) -> dict[str, User]:
    local = User(
        username="localuser",
        email="local@example.com",
        password_hash=hash_password(LOCAL_PASSWORD),
        display_name="Local User",
        auth_source="local",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    ldap = User(
        username="ldapuser",
        email=None,
        password_hash=None,
        display_name="LDAP User",
        auth_source="ldap",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    admin = User(
        username="admin",
        email="admin@example.com",
        password_hash=hash_password(ADMIN_PASSWORD),
        display_name="Admin",
        auth_source="local",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add_all([local, ldap, admin])
    await db_session.commit()
    for user in (local, ldap, admin):
        await db_session.refresh(user)
    return {"local": local, "ldap": ldap, "admin": admin}


@pytest.fixture
def fake_authenticator() -> FakeAuthenticator:
    return FakeAuthenticator(
        {
            "ldapuser": {
                "password": LDAP_PASSWORD,
                "dn": "uid=ldapuser,ou=people,dc=example,dc=org",
                "email": "ldapuser@example.com",
                "display_name": "LDAP User",
            }
        }
    )


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    accounts: dict[str, User],
    fake_authenticator: FakeAuthenticator,
):
    async def override_get_db():
        yield db_session

    async def _resolve(authorization: str | None) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        account = accounts.get(token)
        if account is None:
            raise HTTPException(status_code=401, detail="未提供认证凭证")
        result = await db_session.execute(
            select(User).options(joinedload(User.statistics)).where(User.id == account.id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="用户不存在")
        return user

    async def override_get_current_user(authorization: str | None = Header(default=None)):
        return await _resolve(authorization)

    async def override_get_admin_user(authorization: str | None = Header(default=None)):
        return await _resolve(authorization)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_admin_user] = override_get_admin_user
    app.dependency_overrides[get_ldap_authenticator] = lambda: fake_authenticator

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# 1. 本地登录成功/失败 + email 不能登录
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_local_login_success_and_failure(api_client: httpx.AsyncClient):
    ok = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "localuser", "password": LOCAL_PASSWORD},
    )
    assert ok.status_code == 200, ok.text
    payload = ok.json()["data"]
    assert payload["user"]["username"] == "localuser"
    assert payload["user"]["auth_source"] == "local"
    assert payload["token_type"] == "bearer"
    claims = jwt_handler.verify_token(payload["access_token"])
    assert claims["username"] == "localuser"
    assert claims["email"] == "local@example.com"

    # 大小写不敏感
    mixed = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "LocalUser", "password": LOCAL_PASSWORD},
    )
    assert mixed.status_code == 200

    bad = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "localuser", "password": "wrong-pass"},
    )
    assert bad.status_code == 401
    assert bad.json()["code"] == 40101


@pytest.mark.asyncio
async def test_email_cannot_be_used_as_login_credential(api_client: httpx.AsyncClient):
    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "local@example.com", "password": LOCAL_PASSWORD},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# 2. LDAP 成功回填
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ldap_login_success_backfills_dn_and_last_login(
    api_client: httpx.AsyncClient,
    accounts: dict[str, User],
    db_session: AsyncSession,
    fake_authenticator: FakeAuthenticator,
):
    response = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "ldapuser", "password": LDAP_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["user"]["auth_source"] == "ldap"

    await db_session.refresh(accounts["ldap"])
    assert accounts["ldap"].ldap_dn == "uid=ldapuser,ou=people,dc=example,dc=org"
    assert accounts["ldap"].last_login_at is not None
    assert accounts["ldap"].password_hash is None
    assert fake_authenticator.calls == [("ldapuser", LDAP_PASSWORD)]


# --------------------------------------------------------------------------- #
# 3. LDAP 未启用
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ldap_disabled_ldap_user_fails_local_user_unaffected(
    api_client: httpx.AsyncClient,
):
    app.dependency_overrides[get_ldap_authenticator] = lambda: None

    ldap_login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "ldapuser", "password": LDAP_PASSWORD},
    )
    assert ldap_login.status_code == 401
    assert ldap_login.json()["code"] == 40101

    local_login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "localuser", "password": LOCAL_PASSWORD},
    )
    assert local_login.status_code == 200


# --------------------------------------------------------------------------- #
# 4. 注册接口下线
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_register_endpoint_is_gone(api_client: httpx.AsyncClient):
    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "someone@example.com",
            "password": "SomePass123",
            "verification_code": "123456",
        },
    )
    assert response.status_code in (404, 405)


# --------------------------------------------------------------------------- #
# 5. username 大小写不敏感唯一
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_admin_create_username_is_case_insensitive_unique(
    api_client: httpx.AsyncClient,
):
    duplicate = await api_client.post(
        "/api/v1/users/admin",
        json={
            "username": "LocalUser",
            "email": "another@example.com",
            "password": "AnotherPass123",
        },
        headers={"Authorization": "Bearer admin"},
    )
    assert duplicate.status_code == 400, duplicate.text
    assert duplicate.json()["code"] == 40002

    created = await api_client.post(
        "/api/v1/users/admin",
        json={
            "username": "brandnew",
            "email": "brandnew@example.com",
            "password": "AnotherPass123",
        },
        headers={"Authorization": "Bearer admin"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["username"] == "brandnew"


# --------------------------------------------------------------------------- #
# 6. LDAP 用户重置/改密被拒
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ldap_user_reset_and_change_password_forbidden(
    api_client: httpx.AsyncClient,
    accounts: dict[str, User],
    db_session: AsyncSession,
):
    reset = await api_client.post(
        f"/api/v1/users/admin/{accounts['ldap'].id}/reset-password",
        json={"new_password": "LdapResetPass123"},
        headers={"Authorization": "Bearer admin"},
    )
    assert reset.status_code == 400, reset.text
    assert reset.json()["code"] == 40002

    change = await api_client.put(
        "/api/v1/users/me/password",
        json={"old_password": "whatever", "new_password": "LdapResetPass123"},
        headers={"Authorization": "Bearer ldap"},
    )
    assert change.status_code == 400, change.text
    assert change.json()["code"] == 40002

    await db_session.refresh(accounts["ldap"])
    assert accounts["ldap"].password_hash is None


# --------------------------------------------------------------------------- #
# 7. 管理员创建 LDAP 用户不存口令
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_admin_create_ldap_user_stores_no_local_password(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    response = await api_client.post(
        "/api/v1/users/admin",
        json={"username": "ldapnew", "auth_source": "ldap"},
        headers={"Authorization": "Bearer admin"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()["data"]
    assert payload["username"] == "ldapnew"
    assert payload["auth_source"] == "ldap"
    assert payload["email"] is None

    result = await db_session.execute(select(User).where(User.username == "ldapnew"))
    created = result.scalar_one()
    assert created.password_hash is None
    assert created.auth_source == "ldap"


@pytest.mark.asyncio
async def test_admin_create_local_user_requires_password(
    api_client: httpx.AsyncClient,
):
    response = await api_client.post(
        "/api/v1/users/admin",
        json={"username": "nopassword", "auth_source": "local"},
        headers={"Authorization": "Bearer admin"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == 40002


# --------------------------------------------------------------------------- #
# 8. 响应契约：/users/me 含 username/auth_source/last_login_at（email 可空）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_users_me_exposes_identity_fields(api_client: httpx.AsyncClient):
    response = await api_client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer ldap"}
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["username"] == "ldapuser"
    assert payload["auth_source"] == "ldap"
    assert "last_login_at" in payload
    assert payload["email"] is None


# --------------------------------------------------------------------------- #
# 9. 管理员编辑用户：空串邮箱归一为 None
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_admin_update_blank_email_becomes_none(
    api_client: httpx.AsyncClient,
    accounts: dict[str, User],
    db_session: AsyncSession,
):
    response = await api_client.patch(
        f"/api/v1/users/admin/{accounts['local'].id}",
        json={"email": "   "},
        headers={"Authorization": "Bearer admin"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["email"] is None

    await db_session.refresh(accounts["local"])
    assert accounts["local"].email is None

