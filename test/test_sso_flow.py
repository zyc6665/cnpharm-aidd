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
6. 统一认证账号在平台侧无口令：口令登录、自助改密、管理员重置全部拒绝（P3）；
7. 平台续期时同步校验甲方票据：有效/续期/宽限放行/判死（40103）、不滑动宽限锚点、
   不把 IAM 不可达误判成票据失效、失效后清三个 Cookie 且不成环；
8. 统一认证登出：CSRF、GLO 地址与回跳参数、local/ldap 与关闭 SSO 时不拼 GLO、幂等；
9. 前端接线守卫：登出跳转、``/auth/sso/logout`` 属于公共认证路径、``sso_logout`` 提示。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

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
from app.auth.jwt_handler import jwt_handler  # noqa: E402
from app.config import Settings, settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.common.time import utcnow  # noqa: E402
from app.models.refresh_tokens import RefreshToken  # noqa: E402
from app.models.users import AuthSource, User, UserRole, UserStatus  # noqa: E402
from app.services.iam_client import IamClient, get_iam_client  # noqa: E402
from app.services.iam_session import (  # noqa: E402
    IamTicketDecryptError,
    open_tickets,
    seal_tickets,
)
from app.services.refresh_token_store import (  # noqa: E402
    clear_iam_tickets,
    expires_at_from_payload,
    get_refresh_token,
    revoke_all_for_user,
    revoke_refresh_token,
    rotate_refresh_token,
    store_refresh_token,
    touch_iam_checked_at,
    update_iam_tickets,
)

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
    token_refresh: str | None = "iam-refresh",
    check_code: str = "9001",
    refresh_code: str = "9001",
    check_status: int = 200,
    refresh_status: int = 200,
    refreshed_access: str = "iam-access-2",
    refreshed_refresh: str | None = "iam-refresh-2",
    expires_in: int = 3600,
    calls: list[str] | None = None,
    check_calls: list[str] | None = None,
    refresh_calls: list[str] | None = None,
):
    """假的甲方 IAM：按路径应答 getToken / getUserInfo / checkAccessToken / refreshToken。

    ``calls`` 记录调用轨迹，让「失败路径零 IAM 调用」这类断言可观测；
    ``check_calls`` / ``refresh_calls`` 单独计数，方便断言「只校验不续期」。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/checkAccessToken"):
            if calls is not None:
                calls.append("checkAccessToken")
            if check_calls is not None:
                check_calls.append("checkAccessToken")
            if check_status != 200:
                return httpx.Response(
                    check_status, json={"code": "500", "message": "服务不可用"}
                )
            if check_code != "9001":
                return httpx.Response(200, json={"code": check_code, "message": "票据失效"})
            return httpx.Response(200, json={"code": "9001", "message": "操作成功"})
        if path.endswith("/refreshToken"):
            if calls is not None:
                calls.append("refreshToken")
            if refresh_calls is not None:
                refresh_calls.append("refreshToken")
            if refresh_status != 200:
                return httpx.Response(
                    refresh_status, json={"code": "500", "message": "服务不可用"}
                )
            if refresh_code != "9001":
                return httpx.Response(
                    200, json={"code": refresh_code, "message": "刷新票据失效"}
                )
            data = {"accessToken": refreshed_access, "expiresIn": expires_in}
            if refreshed_refresh is not None:
                data["refreshToken"] = refreshed_refresh
            return httpx.Response(200, json={"code": "9001", "message": "操作成功", "data": data})
        if calls is not None:
            calls.append("getToken" if path.endswith("/getToken") else "getUserInfo")
        if path.endswith("/getToken"):
            if token_code != "9001":
                return httpx.Response(200, json={"code": token_code, "message": "code 非法"})
            token_data: dict[str, object] = {
                "accessToken": "iam-access",
                "expiresIn": expires_in,
            }
            if token_refresh is not None:
                token_data["refreshToken"] = token_refresh
            return httpx.Response(
                200,
                json={"code": "9001", "message": "操作成功", "data": token_data},
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
async def test_callback_backfills_uid_for_preseeded_sso_user(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, monkeypatch
):
    """SSO_AUTO_PROVISION=false 的部署：管理员预建的 sso 账号（无口令、uid 为空）首次登录
    应按用户名匹配到同一行、回填 sso_uid，而不是报 not_provisioned 或重复开户。"""
    monkeypatch.setattr(settings, "SSO_AUTO_PROVISION", False)
    preseeded = await _add_user(
        db_session,
        username=IAM_USERNAME,
        auth_source=AuthSource.SSO.value,
        sso_uid=None,
    )
    assert preseeded.password_hash is None
    assert preseeded.sso_uid is None
    _install_iam(_iam_handler())
    _prime_state(client, target="/tasks")

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/tasks"
    assert "cpumodel_access=" in " ".join(response.headers.get_list("set-cookie"))

    await db_session.refresh(preseeded)
    assert preseeded.sso_uid == IAM_UID
    assert preseeded.auth_source == AuthSource.SSO.value
    assert preseeded.password_hash is None  # 回填过程中不得给 sso 账号补口令
    rows = (await db_session.execute(select(User))).scalars().all()
    assert len(rows) == 1  # 预建账号被复用，没有第二个开户


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


# --------------------------------------------------------------------------- #
# 8. IAM 票据持久化基座（加解密 / store 三函数 / 轮换搬家）
# --------------------------------------------------------------------------- #


def test_seal_tickets_roundtrip_and_ciphertext_differs_from_plaintext():
    """密文可逆，且库里存的绝不是票据原文。"""
    fixed_now = datetime(2026, 11, 13, 10, 0, 0)
    sealed = seal_tickets(
        access_token="iam-access",
        refresh_token="iam-refresh",
        expires_in=300,
        now=fixed_now,
    )

    assert set(sealed) == {
        "iam_access_token_enc",
        "iam_refresh_token_enc",
        "iam_access_expires_at",
        "iam_checked_at",
    }
    assert sealed["iam_access_token_enc"] != "iam-access"
    assert sealed["iam_refresh_token_enc"] != "iam-refresh"
    assert sealed["iam_access_expires_at"] == fixed_now + timedelta(seconds=300)
    assert sealed["iam_checked_at"] == fixed_now

    tickets = open_tickets(
        access_token_enc=sealed["iam_access_token_enc"],
        refresh_token_enc=sealed["iam_refresh_token_enc"],
        access_expires_at=sealed["iam_access_expires_at"],
        checked_at=sealed["iam_checked_at"],
    )
    assert tickets.access_token == "iam-access"
    assert tickets.refresh_token == "iam-refresh"
    assert tickets.access_expires_at == fixed_now + timedelta(seconds=300)
    assert tickets.checked_at == fixed_now


def test_seal_tickets_treats_missing_expires_in_as_immediately_expired():
    """甲方没给 expires_in 时按「立即过期」处理，下次续期直接走 refreshToken。"""
    fixed_now = datetime(2026, 11, 13, 10, 0, 0)
    sealed = seal_tickets(
        access_token="iam-access",
        refresh_token=None,
        expires_in=0,
        now=fixed_now,
    )

    assert sealed["iam_refresh_token_enc"] is None
    assert sealed["iam_access_expires_at"] == fixed_now


def test_open_tickets_rejects_tampered_ciphertext():
    """密文损坏/密钥轮换时抛专用异常，调用方按「票据失效」处理而不是 500。"""
    with pytest.raises(IamTicketDecryptError):
        open_tickets(
            access_token_enc="not-a-fernet-token",
            refresh_token_enc=None,
            access_expires_at=None,
            checked_at=None,
        )


async def _seed_iam_row(
    db: AsyncSession,
    user: User,
    *,
    jti: str = "jti-1",
    access_token: str = "iam-access",
    checked_at: datetime | None = None,
    access_expires_at: datetime | None = None,
) -> None:
    sealed = seal_tickets(
        access_token=access_token,
        refresh_token="iam-refresh",
        expires_in=3600,
        now=checked_at or utcnow(),
    )
    if checked_at is not None:
        sealed["iam_checked_at"] = checked_at
    if access_expires_at is not None:
        sealed["iam_access_expires_at"] = access_expires_at
    await store_refresh_token(
        db,
        jti=jti,
        user_id=user.id,
        expires_at=utcnow() + timedelta(days=1),
        **sealed,
    )
    await db.commit()


@pytest.mark.asyncio
async def test_update_iam_tickets_writes_all_four_columns(db_session: AsyncSession):
    user = await _add_user(
        db_session, username="sso-store", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    await _seed_iam_row(db_session, user)
    new_checked_at = utcnow() + timedelta(minutes=5)

    assert (
        await update_iam_tickets(
            db_session,
            "jti-1",
            access_token_enc="rotated-access-enc",
            refresh_token_enc=None,
            access_expires_at=None,
            checked_at=new_checked_at,
        )
        is True
    )
    await db_session.commit()

    row = await get_refresh_token(db_session, "jti-1")
    assert row is not None
    assert row.iam_access_token_enc == "rotated-access-enc"
    assert row.iam_refresh_token_enc is None
    assert row.iam_access_expires_at is None
    assert row.iam_checked_at == new_checked_at


@pytest.mark.asyncio
async def test_touch_iam_checked_at_keeps_other_columns(db_session: AsyncSession):
    user = await _add_user(
        db_session, username="sso-touch", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    await _seed_iam_row(db_session, user)
    before = await get_refresh_token(db_session, "jti-1")
    assert before is not None
    original_enc = before.iam_access_token_enc
    new_checked_at = utcnow() + timedelta(minutes=1)

    assert await touch_iam_checked_at(db_session, "jti-1", new_checked_at) is True
    await db_session.commit()

    after = await get_refresh_token(db_session, "jti-1")
    assert after is not None
    assert after.iam_checked_at == new_checked_at
    assert after.iam_access_token_enc == original_enc
    assert after.iam_access_expires_at is not None


@pytest.mark.asyncio
async def test_clear_iam_tickets_works_on_revoked_row(db_session: AsyncSession):
    """登出/判死时行已被吊销，clear 仍必须生效（不能带 revoked_at IS NULL）。"""
    user = await _add_user(
        db_session, username="sso-clear", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    await _seed_iam_row(db_session, user)
    await revoke_refresh_token(db_session, "jti-1")
    await db_session.commit()

    assert await clear_iam_tickets(db_session, "jti-1") is True
    await db_session.commit()

    row = await get_refresh_token(db_session, "jti-1")
    assert row is not None
    assert row.revoked_at is not None
    assert row.iam_access_token_enc is None
    assert row.iam_refresh_token_enc is None
    assert row.iam_access_expires_at is None
    assert row.iam_checked_at is None


@pytest.mark.asyncio
async def test_rotate_moves_iam_tickets_to_new_row_and_clears_old(db_session: AsyncSession):
    """轮换把票据搬到新行，旧行同一条 UPDATE 里清空，不留可用凭证。"""
    user = await _add_user(
        db_session, username="sso-rotate", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    await _seed_iam_row(db_session, user)
    old_row = await get_refresh_token(db_session, "jti-1")
    assert old_row is not None
    carried_enc = old_row.iam_access_token_enc

    result = await rotate_refresh_token(
        db_session,
        old_jti="jti-1",
        user_id=user.id,
        new_jti="jti-2",
        new_expires_at=utcnow() + timedelta(days=1),
    )
    await db_session.commit()

    assert result == "ok"
    old_after = await get_refresh_token(db_session, "jti-1")
    new_after = await get_refresh_token(db_session, "jti-2")
    assert old_after is not None and new_after is not None
    assert old_after.revoked_at is not None
    assert old_after.iam_access_token_enc is None
    assert old_after.iam_refresh_token_enc is None
    assert new_after.iam_access_token_enc == carried_enc
    assert new_after.iam_refresh_token_enc is not None


@pytest.mark.asyncio
async def test_revoke_all_for_user_clears_iam_tickets(db_session: AsyncSession):
    """复用入侵吊销全部会话时，顺手清空票据密文，缩短残留窗口。"""
    user = await _add_user(
        db_session, username="sso-revoke-all", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    await _seed_iam_row(db_session, user, jti="jti-a")
    second = await store_refresh_token(
        db_session,
        jti="jti-b",
        user_id=user.id,
        expires_at=utcnow() + timedelta(days=1),
        iam_access_token_enc="enc-b",
        iam_refresh_token_enc="enc-b-r",
        iam_access_expires_at=utcnow(),
        iam_checked_at=utcnow(),
    )
    assert second is not None
    await db_session.commit()

    revoked = await revoke_all_for_user(db_session, user.id)
    await db_session.commit()

    assert revoked == 2
    rows = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalars().all()
    assert len(rows) == 2
    for row in rows:
        assert row.revoked_at is not None
        assert row.iam_access_token_enc is None
        assert row.iam_refresh_token_enc is None
        assert row.iam_access_expires_at is None
        assert row.iam_checked_at is None


# --------------------------------------------------------------------------- #
# 9. 平台续期时的 IAM 票据校验（宽限放行 / 续期 / 判死）
# --------------------------------------------------------------------------- #


@pytest.fixture
def iam_refresh_settings(monkeypatch):
    """续期校验相关的全局开关（端点读的是全局 ``settings``）。"""
    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    monkeypatch.setattr(settings, "SSO_VALIDATE_ON_REFRESH", True)
    monkeypatch.setattr(settings, "SSO_OFFLINE_GRACE_SECONDS", 86400)
    return settings


def _refresh_cookie_value(response: httpx.Response) -> str:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith("cpumodel_refresh="):
            return header.split(";", 1)[0].split("=", 1)[1]
    raise AssertionError("响应未下发 cpumodel_refresh Cookie")


def _set_cookie_headers(response: httpx.Response) -> dict[str, str]:
    headers: dict[str, str] = {}
    for header in response.headers.get_list("set-cookie"):
        name = header.split("=", 1)[0]
        headers[name] = header.lower()
    return headers


async def _seed_sso_session(
    db: AsyncSession,
    user: User,
    *,
    access_token: str = "iam-access",
    refresh_token: str | None = "iam-refresh",
    access_expires_at: datetime | None = None,
    checked_at: datetime | None = None,
) -> str:
    """造一个「平台 refresh 行 + IAM 票据」，返回可直接塞 Cookie 的 refresh JWT。"""
    token = jwt_handler.create_refresh_token(user_id=user.id)
    payload = jwt_handler.decode_token(token) or {}
    sealed = seal_tickets(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=3600,
    )
    if access_expires_at is not None:
        sealed["iam_access_expires_at"] = access_expires_at
    if checked_at is not None:
        sealed["iam_checked_at"] = checked_at
    await store_refresh_token(
        db,
        jti=str(payload.get("jti") or ""),
        user_id=user.id,
        expires_at=expires_at_from_payload(payload),
        **sealed,
    )
    await db.commit()
    return token


def _offline_handler(calls: list[str] | None = None):
    """统一认证不可达：抛 httpx.ConnectError（传输层错误）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.path)
        raise httpx.ConnectError("统一认证不可达")

    return handler


