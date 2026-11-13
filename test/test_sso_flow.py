# test/test_sso_flow.py
"""统一身份认证单点登录端点测试。

覆盖：
1. ``/auth/sso/status`` 暴露开关（前端据此决定是否显示入口）；
2. ``/auth/sso/authorize`` 拼地址、下发**带 HMAC 签名**的 state Cookie、拒绝开放重定向；
3. ``/auth/sso/callback`` 的 state 验签与恒定时间比对、换票失败、开户、同名本地账号
   冲突、停用账号、关闭自动开户；
4. 成功回跳会写入三个认证 Cookie 并落到站内目标地址；
5. 硬编码加固：非 ASCII state 不再 500（P1）、伪造/篡改 state Cookie 一律 303（P2）、
   IAM 超长字段落库前截断（X6）、disabled 分支清 Cookie 与日志净化（X3/X2）；
6. 统一认证账号在平台侧无口令：口令登录、自助改密、管理员重置全部拒绝（P3）。
"""

from __future__ import annotations

import hashlib
import hmac
import sys
from pathlib import Path
from urllib.parse import quote

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
from app.api.v1 import auth_sso as sso_module  # noqa: E402
from app.auth.password import hash_password, verify_password  # noqa: E402
from app.auth.dependencies import get_admin_user, get_current_user  # noqa: E402
from app.config import Settings, settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.users import AuthSource, User, UserRole, UserStatus  # noqa: E402
from app.services.iam_client import IamClient, get_iam_client  # noqa: E402

IAM_UID = "iam-0001"
IAM_USERNAME = "zhangsan"
STATE_COOKIE = "cpumodel_sso_state"
STATE_COOKIE_PATH = "/api/v1/auth/sso"
AUTH_COOKIE_NAMES = ("cpumodel_access", "cpumodel_refresh", "cpumodel_csrf")


def _iam_settings() -> Settings:
    return Settings(
        ENVIRONMENT="development",
        SSO_ENABLED=True,
        SSO_BASE_URL="https://iam.example",
        SSO_APP_ID="cnpharm-aidd",
        SSO_CLIENT_SECRET="client-secret-value",
        SSO_REDIRECT_URI="https://platform.example/api/v1/auth/sso/callback",
    )


