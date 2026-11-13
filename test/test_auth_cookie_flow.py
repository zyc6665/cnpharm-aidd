# test/test_auth_cookie_flow.py
"""httpOnly Cookie + CSRF 认证流转测试。

覆盖固定契约：
1. login 下发 access / refresh / csrf 三个 Set-Cookie 且属性正确；
2. 仅凭 Cookie 访问受保护接口成功；
3. Cookie + 非安全方法缺 ``X-CSRF-Token`` -> 403，带头 -> 成功；
4. Bearer 认证不受 CSRF 约束；
5. refresh 用 Cookie 换新，body 默认不含 token；``X-Token-Transport: body`` 时才返回；
6. logout 删除三个 Cookie。
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models as _models  # noqa: F401,E402  注册全部表
from app.auth.password import hash_password  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402

USERNAME = "cookieuser"
PASSWORD = "Cookie-Flow-Passw0rd!"

ACCESS_COOKIE = "cpumodel_access"
REFRESH_COOKIE = "cpumodel_refresh"
CSRF_COOKIE = "cpumodel_csrf"


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
async def member(db_session: AsyncSession) -> User:
    user = User(
        username=USERNAME,
        email="cookie@example.com",
        password_hash=hash_password(PASSWORD),
        display_name="Cookie User",
        auth_source="local",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, member: User):
    """真实认证依赖 + 测试数据库；只覆盖 get_db。"""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


def _set_cookie_headers(response: httpx.Response) -> dict[str, str]:
    """把响应里的 Set-Cookie 按 cookie 名解析成 name -> 原始行。"""
    result: dict[str, str] = {}
    for line in response.headers.get_list("set-cookie"):
        name = line.split("=", 1)[0].strip()
        result[name] = line
    return result


async def _login(client: httpx.AsyncClient) -> httpx.Response:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response


@pytest.mark.asyncio
async def test_login_sets_three_cookies_with_contract_attributes(api_client: httpx.AsyncClient):
    response = await _login(api_client)
    cookies = _set_cookie_headers(response)

    assert set(cookies) == {ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE}

    access = cookies[ACCESS_COOKIE].lower()
    assert "httponly" in access
    assert "path=/" in access
    assert "samesite=lax" in access
    assert "max-age=3600" in access

    refresh = cookies[REFRESH_COOKIE].lower()
    assert "httponly" in refresh
    assert "path=/api/v1/auth" in refresh
    assert "samesite=strict" in refresh
    assert "max-age=604800" in refresh

    csrf = cookies[CSRF_COOKIE].lower()
    assert "httponly" not in csrf
    assert "path=/" in csrf
    assert "samesite=lax" in csrf
    # CSRF Cookie 寿命与 refresh 对齐（前端据此判断是否可尝试恢复会话）
    assert "max-age=604800" in csrf

    # 兼容旧客户端：body 仍返回 user 与两个 token。
    data = response.json()["data"]
    assert data["user"]["username"] == USERNAME
    assert data["access_token"]
    assert data["refresh_token"]


@pytest.mark.asyncio
async def test_cookie_authentication_reaches_protected_endpoint(
    api_client: httpx.AsyncClient,
):
    await _login(api_client)
    response = await api_client.get("/api/v1/users/me")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["username"] == USERNAME


@pytest.mark.asyncio
async def test_cookie_post_without_csrf_header_is_forbidden(
    api_client: httpx.AsyncClient,
):
    await _login(api_client)
    response = await api_client.post("/api/v1/auth/logout")
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "CSRF 校验失败"


@pytest.mark.asyncio
async def test_cookie_post_with_csrf_header_succeeds(api_client: httpx.AsyncClient):
    await _login(api_client)
    csrf_token = api_client.cookies.get(CSRF_COOKIE)
    assert csrf_token
    response = await api_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_bearer_auth_skips_csrf(api_client: httpx.AsyncClient):
    login = await _login(api_client)
    access_token = login.json()["data"]["access_token"]
    # 清掉 Cookie，确保只走 Bearer；POST 无 CSRF 头也应成功。
    api_client.cookies.clear()
    response = await api_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_refresh_uses_cookie_and_omits_tokens_from_body(
    api_client: httpx.AsyncClient,
):
    login = await _login(api_client)
    old_refresh = api_client.cookies.get(REFRESH_COOKIE)
    assert old_refresh

    response = await api_client.post("/api/v1/auth/refresh")
    assert response.status_code == 200, response.text

    data = response.json()["data"]
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert data["token_type"] == "bearer"

    cookies = _set_cookie_headers(response)
    assert set(cookies) == {ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE}
    assert api_client.cookies.get(REFRESH_COOKIE) != old_refresh

    # 新 Cookie 可以继续访问受保护接口。
    me = await api_client.get("/api/v1/users/me")
    assert me.status_code == 200, me.text


@pytest.mark.asyncio
async def test_refresh_body_fallback_for_legacy_clients(api_client: httpx.AsyncClient):
    login = await _login(api_client)
    refresh_token = login.json()["data"]["refresh_token"]
    api_client.cookies.clear()

    response = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"X-Token-Transport": "body"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]


@pytest.mark.asyncio
async def test_logout_clears_all_cookies(api_client: httpx.AsyncClient):
    await _login(api_client)
    csrf_token = api_client.cookies.get(CSRF_COOKIE)
    response = await api_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200, response.text

    cookies = _set_cookie_headers(response)
    assert set(cookies) == {ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE}
    for name, line in cookies.items():
        lowered = line.lower()
        assert "max-age=0" in lowered or "expires=" in lowered, (name, line)

    assert api_client.cookies.get(ACCESS_COOKIE) is None
    assert api_client.cookies.get(REFRESH_COOKIE) is None
    assert api_client.cookies.get(CSRF_COOKIE) is None

    # 清理后访问受保护接口应回到未认证。
    me = await api_client.get("/api/v1/users/me")
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_refresh_failure_clears_all_auth_cookies(api_client: httpx.AsyncClient):
    """刷新失败（含 40103 统一认证会话失效）必须清三个 Cookie。

    否则前端还攥着可用的 ``cpumodel_refresh``，会形成「刷新 -> 401 -> 再刷新」的死循环；
    端点的 ``Set-Cookie`` 写在注入的 Response 上，抛异常后由全局异常处理器补齐。
    """
    api_client.cookies.set(REFRESH_COOKIE, "not-a-valid-refresh-token", path="/api/v1/auth")

    response = await api_client.post("/api/v1/auth/refresh")

    assert response.status_code == 401, response.text
    cookies = _set_cookie_headers(response)
    assert set(cookies) == {ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE}
    for name, line in cookies.items():
        lowered = line.lower()
        assert "max-age=0" in lowered or "expires=" in lowered, (name, line)