def _check_expired_then_offline_handler(calls: list[str] | None = None):
    """check 明确说票据过期，但续期调用直接连接失败——两条分支的交叉场景。"""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/checkAccessToken"):
            if calls is not None:
                calls.append("checkAccessToken")
            return httpx.Response(200, json={"code": "2002", "message": "票据失效"})
        if path.endswith("/refreshToken"):
            if calls is not None:
                calls.append("refreshToken")
            raise httpx.ConnectError("统一认证续期接口不可达")
        raise AssertionError(f"unexpected path {path}")

    return handler


@pytest.mark.asyncio
async def test_refresh_keeps_tickets_when_iam_access_alive(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    checks: list[str] = []
    refreshes: list[str] = []
    _install_iam(_iam_handler(calls=calls, check_calls=checks, refresh_calls=refreshes))
    user = await _add_user(
        db_session, username="sso-alive", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user)
    old_jti = (jwt_handler.decode_token(token) or {}).get("jti")

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200
    assert calls == ["checkAccessToken"]
    assert len(checks) == 1 and refreshes == []
    new_jti = (jwt_handler.decode_token(_refresh_cookie_value(response)) or {}).get("jti")
    old_row = await get_refresh_token(db_session, old_jti)
    new_row = await get_refresh_token(db_session, new_jti)
    assert old_row is not None and old_row.revoked_at is not None
    assert old_row.iam_access_token_enc is None
    assert old_row.iam_refresh_token_enc is None
    assert new_row is not None
    assert new_row.iam_access_token_enc is not None
    assert new_row.iam_refresh_token_enc is not None
    assert new_row.iam_checked_at is not None


@pytest.mark.asyncio
async def test_refresh_renews_when_iam_access_expired(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    user = await _add_user(
        db_session, username="sso-expired", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(
        db_session, user, access_expires_at=utcnow() - timedelta(minutes=5)
    )

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200
    assert calls == ["refreshToken"]
    new_row = await get_refresh_token(
        db_session, (jwt_handler.decode_token(_refresh_cookie_value(response)) or {}).get("jti")
    )
    assert new_row is not None
    tickets = open_tickets(
        access_token_enc=new_row.iam_access_token_enc,
        refresh_token_enc=new_row.iam_refresh_token_enc,
        access_expires_at=new_row.iam_access_expires_at,
        checked_at=new_row.iam_checked_at,
    )
    assert tickets.access_token == "iam-access-2"
    assert tickets.refresh_token == "iam-refresh-2"

    # 续期成功必须重下三个 Cookie（access/refresh/csrf 一起换，避免只换一半）。
    assert set(_set_cookie_headers(response)) == set(AUTH_COOKIE_NAMES)


@pytest.mark.asyncio
async def test_refresh_falls_back_to_iam_refresh_on_code_2002(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    _install_iam(_iam_handler(check_code="2002", calls=calls))
    user = await _add_user(
        db_session, username="sso-2002", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200
    assert calls == ["checkAccessToken", "refreshToken"]
    new_row = await get_refresh_token(
        db_session, (jwt_handler.decode_token(_refresh_cookie_value(response)) or {}).get("jti")
    )
    assert new_row is not None
    tickets = open_tickets(
        access_token_enc=new_row.iam_access_token_enc,
        refresh_token_enc=new_row.iam_refresh_token_enc,
        access_expires_at=new_row.iam_access_expires_at,
        checked_at=new_row.iam_checked_at,
    )
    assert tickets.access_token == "iam-access-2"


@pytest.mark.asyncio
async def test_refresh_rejects_session_when_both_iam_codes_fail(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    _install_iam(_iam_handler(check_code="2002", refresh_code="2002", calls=calls))
    user = await _add_user(
        db_session, username="sso-dead", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user)
    old_jti = (jwt_handler.decode_token(token) or {}).get("jti")

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40103
    assert response.json()["detail"] == {"reason": "iam_session_expired"}
    assert calls == ["checkAccessToken", "refreshToken"]

    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert name in headers
        assert "max-age=0" in headers[name]

    rows = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalars().all()
    created = [row for row in rows if row.jti != old_jti]
    assert len(created) == 1
    assert created[0].revoked_at is not None
    assert created[0].iam_access_token_enc is None
    assert created[0].iam_refresh_token_enc is None
    assert created[0].iam_access_expires_at is None
    assert created[0].iam_checked_at is None


@pytest.mark.asyncio
async def test_refresh_renews_without_access_token(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    user = await _add_user(
        db_session, username="sso-no-access", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user, access_token="")

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200
    assert calls == ["refreshToken"]


@pytest.mark.asyncio
async def test_refresh_rejects_when_iam_refresh_code_invalid_without_access(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    """没有 access 时只剩 refreshToken 一条路；甲方回 2002 就只能判死，没有宽限。"""
    calls: list[str] = []
    _install_iam(_iam_handler(refresh_code="2002", calls=calls))
    user = await _add_user(
        db_session,
        username="sso-refresh-dead",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    token = await _seed_sso_session(db_session, user, access_token="")
    old_jti = (jwt_handler.decode_token(token) or {}).get("jti")

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40103
    assert response.json()["detail"] == {"reason": "iam_session_expired"}
    assert calls == ["refreshToken"]

    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert name in headers
        assert "max-age=0" in headers[name]

    rows = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalars().all()
    created = [row for row in rows if row.jti != old_jti]
    assert len(created) == 1
    assert created[0].revoked_at is not None
    assert created[0].iam_access_token_enc is None
    assert created[0].iam_refresh_token_enc is None


@pytest.mark.asyncio
async def test_refresh_rejects_sso_session_without_tickets(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    """迁移前的存量 SSO 会话没有票据：直接判死，且不打扰 IAM。"""
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    user = await _add_user(
        db_session, username="sso-legacy", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = jwt_handler.create_refresh_token(user_id=user.id)
    payload = jwt_handler.decode_token(token) or {}
    await store_refresh_token(
        db_session,
        jti=str(payload.get("jti") or ""),
        user_id=user.id,
        expires_at=expires_at_from_payload(payload),
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40103
    assert calls == []


@pytest.mark.asyncio
async def test_refresh_passes_within_grace_when_iam_unreachable(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    _install_iam(_offline_handler(calls))
    user = await _add_user(
        db_session, username="sso-grace", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    anchor = utcnow() - timedelta(hours=1)
    token = await _seed_sso_session(db_session, user, checked_at=anchor)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200
    assert len(calls) == 1 and calls[0].endswith("/checkAccessToken")
    new_row = await get_refresh_token(
        db_session, (jwt_handler.decode_token(_refresh_cookie_value(response)) or {}).get("jti")
    )
    assert new_row is not None
    # 失败放行不得刷新锚点，否则 IAM 长期故障会变成永久放行。
    assert new_row.iam_checked_at == anchor


@pytest.mark.asyncio
async def test_refresh_rejects_when_grace_exhausted(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    _install_iam(_offline_handler(calls))
    user = await _add_user(
        db_session, username="sso-grace-dead", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(
        db_session, user, checked_at=utcnow() - timedelta(hours=25)
    )
    old_jti = (jwt_handler.decode_token(token) or {}).get("jti")

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40103
    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert "max-age=0" in headers[name]

    # 宽限耗尽同样要吊销「刚轮换出来但没下发」的新 jti，否则留下一个孤儿会话。
    rows = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalars().all()
    created = [row for row in rows if row.jti != old_jti]
    assert len(created) == 1
    assert created[0].revoked_at is not None
    assert created[0].iam_refresh_token_enc is None


@pytest.mark.asyncio
async def test_refresh_passes_when_iam_returns_http_503(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    _install_iam(_iam_handler(check_status=503, calls=calls))
    user = await _add_user(
        db_session, username="sso-503", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    anchor = utcnow() - timedelta(minutes=10)
    token = await _seed_sso_session(db_session, user, checked_at=anchor)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200
    assert calls == ["checkAccessToken"]
    new_row = await get_refresh_token(
        db_session, (jwt_handler.decode_token(_refresh_cookie_value(response)) or {}).get("jti")
    )
    assert new_row is not None and new_row.iam_checked_at == anchor


@pytest.mark.asyncio
async def test_refresh_treats_iam_refresh_transport_failure_as_unavailable(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    """check 说票据过期、续期时连接失败：归入「不可达」而非「失效」，宽限期内放行。

    这条分支很容易被写成「续期失败就判死」——那会把一次网络抖动变成全体掉线。
    """
    calls: list[str] = []
    _install_iam(_check_expired_then_offline_handler(calls))
    user = await _add_user(
        db_session,
        username="sso-refresh-offline",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    anchor = utcnow() - timedelta(hours=1)
    token = await _seed_sso_session(db_session, user, checked_at=anchor)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200, response.text
    assert calls == ["checkAccessToken", "refreshToken"]
    new_row = await get_refresh_token(
        db_session, (jwt_handler.decode_token(_refresh_cookie_value(response)) or {}).get("jti")
    )
    assert new_row is not None
    # 与 check 阶段不可达一致：放行但不推进锚点。
    assert new_row.iam_checked_at == anchor


@pytest.mark.asyncio
async def test_refresh_fails_closed_when_offline_grace_is_zero(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings, monkeypatch
):
    """``SSO_OFFLINE_GRACE_SECONDS=0`` 是严格失败关闭：锚点再新也不放行。"""
    monkeypatch.setattr(settings, "SSO_OFFLINE_GRACE_SECONDS", 0)
    calls: list[str] = []
    _install_iam(_offline_handler(calls))
    user = await _add_user(
        db_session,
        username="sso-strict",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    # 锚点取「刚刚校验成功」，用来证明 0 不是「相差 0 秒恰好放行」。
    token = await _seed_sso_session(db_session, user, checked_at=utcnow())
    old_jti = (jwt_handler.decode_token(token) or {}).get("jti")

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40103
    assert len(calls) == 1 and calls[0].endswith("/checkAccessToken")

    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert "max-age=0" in headers[name]

    rows = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalars().all()
    created = [row for row in rows if row.jti != old_jti]
    assert len(created) == 1 and created[0].revoked_at is not None


@pytest.mark.asyncio
async def test_refresh_does_not_slide_grace_anchor_across_failures(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    _install_iam(_offline_handler(calls))
    user = await _add_user(
        db_session, username="sso-anchor", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    anchor = utcnow() - timedelta(hours=20)
    token = await _seed_sso_session(db_session, user, checked_at=anchor)

    first = await client.post("/api/v1/auth/refresh", cookies={"cpumodel_refresh": token})
    assert first.status_code == 200
    second = await client.post(
        "/api/v1/auth/refresh",
        cookies={"cpumodel_refresh": _refresh_cookie_value(first)},
    )
    assert second.status_code == 200
    assert len(calls) == 2
    new_row = await get_refresh_token(
        db_session, (jwt_handler.decode_token(_refresh_cookie_value(second)) or {}).get("jti")
    )
    assert new_row is not None and new_row.iam_checked_at == anchor


@pytest.mark.asyncio
async def test_refresh_retries_on_iam_check_http_401(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    """check 直接回 HTTP 401 不等于票据已死：先给 refreshToken 一次自愈机会。"""
    calls: list[str] = []
    _install_iam(_iam_handler(check_status=401, calls=calls))
    user = await _add_user(
        db_session,
        username="sso-check-401",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    token = await _seed_sso_session(db_session, user)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200, response.text
    # 只有 check 的 401 没有直接判死，才可能继续走到 refreshToken。
    assert calls == ["checkAccessToken", "refreshToken"]
    new_row = await get_refresh_token(
        db_session, (jwt_handler.decode_token(_refresh_cookie_value(response)) or {}).get("jti")
    )
    assert new_row is not None
    assert new_row.iam_checked_at is not None


@pytest.mark.asyncio
async def test_refresh_rejects_session_when_iam_refresh_http_401(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    """check 与 refresh 都回 401：续期也被拒，说明票据确实失效。"""
    calls: list[str] = []
    _install_iam(_iam_handler(check_status=401, refresh_status=401, calls=calls))
    user = await _add_user(
        db_session,
        username="sso-refresh-401",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    token = await _seed_sso_session(db_session, user)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40103
    assert response.json()["detail"] == {"reason": "iam_session_expired"}
    assert calls == ["checkAccessToken", "refreshToken"]

    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert name in headers
        assert "max-age=0" in headers[name]


@pytest.mark.asyncio
async def test_refresh_grace_passes_on_iam_system_error_9100(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    """check 2002 + refresh 9100（系统异常）：归入不可达走宽限，锚点不滑动。"""
    calls: list[str] = []
    _install_iam(_iam_handler(check_code="2002", refresh_code="9100", calls=calls))
    user = await _add_user(
        db_session,
        username="sso-9100",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    anchor = utcnow() - timedelta(minutes=10)
    token = await _seed_sso_session(db_session, user, checked_at=anchor)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200, response.text
    assert calls == ["checkAccessToken", "refreshToken"]
    new_row = await get_refresh_token(
        db_session, (jwt_handler.decode_token(_refresh_cookie_value(response)) or {}).get("jti")
    )
    assert new_row is not None
    # 系统错误码只配「宽限」不配「续命」：锚点保持旧值，故障拖长也不会永久放行。
    assert new_row.iam_checked_at == anchor


@pytest.mark.asyncio
async def test_refresh_grace_passes_on_iam_system_error_9002(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    """check 与 refresh 都回 9002（参数错误）：配置问题不踢人，按不可达宽限放行。"""
    calls: list[str] = []
    _install_iam(_iam_handler(check_code="9002", refresh_code="9002", calls=calls))
    user = await _add_user(
        db_session,
        username="sso-9002",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    anchor = utcnow() - timedelta(minutes=10)
    token = await _seed_sso_session(db_session, user, checked_at=anchor)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200, response.text
    assert calls == ["checkAccessToken", "refreshToken"]
    new_row = await get_refresh_token(
        db_session, (jwt_handler.decode_token(_refresh_cookie_value(response)) or {}).get("jti")
    )
    assert new_row is not None
    assert new_row.iam_checked_at == anchor


@pytest.mark.asyncio
async def test_refresh_fails_closed_when_iam_anchor_missing(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    """B2 回归：有密文但 ``iam_checked_at`` 为空的行不得每次重新起算宽限。"""
    calls: list[str] = []
    _install_iam(_offline_handler(calls))
    user = await _add_user(
        db_session,
        username="sso-no-anchor",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    token = await _seed_sso_session(db_session, user)
    jti = (jwt_handler.decode_token(token) or {}).get("jti")
    assert await touch_iam_checked_at(db_session, str(jti), None) is True
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40103
    assert len(calls) == 1 and calls[0].endswith("/checkAccessToken")

    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert name in headers
        assert "max-age=0" in headers[name]


@pytest.mark.asyncio
async def test_refresh_skips_iam_when_validation_disabled(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings, monkeypatch
):
    monkeypatch.setattr(settings, "SSO_VALIDATE_ON_REFRESH", False)
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    user = await _add_user(
        db_session, username="sso-skip", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200
    assert calls == []

    # 不校验不等于丢票据：轮换仍要把密文搬到新行，以后重新开启校验才有东西可用。
    new_jti = (jwt_handler.decode_token(_refresh_cookie_value(response)) or {}).get("jti")
    new_row = await get_refresh_token(db_session, new_jti)
    assert new_row is not None
    assert new_row.iam_access_token_enc is not None
    assert new_row.iam_refresh_token_enc is not None
    old_row = await get_refresh_token(db_session, (jwt_handler.decode_token(token) or {}).get("jti"))
    assert old_row is not None and old_row.iam_access_token_enc is None


@pytest.mark.asyncio
async def test_refresh_skips_iam_when_sso_disabled(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings, monkeypatch
):
    monkeypatch.setattr(settings, "SSO_ENABLED", False)
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    user = await _add_user(
        db_session, username="sso-off", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200
    assert calls == []


@pytest.mark.asyncio
async def test_refresh_skips_iam_for_local_user(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    user = await _add_user(db_session, username="local-refresh")
    token = await _seed_sso_session(db_session, user)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200
    assert calls == []


@pytest.mark.asyncio
async def test_refresh_skips_iam_when_client_unavailable(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    app.dependency_overrides[get_iam_client] = lambda: None
    user = await _add_user(
        db_session, username="sso-no-client", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user)

    response = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )

    assert response.status_code == 200
    assert calls == []


@pytest.mark.asyncio
async def test_refresh_reuse_detection_consumes_iam_refresh_only_once(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    """两个标签同时刷新：只有轮换成功的那个会消费甲方单次 refreshToken。"""
    refreshes: list[str] = []
    _install_iam(_iam_handler(refresh_calls=refreshes))
    user = await _add_user(
        db_session, username="sso-reuse", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(
        db_session, user, access_expires_at=utcnow() - timedelta(minutes=5)
    )
    old_jti = (jwt_handler.decode_token(token) or {}).get("jti")

    first = await client.post("/api/v1/auth/refresh", cookies={"cpumodel_refresh": token})
    assert first.status_code == 200
    assert len(refreshes) == 1
    new_jti = (jwt_handler.decode_token(_refresh_cookie_value(first)) or {}).get("jti")

    second = await client.post("/api/v1/auth/refresh", cookies={"cpumodel_refresh": token})
    assert second.status_code == 401
    assert len(refreshes) == 1
    reused = await get_refresh_token(db_session, old_jti)
    rolled = await get_refresh_token(db_session, new_jti)
    assert reused is not None and reused.revoked_at is not None
    assert rolled is not None and rolled.revoked_at is not None


@pytest.mark.asyncio
async def test_refresh_does_not_loop_after_iam_session_killed(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings
):
    """40103 之后 Cookie 已被删除：再刷新没有凭证直接 401，不会再打 IAM（不成环）。

    前端 ``shouldAttemptTokenRefresh('/auth/refresh')`` 为 false，这里从服务端再兜一层：
    失效响应必须把 ``cpumodel_refresh`` 一起清掉，否则「刷新→401→再刷新」会一直转。
    """
    calls: list[str] = []
    _install_iam(_iam_handler(check_code="2002", refresh_code="2002", calls=calls))
    user = await _add_user(
        db_session,
        username="sso-loop",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    token = await _seed_sso_session(db_session, user)

    first = await client.post(
        "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
    )
    assert first.status_code == 401
    assert first.json()["code"] == 40103
    # 服务端删 Cookie 后客户端 jar 里不应再留着可用凭证。
    assert client.cookies.get("cpumodel_refresh") is None
    calls_after_first = list(calls)
    assert calls_after_first == ["checkAccessToken", "refreshToken"]

    rows_before = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalars().all()

    second = await client.post("/api/v1/auth/refresh")

    assert second.status_code == 401
    # 缺令牌是普通未授权（业务码 401），不是又一次「IAM 会话失效」，也不是 500。
    assert second.json()["code"] == 401
    assert calls == calls_after_first

    rows_after = (
        await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    ).scalars().all()
    assert sorted(row.jti for row in rows_after) == sorted(row.jti for row in rows_before)


@pytest.mark.asyncio
async def test_refresh_rejects_tampered_ciphertext(
    db_session: AsyncSession, client: httpx.AsyncClient, iam_refresh_settings, caplog
):
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    user = await _add_user(
        db_session, username="sso-tampered", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user)
    jti = (jwt_handler.decode_token(token) or {}).get("jti")
    await update_iam_tickets(
        db_session,
        jti,
        access_token_enc="not-a-fernet-token",
        refresh_token_enc="also-broken",
        access_expires_at=utcnow(),
        checked_at=utcnow(),
    )
    await db_session.commit()

    with caplog.at_level(logging.ERROR, logger="app.api.v1.auth"):
        response = await client.post(
            "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
        )

    assert response.status_code == 401
    assert response.json()["code"] == 40103
    assert calls == []
    # 密钥轮换/密文损坏必须留痕，否则运维只能看到一个没有上下文的 401。
    assert "统一认证票据解密失败" in caplog.text



# --------------------------------------------------------------------------- #
# 10. callback 落票据与统一认证登出（POST /auth/sso/logout）
# --------------------------------------------------------------------------- #


def _glo_query(url: str) -> dict[str, list[str]]:
    """把 GLO 地址拆成 query 字典，便于逐项断言参数名（含甲方拼写 redirctToUrl）。"""
    return parse_qs(urlsplit(url).query)


async def _login_via_sso(
    http: httpx.AsyncClient, *, handler=None
) -> httpx.Response:
    """走一遍完整回调，把三个平台认证 Cookie 装进 cookie jar。"""
    _install_iam(handler or _iam_handler())
    _prime_state(http)
    response = await http.get("/api/v1/auth/sso/callback?code=c1&state=state-1")
    assert response.status_code == 303
    assert response.headers["location"] == "/workspace"
    return response


async def _latest_refresh_row(db: AsyncSession, user: User) -> RefreshToken:
    result = await db.execute(
        select(RefreshToken)
        .where(RefreshToken.user_id == user.id)
        .order_by(RefreshToken.created_at.desc())
    )
    row = result.scalars().first()
    assert row is not None
    return row


class _FakeAudit:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def log_login(self, **kwargs) -> None:  # 回调也会写登录审计，这里不需要断言
        pass

    def log_logout(self, **kwargs) -> None:
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_callback_persists_encrypted_iam_tickets(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    before = utcnow()

    await _login_via_sso(client)

    user = (
        await db_session.execute(select(User).where(User.sso_uid == IAM_UID))
    ).scalar_one()
    row = await _latest_refresh_row(db_session, user)
    assert row.iam_access_token_enc  # 密文非空
    assert row.iam_access_token_enc != "iam-access"  # 不是明文
    assert row.iam_refresh_token_enc and row.iam_refresh_token_enc != "iam-refresh"
    assert row.iam_access_expires_at is not None
    assert row.iam_access_expires_at >= before + timedelta(seconds=3500)
    assert row.iam_access_expires_at <= utcnow() + timedelta(seconds=3700)
    assert row.iam_checked_at is not None
    assert row.iam_checked_at >= before


@pytest.mark.asyncio
async def test_callback_without_iam_refresh_token_keeps_platform_session(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, caplog
):
    """甲方不返回 refreshToken 时登录照常成功，但 access 过期后平台续期必须 40103。"""
    with caplog.at_level(logging.WARNING, logger="app.api.v1.auth_sso"):
        await _login_via_sso(client, handler=_iam_handler(token_refresh=None))

    # 缺 refreshToken 是「以后一定会到期」的隐患，必须留下可检索的日志。
    assert "统一认证未返回 refreshToken" in caplog.text

    user = (
        await db_session.execute(select(User).where(User.sso_uid == IAM_UID))
    ).scalar_one()
    row = await _latest_refresh_row(db_session, user)
    assert row.iam_access_token_enc
    assert row.iam_refresh_token_enc is None

    # 把 IAM access 的有效期拨到过去：平台续期时只能走 refresh 分支，而票据缺失
    row.iam_access_expires_at = utcnow() - timedelta(minutes=5)
    await db_session.commit()

    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json()["code"] == 40103


@pytest.mark.asyncio
async def test_sso_logout_returns_glo_url_and_clears_session(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, monkeypatch
):
    # 默认回跳地址由 SSO_REDIRECT_URI 推导；这里显式给出线上同源形态
    monkeypatch.setattr(
        settings,
        "SSO_REDIRECT_URI",
        "https://platform.example/api/v1/auth/sso/callback",
    )
    monkeypatch.setattr(settings, "SSO_LOGOUT_REDIRECT_URI", "")
    await _login_via_sso(client)
    csrf = client.cookies.get("cpumodel_csrf")
    refresh = client.cookies.get("cpumodel_refresh")
    assert csrf and refresh
    payload = jwt_handler.decode_token(refresh)
    assert payload is not None
    jti = str(payload["jti"])
    user = (
        await db_session.execute(select(User).where(User.sso_uid == IAM_UID))
    ).scalar_one()

    response = await client.post(
        "/api/v1/auth/sso/logout", headers={"X-CSRF-Token": csrf}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    logout_url = body["data"]["logout_url"]
    assert logout_url.startswith("https://iam.example/auth/api/user/webungateway/GLO?")
    query = _glo_query(logout_url)
    assert query["redirctToUrl"] == ["https://platform.example/login?sso_logout=1"]
    assert query["redirectToLogin"] == ["false"]
    assert query["appId"] == ["cnpharm-aidd"]

    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert name in headers
        assert "max-age=0" in headers[name] or "expires=" in headers[name]

    # 平台会话被吊销，且 IAM 票据同步清空（避免已吊销行还留着可用的 refreshToken）
    await db_session.refresh(user)
    row = await get_refresh_token(db_session, jti)
    assert row is not None
    assert row.revoked_at is not None
    assert row.iam_access_token_enc is None
    assert row.iam_refresh_token_enc is None


@pytest.mark.asyncio
async def test_sso_logout_requires_csrf_when_cookie_present(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    await _login_via_sso(client)
    refresh = client.cookies.get("cpumodel_refresh")
    payload = jwt_handler.decode_token(refresh)
    jti = str(payload["jti"])

    response = await client.post("/api/v1/auth/sso/logout")

    assert response.status_code == 403
    assert "CSRF" in response.text
    row = await get_refresh_token(db_session, jti)
    assert row is not None
    assert row.revoked_at is None  # 校验失败不得动会话


@pytest.mark.asyncio
async def test_sso_logout_without_cookies_is_idempotent(client: httpx.AsyncClient, sso_settings):
    response = await client.post("/api/v1/auth/sso/logout")

    assert response.status_code == 200
    assert response.json()["data"]["logout_url"] is None


@pytest.mark.asyncio
async def test_sso_logout_skips_glo_for_local_user(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    user = await _add_user(db_session, username="local-out")
    token = await _seed_sso_session(db_session, user)
    client.cookies.set("cpumodel_refresh", token, path="/api/v1/auth")
    client.cookies.set("cpumodel_csrf", "csrf-value", path="/")

    response = await client.post(
        "/api/v1/auth/sso/logout", headers={"X-CSRF-Token": "csrf-value"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["logout_url"] is None
    # 本地/域账号不该被送到统一认证登出页。
    assert calls == []
    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert "max-age=0" in headers[name] or "expires=" in headers[name]
    row = await _latest_refresh_row(db_session, user)
    assert row.revoked_at is not None


@pytest.mark.asyncio
async def test_sso_logout_skips_glo_when_sso_disabled(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, monkeypatch
):
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    user = await _add_user(
        db_session, username="sso-out", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user)
    client.cookies.set("cpumodel_refresh", token, path="/api/v1/auth")
    client.cookies.set("cpumodel_csrf", "csrf-value", path="/")
    monkeypatch.setattr(settings, "SSO_ENABLED", False)

    response = await client.post(
        "/api/v1/auth/sso/logout", headers={"X-CSRF-Token": "csrf-value"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["logout_url"] is None
    # 关掉 SSO 后即使该用户历史上来自 sso，也不应再拼 GLO 地址。
    assert calls == []


@pytest.mark.asyncio
async def test_sso_logout_works_without_valid_access_token(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    """登出不依赖 get_current_user：access 过期/被篡改也要能退出。"""
    _install_iam(_iam_handler())
    user = await _add_user(
        db_session, username="sso-expired", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user)
    client.cookies.set("cpumodel_access", "expired-access-cookie", path="/")
    client.cookies.set("cpumodel_refresh", token, path="/api/v1/auth")
    client.cookies.set("cpumodel_csrf", "csrf-value", path="/")

    response = await client.post(
        "/api/v1/auth/sso/logout", headers={"X-CSRF-Token": "csrf-value"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["logout_url"] is not None


@pytest.mark.asyncio
async def test_sso_logout_tolerates_garbage_refresh_cookie(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    client.cookies.set("cpumodel_refresh", "not-a-jwt", path="/api/v1/auth")
    client.cookies.set("cpumodel_csrf", "csrf-value", path="/")

    response = await client.post(
        "/api/v1/auth/sso/logout", headers={"X-CSRF-Token": "csrf-value"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["logout_url"] is None
    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert "max-age=0" in headers[name] or "expires=" in headers[name]


@pytest.mark.asyncio
async def test_sso_logout_honours_override_redirect(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, monkeypatch
):
    override = "https://portal.example.internal/login?sso_logout=1"
    monkeypatch.setattr(settings, "SSO_LOGOUT_REDIRECT_URI", override)
    await _login_via_sso(client)
    csrf = client.cookies.get("cpumodel_csrf")

    response = await client.post(
        "/api/v1/auth/sso/logout", headers={"X-CSRF-Token": csrf}
    )

    logout_url = response.json()["data"]["logout_url"]
    assert _glo_query(logout_url)["redirctToUrl"] == [override]


@pytest.mark.asyncio
async def test_sso_logout_audits_only_identified_user(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, monkeypatch
):
    fake = _FakeAudit()
    monkeypatch.setattr(sso_module, "get_audit_logger", lambda: fake)

    await _login_via_sso(client)
    csrf = client.cookies.get("cpumodel_csrf")
    user = (
        await db_session.execute(select(User).where(User.sso_uid == IAM_UID))
    ).scalar_one()

    await client.post("/api/v1/auth/sso/logout", headers={"X-CSRF-Token": csrf})

    assert len(fake.calls) == 1
    assert fake.calls[0]["user_id"] == str(user.id)

    # 无法识别用户时不写审计（登出仍然幂等成功）
    client.cookies.clear()
    client.cookies.set("cpumodel_refresh", "garbage", path="/api/v1/auth")
    client.cookies.set("cpumodel_csrf", "csrf-value", path="/")
    again = await client.post(
        "/api/v1/auth/sso/logout", headers={"X-CSRF-Token": "csrf-value"}
    )
    assert again.status_code == 200
    assert len(fake.calls) == 1


# --------------------------------------------------------------------------- #
# 11. 前端接线守卫（vitest 之外的源码级兜底：验收命令只跑后端）
# --------------------------------------------------------------------------- #
FRONTEND_SRC = PROJECT_ROOT / "frontend" / "src"


def _frontend_source(relative_path: str) -> str:
    return (FRONTEND_SRC / relative_path).read_text(encoding="utf-8")


def test_frontend_treats_sso_logout_as_public_auth_path():
    """登出接口自身 401 不得再触发 /auth/refresh，否则可能递归刷新。"""
    policy = _frontend_source("api/auth-request-policy.ts")
    assert "'/auth/sso/logout'" in policy


def test_frontend_logout_uses_glo_redirect_url():
    """登出必须走「POST 换 URL + 顶层跳转」，而不是 axios 跟随 302（JS 读不到）。"""
    api = _frontend_source("api/auth.ts")
    assert "ssoLogout" in api
    store = _frontend_source("stores/user.ts")
    assert "ssoLogout" in store
    page = _frontend_source("views/user/index.vue")
    assert "window.location.assign(logoutUrl)" in page
    assert "router.push('/')" in page


def test_frontend_login_page_handles_sso_logout_query():
    """GLO 回跳 ``/login?sso_logout=1`` 要提示一次并去掉 query，避免刷新后重复提示。"""
    login = _frontend_source("views/auth/Login.vue")
    assert "route.query.sso_logout" in login
    assert "ssoLogoutSuccess" in login
    # 双语键必须同时存在，否则 en 界面会显示原始 key。
    assert "ssoLogoutSuccess" in _frontend_source("locales/zh-CN/index.ts")
    assert "ssoLogoutSuccess" in _frontend_source("locales/en-US/index.ts")


def test_frontend_wires_sso_login_and_session_expiry():
    """前端接线兜底：入口按钮、?sso_error 文案、iam_session_expired 单点决策都必须落地。"""
    login = _frontend_source("views/auth/Login.vue")
    for token in ("getSsoStatus", "sso_error", "ssoLogin", "navigateToSso"):
        assert token in login

    request = _frontend_source("api/request.ts")
    assert "applySessionInvalid" in request
    assert "rememberRefreshFailure" in request
    session = _frontend_source("api/sso-session.ts")
    assert "applySessionInvalid" in session
    assert "iam_session_expired" in _frontend_source("utils/sso.ts")
    assert "iam_session_expired" in session

    for locale in ("locales/zh-CN/index.ts", "locales/en-US/index.ts"):
        source = _frontend_source(locale)
        assert "ssoError" in source
        assert "not_provisioned" in source
        assert "authSourceSso" in source