def _iam_handler(
    *,
    token_code: str = "9001",
    user_info: dict | None = None,
    user_info_code: str = "9001",
    calls: list[str] | None = None,
):
    """假的甲方 IAM：按路径应答 getToken 与 getUserInfo。

    ``calls`` 记录调用轨迹，让「失败路径零 IAM 调用」这类断言可观测。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if calls is not None:
            calls.append("getToken" if path.endswith("/getToken") else "getUserInfo")
        if path.endswith("/getToken"):
            if token_code != "9001":
                return httpx.Response(200, json={"code": token_code, "message": "code 非法"})
            return httpx.Response(
                200,
                json={
                    "code": "9001",
                    "message": "操作成功",
                    "data": {"accessToken": "iam-access", "refreshToken": "iam-refresh"},
                },
            )
        if path.endswith("/getUserInfo"):
            if user_info_code != "9001":
                return httpx.Response(200, json={"code": user_info_code, "message": "票据过期"})
            payload = {
                "userId": IAM_UID,
                "userName": IAM_USERNAME,
                "fullname": "张三",
                "employeeNo": "E1001",
                "email": "zhangsan@example.com",
                "orgs": [{"deptCode": "D01", "deptName": "信息中心"}],
            }
            payload.update(user_info or {})
            return httpx.Response(200, json={"code": "9001", "userInfo": payload})
        raise AssertionError(f"unexpected path {path}")

    return handler


def _install_iam(handler) -> None:
    fake = IamClient(_iam_settings(), transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_iam_client] = lambda: fake


def _set_cookie_blob(response: httpx.Response) -> str:
    return " ".join(response.headers.get_list("set-cookie"))


def _state_cookie_headers(response: httpx.Response) -> list[str]:
    return [
        header
        for header in response.headers.get_list("set-cookie")
        if header.startswith(f"{STATE_COOKIE}=")
    ]


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
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def guards_client(db_session: AsyncSession):
    """带认证覆盖的客户端：Bearer <username> 映射到库里的用户（P3 守卫用例专用）。"""

    async def override_get_db():
        yield db_session

    async def _resolve(authorization: str | None = Header(default=None)) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        result = await db_session.execute(
            select(User).options(joinedload(User.statistics)).where(User.username == token)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="未提供认证凭证")
        return user

    async def override_get_current_user(authorization: str | None = Header(default=None)):
        return await _resolve(authorization)

    async def override_get_admin_user(authorization: str | None = Header(default=None)):
        return await _resolve(authorization)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_admin_user] = override_get_admin_user
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    app.dependency_overrides.clear()


@pytest.fixture
def sso_settings(monkeypatch):
    """打开 SSO 并固定策略项（不动真实配置文件）。"""
    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    monkeypatch.setattr(settings, "SSO_SUCCESS_PATH", "/workspace")
    monkeypatch.setattr(settings, "SSO_AUTO_PROVISION", True)
    monkeypatch.setattr(settings, "SSO_USERNAME_CLAIM", "userName")
    return settings


async def _add_user(
    db: AsyncSession,
    *,
    username: str,
    auth_source: str = AuthSource.LOCAL.value,
    status: str = UserStatus.ACTIVE.value,
    sso_uid: str | None = None,
    role: str = UserRole.USER.value,
    password_hash: str | None = None,
) -> User:
    stored_hash = password_hash
    if stored_hash is None and auth_source == AuthSource.LOCAL.value:
        # 只有本地账号才有平台口令；sso/ldap 账号与生产一致地留 None。
        stored_hash = hash_password("Pwd12345!")
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=stored_hash,
        display_name=username,
        auth_source=auth_source,
        sso_uid=sso_uid,
        role=role,
        status=status,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _signed_state_cookie(state: str = "state-1", target: str = "/workspace") -> str:
    return sso_module._state_cookie_value(state, target)


def _prime_state(http: httpx.AsyncClient, state: str = "state-1", target: str = "/workspace") -> None:
    """模拟 authorize 已经把**签名后的** state 写进 Cookie。"""
    http.cookies.set(STATE_COOKIE, _signed_state_cookie(state, target), path=STATE_COOKIE_PATH)


def _forged_state_cookies() -> list[str]:
    """一组「形状对但验不过」的 Cookie 值：无签名、空签名、多段、改签名。"""
    signed = _signed_state_cookie()
    payload = signed.rsplit("|", 1)[0]
    flipped = signed[:-1] + ("0" if signed[-1] != "0" else "1")
    return [
        "state-1|%2Fworkspace",  # 旧格式（两段、无签名）
        payload + "|",  # 签名段为空
        payload,  # 只有两段
        signed + "|deadbeef",  # 四段
        flipped,  # 改一个 hex 字符
        "state-1|%2Fworkspace|" + "z" * 64,  # 非 hex 签名
    ]


# --------------------------------------------------------------------------- #
# 1. status / authorize
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_status_reflects_switch(client: httpx.AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "SSO_ENABLED", False)
    body = (await client.get("/api/v1/auth/sso/status")).json()
    assert body["data"]["enabled"] is False

    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    body = (await client.get("/api/v1/auth/sso/status")).json()
    assert body["data"]["enabled"] is True
    assert body["data"]["authorize_path"] == "/api/v1/auth/sso/authorize"


@pytest.mark.asyncio
async def test_authorize_redirects_to_iam_and_keeps_state_in_cookie(
    client: httpx.AsyncClient, sso_settings, monkeypatch
):
    monkeypatch.setattr(settings, "SSO_ENABLED", False)
    disabled = await client.get("/api/v1/auth/sso/authorize")
    assert disabled.status_code == 303
    assert disabled.headers["location"] == "/login?sso_error=disabled"

    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    _install_iam(_iam_handler())
    response = await client.get("/api/v1/auth/sso/authorize?next=/tasks")

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://iam.example/auth/api/user/webungateway/authorize?")
    assert "appId=cnpharm-aidd" in location
    assert "responseType=code" in location
    assert "redirectUri=https%3A%2F%2Fplatform.example" in location

    cookie = client.cookies.get(STATE_COOKIE, path=STATE_COOKIE_PATH)
    assert cookie is not None
    state, encoded_target, signature = cookie.split("|")
    assert len(signature) == 64 and all(c in "0123456789abcdef" for c in signature)
    assert f"state={state}" in location  # 回跳时 state 必须与 Cookie 一致
    assert encoded_target == quote("/tasks", safe="")


@pytest.mark.asyncio
async def test_authorize_rejects_open_redirect(client: httpx.AsyncClient, sso_settings):
    _install_iam(_iam_handler())
    await client.get("/api/v1/auth/sso/authorize?next=//evil.example/steal")

    cookie = client.cookies.get(STATE_COOKIE, path=STATE_COOKIE_PATH)
    assert cookie is not None
    _, encoded_target, _ = cookie.split("|")
    # 非站内路径被丢弃，回落到 SSO_SUCCESS_PATH
    assert encoded_target == quote("/workspace", safe="")


@pytest.mark.asyncio
async def test_authorize_cookie_value_is_hmac_signed(
    client: httpx.AsyncClient, sso_settings
):
    """Cookie 值是 ``<state>|<编码目标>|<HMAC-SHA256 hex>``，签名可被独立重算。"""
    _install_iam(_iam_handler())
    response = await client.get("/api/v1/auth/sso/authorize?next=/tasks")

    cookie = client.cookies.get(STATE_COOKIE, path=STATE_COOKIE_PATH)
    assert cookie is not None
    parts = cookie.split("|")
    assert len(parts) == 3
    state, encoded_target, signature = parts
    assert f"state={state}" in response.headers["location"]

    expected = hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        b"sso-state-v1:" + f"{state}|{encoded_target}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert signature == expected


@pytest.mark.asyncio
async def test_state_cookie_is_host_only(client: httpx.AsyncClient, sso_settings, monkeypatch):
    """state Cookie 不设 Domain：兄弟子域无法往本域种一枚「合法」的 state。"""
    monkeypatch.setattr(settings, "COOKIE_DOMAIN", ".corp.example")
    _install_iam(_iam_handler())
    response = await client.get("/api/v1/auth/sso/authorize?next=/tasks")

    headers = _state_cookie_headers(response)
    assert len(headers) == 1
    assert "domain=" not in headers[0].lower()


@pytest.mark.asyncio
async def test_auth_cookies_keep_configured_domain(
    client: httpx.AsyncClient, sso_settings, monkeypatch
):
    """只把 state Cookie 改成 host-only，三枚认证 Cookie 仍按 COOKIE_DOMAIN 下发。"""
    monkeypatch.setattr(settings, "COOKIE_DOMAIN", ".corp.example")
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    for name in AUTH_COOKIE_NAMES:
        headers = [
            header
            for header in response.headers.get_list("set-cookie")
            if header.startswith(f"{name}=")
        ]
        assert headers, name
        assert "domain=.corp.example" in headers[0].lower()


# --------------------------------------------------------------------------- #
# 2. state 校验（P1 / P2）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_callback_rejects_state_mismatch(client: httpx.AsyncClient, sso_settings):
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    _prime_state(client, state="expected")

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=forged")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?sso_error=state"
    assert calls == []  # state 不过关就不该碰 IAM
    blob = _set_cookie_blob(response)
    for name in AUTH_COOKIE_NAMES:
        assert f"{name}=" not in blob


@pytest.mark.asyncio
async def test_callback_without_state_cookie_fails_closed(client: httpx.AsyncClient, sso_settings):
    _install_iam(_iam_handler())

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=state"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_state", ["中", "\ufffd\ufffd", "s" * 300])
async def test_callback_non_ascii_state_returns_303_state_error(
    client: httpx.AsyncClient, sso_settings, raw_state
):
    """P1：非 ASCII / 超长 state 走 303 失败分支，而不是 compare_digest 抛 TypeError 变 500。"""
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    _prime_state(client)  # Cookie 侧保持 ASCII：线上复现路径就是「Cookie 正常、query 异常」

    response = await client.get(
        f"/api/v1/auth/sso/callback?code=c1&state={quote(raw_state, safe='')}"
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login?sso_error=state"
    assert response.headers.get("content-type") != "application/json"
    assert calls == []
    blob = _set_cookie_blob(response)
    for name in AUTH_COOKIE_NAMES:
        assert f"{name}=" not in blob
    assert any("Max-Age=0" in header for header in _state_cookie_headers(response))


@pytest.mark.parametrize(
    ("stored", "received", "expected"),
    [
        ("abc", "abc", True),
        ("中", "中", True),  # 字节比较：非 ASCII 不再抛 TypeError
        ("中", "文", False),
        ("\ud800", "\ud800", False),  # 编码异常兜底，不得抛出
        (None, "x", False),
        ("x", None, False),
        ("", "", False),
    ],
)
def test_states_match_unit(stored, received, expected):
    assert sso_module._states_match(stored, received) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", _forged_state_cookies())
async def test_callback_rejects_forged_state_cookie(
    client: httpx.AsyncClient, sso_settings, raw
):
    """P2：没有服务端 HMAC 的 state Cookie 一律不认（伪造 / 截断 / 改签名）。"""
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    client.cookies.set(STATE_COOKIE, raw, path=STATE_COOKIE_PATH)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?sso_error=state"
    assert calls == []


@pytest.mark.asyncio
async def test_callback_rejects_tampered_target_keeping_state(
    client: httpx.AsyncClient, sso_settings
):
    """目标在签名覆盖内：改中间的 target 会让整枚 Cookie 验签失败。"""
    _install_iam(_iam_handler())
    state, _, signature = _signed_state_cookie().split("|")
    tampered = f"{state}|{quote('//evil.example', safe='')}|{signature}"
    client.cookies.set(STATE_COOKIE, tampered, path=STATE_COOKIE_PATH)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?sso_error=state"


# --------------------------------------------------------------------------- #
# 3. 回跳流程
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_callback_token_failure_reports_token_error(
    client: httpx.AsyncClient, sso_settings
):
    calls: list[str] = []
    _install_iam(_iam_handler(token_code="1014", calls=calls))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=used&state=state-1")

    assert response.headers["location"] == "/login?sso_error=token"
    assert calls == ["getToken"]  # 换票失败就短路，不再调 getUserInfo


@pytest.mark.asyncio
async def test_callback_provisions_new_sso_user(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    _install_iam(_iam_handler())
    _prime_state(client, target="/tasks")

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/tasks"
    cookies = response.headers.get_list("set-cookie")
    joined = " ".join(cookies)
    assert "cpumodel_access=" in joined
    assert "cpumodel_refresh=" in joined
    assert "cpumodel_csrf=" in joined

    user = (
        await db_session.execute(select(User).where(User.sso_uid == IAM_UID))
    ).scalar_one()
    assert user.auth_source == AuthSource.SSO.value
    assert user.username == IAM_USERNAME
    assert user.display_name == "张三"
    assert user.email == "zhangsan@example.com"
    assert user.password_hash is None  # 单点用户不存口令
    assert user.last_login_at is not None


@pytest.mark.asyncio
async def test_callback_reuses_sso_user_by_uid_even_if_username_changed(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    existing = await _add_user(
        db_session,
        username="old-username",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    assert existing.password_hash is None  # 夹具与生产一致：sso 账号无口令
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/workspace"
    await db_session.refresh(existing)
    assert existing.username == "old-username"  # 平台侧用户名不被强制改名
    assert existing.auth_source == AuthSource.SSO.value
    assert existing.password_hash is None
    assert existing.last_login_at is not None
    count = (await db_session.execute(select(User).where(User.sso_uid == IAM_UID))).scalars().all()
    assert len(count) == 1  # 没有重复开户


@pytest.mark.asyncio
async def test_callback_refuses_to_take_over_local_account(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    local = await _add_user(db_session, username=IAM_USERNAME, auth_source=AuthSource.LOCAL.value)
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=conflict"
    assert "cpumodel_access" not in response.cookies
    await db_session.refresh(local)
    assert local.sso_uid is None  # 本地账号没有被悄悄绑定给统一认证身份


@pytest.mark.asyncio
async def test_callback_rejects_inactive_account(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    user = await _add_user(
        db_session,
        username=IAM_USERNAME,
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
        status=UserStatus.DISABLED.value,
    )
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=inactive"
    blob = _set_cookie_blob(response)
    for name in AUTH_COOKIE_NAMES:
        assert f"{name}=" not in blob
    assert any("Max-Age=0" in header for header in _state_cookie_headers(response))
    await db_session.refresh(user)
    assert user.last_login_at is None


@pytest.mark.asyncio
async def test_callback_reports_not_provisioned_when_auto_provision_disabled(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, monkeypatch
):
    monkeypatch.setattr(settings, "SSO_AUTO_PROVISION", False)
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=not_provisioned"
    assert (await db_session.execute(select(User))).scalars().all() == []


@pytest.mark.asyncio
async def test_callback_sanitizes_username_from_claim(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    _install_iam(_iam_handler(user_info={"userName": "张 三/../admin"}))
    _prime_state(client)

    await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    user = (await db_session.execute(select(User))).scalar_one()
    assert user.username == "admin" or all(
        ch.isalnum() or ch in "._-" for ch in user.username
    )
    assert "/" not in user.username and " " not in user.username


@pytest.mark.asyncio
async def test_callback_clips_overlong_iam_fields(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    """X6：IAM 字段没有长度约束，落库前按列宽截断（PostgreSQL 否则报 DataError → 500）。"""
    _install_iam(
        _iam_handler(
            user_info={
                "userId": "u" * 300,
                "fullname": "名" * 300,
                "email": "a" * 250 + "@example.com",
            }
        )
    )
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/workspace"
    user = (await db_session.execute(select(User))).scalar_one()
    assert len(user.sso_uid) <= 128 and user.sso_uid == "u" * 128
    assert len(user.display_name) <= 100 and user.display_name == "名" * 100
    assert len(user.email) <= 255 and user.email == "a" * 250 + "@exam"


@pytest.mark.asyncio
async def test_callback_cookie_target_cannot_escape_site(
    client: httpx.AsyncClient, sso_settings
):
    """签名合法但目标越界：签名只保证「没被改」，不保证 target 可信。"""
    _install_iam(_iam_handler())
    client.cookies.set(
        STATE_COOKIE, _signed_state_cookie("state-1", "//evil.example"), path=STATE_COOKIE_PATH
    )

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/workspace"


# --------------------------------------------------------------------------- #
# 4. _safe_local_path（P4）
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    [
        "//evil.example",
        "https://evil.example",
        "http://evil.example",
        "/\\\\evil.example",
        "/a\r\nSet-Cookie: x=1",
        "javascript:alert(1)",
        "",
        "workspace",
    ],
)
def test_safe_local_path_rejects(value):
    assert sso_module._safe_local_path(value) is None


@pytest.mark.parametrize("value", ["/workspace", "/tasks?x=1#y", "/a/b/c"])
def test_safe_local_path_keeps(value):
    assert sso_module._safe_local_path(value) == value


def test_safe_local_path_truncates():
    assert len(sso_module._safe_local_path("/" + "a" * 600)) == 512


# --------------------------------------------------------------------------- #
# 5. disabled 分支与日志净化（X3 / X2）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_disabled_branches_clear_state_cookie(client: httpx.AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "SSO_ENABLED", False)

    for path in (
        "/api/v1/auth/sso/authorize",
        "/api/v1/auth/sso/callback?code=c1&state=s",
    ):
        response = await client.get(path)
        assert response.status_code == 303
        assert response.headers["location"] == "/login?sso_error=disabled"
        assert any("Max-Age=0" in header for header in _state_cookie_headers(response)), path


@pytest.mark.asyncio
async def test_callback_error_param_is_log_sanitized(
    client: httpx.AsyncClient, sso_settings, caplog
):
    """X2：``%0d%0a`` 能把一条日志伪造出两行，进日志前必须净化。"""
    _install_iam(_iam_handler())
    _prime_state(client)

    with caplog.at_level("INFO", logger="app.api.v1.auth_sso"):
        response = await client.get(
            "/api/v1/auth/sso/callback?code=c1&state=state-1&error=bad%0d%0a伪造行"
        )

    assert response.headers["location"] == "/login?sso_error=denied"
    lines = [
        record.getMessage()
        for record in caplog.records
        if record.name == "app.api.v1.auth_sso" and "error=" in record.getMessage()
    ]
    assert lines
    for line in lines:
        assert "\r" not in line
        assert "\n" not in line
        assert "?" in line


# --------------------------------------------------------------------------- #
# 6. 统一认证账号无平台口令（P3）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_sso_account_cannot_login_with_password(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    """sso 账号即使库里有 hash（管理员重置过的历史数据），口令登录也必须 401。"""
    await _add_user(
        db_session,
        username="sso-user",
        auth_source=AuthSource.SSO.value,
        sso_uid="iam-9",
        password_hash=hash_password("Pwd12345!"),
    )

    ok = await client.post(
        "/api/v1/auth/login",
        json={"username": "sso-user", "password": "Pwd12345!"},
    )
    assert ok.status_code == 401
    assert ok.json()["code"] == 40101
    assert ok.json()["message"] == "用户名或密码错误"
    assert "cpumodel_" not in _set_cookie_blob(ok)

    bad = await client.post(
        "/api/v1/auth/login",
        json={"username": "sso-user", "password": "{{SECRET_qm2wv7tx}}"},
    )
    assert bad.status_code == 401
    assert bad.json()["code"] == 40101
    assert bad.json()["message"] == "用户名或密码错误"


@pytest.mark.asyncio
async def test_admin_reset_password_rejects_sso_account(
    guards_client: httpx.AsyncClient, db_session: AsyncSession
):
    admin = await _add_user(db_session, username="admin", role=UserRole.ADMIN.value)
    sso_user = await _add_user(
        db_session,
        username="sso-target",
        auth_source=AuthSource.SSO.value,
        sso_uid="iam-9",
    )

    response = await guards_client.post(
        f"/api/v1/users/admin/{sso_user.id}/reset-password",
        json={"new_password": "LdapResetPass123"},
        headers={"Authorization": f"Bearer {admin.username}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 40002
    message = response.json()["message"]
    assert "统一认证" in message
    assert "LDAP" not in message
    await db_session.refresh(sso_user)
    assert sso_user.password_hash is None


@pytest.mark.asyncio
async def test_change_password_rejects_sso_account(
    guards_client: httpx.AsyncClient, db_session: AsyncSession
):
    sso_user = await _add_user(
        db_session,
        username="sso-self",
        auth_source=AuthSource.SSO.value,
        sso_uid="iam-9",
    )

    response = await guards_client.put(
        "/api/v1/users/me/password",
        json={
            "old_password": "LdapResetPass123",
            "new_password": "AnotherPass123",
        },
        headers={"Authorization": f"Bearer {sso_user.username}"},
    )

    assert response.status_code == 400  # 不再是 verify(None) 的 500
    assert response.json()["code"] == 40002
    assert "统一认证" in response.json()["message"]
    await db_session.refresh(sso_user)
    assert sso_user.password_hash is None


@pytest.mark.asyncio
async def test_ldap_guard_messages_unchanged(
    guards_client: httpx.AsyncClient, db_session: AsyncSession
):
    admin = await _add_user(db_session, username="admin-ldap", role=UserRole.ADMIN.value)
    ldap_user = await _add_user(db_session, username="ldap-user", auth_source=AuthSource.LDAP.value)

    reset = await guards_client.post(
        f"/api/v1/users/admin/{ldap_user.id}/reset-password",
        json={"new_password": "LdapResetPass123"},
        headers={"Authorization": f"Bearer {admin.username}"},
    )
    assert reset.status_code == 400
    assert reset.json()["code"] == 40002
    assert "企业目录" in reset.json()["message"]

    change = await guards_client.put(
        "/api/v1/users/me/password",
        json={
            "old_password": "LdapResetPass123",
            "new_password": "AnotherPass123",
        },
        headers={"Authorization": f"Bearer {ldap_user.username}"},
    )
    assert change.status_code == 400
    assert change.json()["code"] == 40002
    assert "企业目录" in change.json()["message"]


def test_verify_password_fails_closed():
    """D6：None / 空串 / 畸形 hash 一律 False，而不是 AttributeError/ValueError → 500。"""
    assert verify_password("x", None) is False
    assert verify_password("x", "") is False
    assert verify_password("x", "not-a-bcrypt-hash") is False

    hashed = hash_password("Pwd12345!")
    assert verify_password("Pwd12345!", hashed) is True
    assert verify_password("wrong", hashed) is False


# --------------------------------------------------------------------------- #
# 7. Cookie 标志位配置校验（D3）
#
# 规格上这两条属于 test/test_config_security.py::TestCookieSettings，本轮改动白名单
# 只放开了 test/test_sso_flow.py，故先落在这里；待白名单放开后迁回。
# --------------------------------------------------------------------------- #


def test_samesite_none_requires_secure_cookie():
    with pytest.raises(ValueError, match="COOKIE_SAMESITE=none requires COOKIE_SECURE"):
        Settings(ENVIRONMENT="development", COOKIE_SAMESITE="none", COOKIE_SECURE=False)


def test_samesite_none_with_secure_is_accepted():
    config = Settings(ENVIRONMENT="development", COOKIE_SAMESITE="none", COOKIE_SECURE=True)
    assert config.COOKIE_SAMESITE == "none"
    assert Settings(ENVIRONMENT="development").COOKIE_SAMESITE == "lax"
