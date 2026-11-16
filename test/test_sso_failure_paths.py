# test/test_sso_failure_paths.py
"""统一认证**失败路径**收口测试（评审项 A-01/A-02/A-03/A-04/A-05/A-07/A-09/C-02/S-02）。

与 ``test/test_sso_flow.py`` 的分工：那个文件测「成功链路 + 既有守卫」，本文件只测
「失败时到底发生了什么」——有没有审计、有没有把半截账号写进库、有没有清 state
Cookie、公开码有没有泄漏内部信息、登出/续期失败时 Cookie 是否被误删。

三条与本文件成败直接相关的设计取舍：

1. **``get_db`` 覆盖成生产同构**（``yield`` 之后无条件 ``commit``，镜像
   ``backend/app/database/session.py:77-87``）。若照旧只 ``yield`` 不提交，
   「停用账号被回填 sso_uid」「落库失败留下半截账号」这类脏写永远不会落库，
   断言只能假绿。
2. **审计用替身**（``monkeypatch.setattr(sso_module, "get_audit_logger", ...)``）
   而不是读日志：审计字段（reason/branch/sso_uid/error_type）是可聚合的契约，
   必须逐字段断言，不能靠 grep 文本。
3. **公开码与内部原因分开断言**：URL 里只能出现 9 个公开码，``reason`` 只进审计。
   这条边界是本轮收口的核心，写错一次就等于把内部细节泄给浏览器。
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import re
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.requests import Request as StarletteRequest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models as _models  # noqa: F401,E402  注册全部表
from app.api.v1 import auth as auth_module  # noqa: E402
from app.api.v1 import auth_sso as sso_module  # noqa: E402
from app.auth.jwt_handler import jwt_handler  # noqa: E402
from app.common.time import utcnow  # noqa: E402
from app.config import Settings, settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.logging.audit import AuditResult  # noqa: E402
from app.main import app  # noqa: E402
from app.models.refresh_tokens import RefreshToken  # noqa: E402
from app.models.users import AuthSource, User, UserStatus  # noqa: E402
from app.services.iam_client import IamClient, get_iam_client  # noqa: E402
from app.services.iam_session import seal_tickets  # noqa: E402
from app.services.refresh_token_store import (  # noqa: E402
    expires_at_from_payload,
    get_refresh_token,
    store_refresh_token,
)

SSO_SOURCE = PROJECT_ROOT / "backend" / "app" / "api" / "v1" / "auth_sso.py"
FRONTEND_SSO = PROJECT_ROOT / "frontend" / "src" / "utils" / "sso.ts"

IAM_UID = "iam-0001"
IAM_USERNAME = "zhangsan"
STATE_COOKIE = "cpumodel_sso_state"
STATE_COOKIE_PATH = "/api/v1/auth/sso"
AUTH_COOKIE_NAMES = ("cpumodel_access", "cpumodel_refresh", "cpumodel_csrf")

#: 前端 ``SSO_ERROR_CODES`` 的同一组码：公开码表**不允许**新增（新增一个就意味着
#: 中英 locales 各加一条翻译，且历史版本前端会显示原始 key）。
PUBLIC_CODES = {
    "disabled",
    "state",
    "denied",
    "token",
    "userinfo",
    "unavailable",
    "conflict",
    "inactive",
    "not_provisioned",
}

#: 内部失败原因词表（只进审计/日志）。值被冻结在这里，是为了防止有人把自由文本
#: （「用户不存在」之类）塞进 ``reason``——那样告警规则与统计口径会立刻失效。
INTERNAL_REASONS = {
    "sso_disabled",
    "state_mismatch",
    "access_denied",
    "token_exchange_failed",
    "token_exchange_unavailable",
    "token_exchange_unexpected",
    "userinfo_failed",
    "userinfo_unavailable",
    "userinfo_unexpected",
    "account_conflict",
    "account_inactive",
    "not_provisioned",
    "provision_unexpected",
    "session_persist_failed",
    # 回调既没带 code 也没带 error：公开码仍是 denied，但要和「用户点了拒绝」分开计数。
    "malformed_callback",
}


# --------------------------------------------------------------------------- #
# 夹具：与生产同构的 DB 会话 / 客户端
# --------------------------------------------------------------------------- #


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
    """``get_db`` 覆盖成**生产同构**：``yield`` 之后无条件 commit。

    ``backend/app/database/session.py:77-87`` 就是这么写的，而 A-02 的脏写正是被这句
    无条件 commit 落库的。用例若只 ``yield`` 不提交，就永远看不到脏写。
    """

    async def override_get_db():
        try:
            yield db_session
        except Exception:
            # 生产侧：异常 -> rollback 再抛出（与 session.py 的 except 分支一致）。
            await db_session.rollback()
            raise
        await db_session.commit()

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    app.dependency_overrides.clear()


@pytest.fixture
def sso_settings(monkeypatch):
    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    monkeypatch.setattr(settings, "SSO_SUCCESS_PATH", "/workspace")
    monkeypatch.setattr(settings, "SSO_AUTO_PROVISION", True)
    monkeypatch.setattr(settings, "SSO_USERNAME_CLAIM", "userName")
    return settings


@pytest.fixture
def iam_refresh_settings(monkeypatch):
    """续期校验相关开关（S-02 的两条用例需要）。"""
    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    monkeypatch.setattr(settings, "SSO_VALIDATE_ON_REFRESH", True)
    monkeypatch.setattr(settings, "SSO_OFFLINE_GRACE_SECONDS", 86400)
    return settings


class _FakeAudit:
    """记录 ``log_login`` / ``log_logout`` 的入参，供逐字段断言。"""

    def __init__(self) -> None:
        self.logins: list[dict] = []
        self.logouts: list[dict] = []

    def log_login(self, **kwargs) -> None:
        self.logins.append(kwargs)

    def log_logout(self, **kwargs) -> None:
        self.logouts.append(kwargs)


@pytest.fixture
def audit(monkeypatch) -> _FakeAudit:
    fake = _FakeAudit()
    monkeypatch.setattr(sso_module, "get_audit_logger", lambda: fake)
    return fake


# --------------------------------------------------------------------------- #
# 假的甲方 IAM + 各种小工具
# --------------------------------------------------------------------------- #


def _iam_settings() -> Settings:
    return Settings(
        ENVIRONMENT="development",
        SSO_ENABLED=True,
        SSO_BASE_URL="https://iam.example",
        SSO_APP_ID="cnpharm-aidd",
        SSO_CLIENT_SECRET="secret",
        SSO_REDIRECT_URI="https://platform.example/api/v1/auth/sso/callback",
    )


def _iam_handler(
    *,
    token_code: str = "9001",
    user_info: dict | None = None,
    user_info_code: str = "9001",
    check_code: str = "9001",
    calls: list[str] | None = None,
    transport_fail: set[str] | None = None,
):
    """假 IAM：``transport_fail`` 里的端点直接抛连接错误（传输层失败）。"""

    broken = transport_fail or set()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        kind = (
            "checkAccessToken"
            if path.endswith("/checkAccessToken")
            else "refreshToken"
            if path.endswith("/refreshToken")
            else "getToken"
            if path.endswith("/getToken")
            else "getUserInfo"
        )
        if calls is not None:
            calls.append(kind)
        if kind in broken:
            raise httpx.ConnectError("统一认证不可达")
        if kind == "checkAccessToken":
            if check_code != "9001":
                return httpx.Response(200, json={"code": check_code, "message": "票据失效"})
            return httpx.Response(200, json={"code": "9001", "message": "操作成功"})
        if kind == "refreshToken":
            return httpx.Response(
                200,
                json={
                    "code": "9001",
                    "message": "操作成功",
                    "data": {
                        "accessToken": "iam-access-renewed",
                        "refreshToken": "iam-refresh-renewed",
                        "expiresIn": 3600,
                    },
                },
            )
        if kind == "getToken":
            if token_code != "9001":
                return httpx.Response(200, json={"code": token_code, "message": "code 非法"})
            return httpx.Response(
                200,
                json={
                    "code": "9001",
                    "message": "操作成功",
                    "data": {
                        "accessToken": "iam-access",
                        "refreshToken": "iam-refresh",
                        "expiresIn": 3600,
                    },
                },
            )
        if user_info_code != "9001":
            return httpx.Response(200, json={"code": user_info_code, "message": "票据过期"})
        payload = {
            "userId": IAM_UID,
            "userName": IAM_USERNAME,
            "fullname": "张三",
            "email": "zhangsan@example.com",
            "orgs": [{"deptCode": "D01", "deptName": "信息中心"}],
        }
        payload.update(user_info or {})
        return httpx.Response(200, json={"code": "9001", "userInfo": payload})

    return handler


def _install_iam(handler) -> None:
    fake = IamClient(_iam_settings(), transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_iam_client] = lambda: fake


def _signed_state_cookie(state: str = "state-1", target: str = "/workspace") -> str:
    return sso_module._state_cookie_value(state, target)


def _prime_state(
    http: httpx.AsyncClient, state: str = "state-1", target: str = "/workspace"
) -> None:
    http.cookies.set(STATE_COOKIE, _signed_state_cookie(state, target), path=STATE_COOKIE_PATH)


def _set_cookie_list(response) -> list[str]:
    """统一取 ``Set-Cookie`` 列表：httpx 是 ``get_list``、Starlette 是 ``getlist``。"""
    headers = response.headers
    getter = getattr(headers, "get_list", None) or headers.getlist
    return list(getter("set-cookie"))


def _state_cookie_headers(response) -> list[str]:
    return [
        header
        for header in _set_cookie_list(response)
        if header.startswith(f"{STATE_COOKIE}=")
    ]


def _set_cookie_headers(response) -> dict[str, str]:
    headers: dict[str, str] = {}
    for header in _set_cookie_list(response):
        headers[header.split("=", 1)[0]] = header.lower()
    return headers


def _is_expired_cookie(header: str) -> bool:
    return "max-age=0" in header or "expires=" in header


async def _add_user(
    db: AsyncSession,
    *,
    username: str,
    auth_source: str = AuthSource.LOCAL.value,
    status: str = UserStatus.ACTIVE.value,
    sso_uid: str | None = None,
) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name=username,
        auth_source=auth_source,
        sso_uid=sso_uid,
        status=status,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _count(db: AsyncSession, model) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


async def _snapshot(db: AsyncSession, user_id) -> dict[str, object]:
    """把「不该被改」的四列取成普通值（ORM 对象在 rollback 后会过期）。"""
    row = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    return {
        "sso_uid": row.sso_uid,
        "display_name": row.display_name,
        "email": row.email,
        "last_login_at": row.last_login_at,
        "status": row.status,
    }


async def _login_via_sso(http: httpx.AsyncClient, *, handler=None) -> httpx.Response:
    """走一遍成功回调，把三枚平台 Cookie 装进 cookie jar。"""
    _install_iam(handler or _iam_handler())
    _prime_state(http)
    response = await http.get("/api/v1/auth/sso/callback?code=c1&state=state-1")
    assert response.status_code == 303
    assert response.headers["location"] == "/workspace"
    return response


async def _seed_sso_session(
    db: AsyncSession,
    user: User,
    *,
    access_expires_at=None,
) -> str:
    """造一个「平台 refresh 行 + IAM 票据」，返回可塞 Cookie 的 refresh JWT。"""
    token = jwt_handler.create_refresh_token(user_id=user.id)
    payload = jwt_handler.decode_token(token) or {}
    sealed = seal_tickets(access_token="iam-access", refresh_token="iam-refresh", expires_in=3600)
    if access_expires_at is not None:
        sealed["iam_access_expires_at"] = access_expires_at
    await store_refresh_token(
        db,
        jti=str(payload.get("jti") or ""),
        user_id=user.id,
        expires_at=expires_at_from_payload(payload),
        **sealed,
    )
    await db.commit()
    return token


def _bare_request() -> StarletteRequest:
    """不经过路由的最小请求对象：``_fail`` 只用到 client / headers。"""
    return StarletteRequest(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/sso/callback",
            "query_string": b"",
            "headers": [(b"user-agent", b"pytest-agent")],
            "client": ("127.0.0.1", 45678),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )


# --------------------------------------------------------------------------- #
# 1. 公开码 / 原因词表（T-01、T-16）
# --------------------------------------------------------------------------- #


def _module_tree() -> ast.Module:
    return ast.parse(SSO_SOURCE.read_text(encoding="utf-8"))


def _string_literals(node: ast.AST) -> set[str]:
    """收集节点下所有字符串常量（``a if c else b`` 两个分支都算）。"""
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def test_public_error_codes_are_frozen():
    """公开码只允许这 9 个：前端 ``SSO_ERROR_CODES`` 与后端白名单必须一致。"""
    codes: set[str] = set()
    for node in _module_tree().body:
        targets = getattr(node, "targets", [])
        if any(getattr(target, "id", "") == "_FAIL_PUBLIC_CODES" for target in targets):
            codes = _string_literals(node.value)
    assert codes == PUBLIC_CODES

    source = FRONTEND_SSO.read_text(encoding="utf-8")
    match = re.search(r"SSO_ERROR_CODES[^=]*=\s*\[(.*?)\]", source, re.S)
    assert match is not None
    frontend_codes = set(re.findall(r"['\"]([a-z_]+)['\"]", match.group(1)))
    # 前后端是两份独立常量：少一个前端就显示原始 key，多一个后端会静默降级。
    assert frontend_codes == PUBLIC_CODES


def test_internal_reason_vocabulary_is_frozen():
    """``reason`` 取值被冻结：改词/拼错都会被这条用例挡住。"""
    reasons: set[str] = set()
    for node in ast.walk(_module_tree()):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_fail"
            and len(node.args) >= 4
        ):
            reasons |= _string_literals(node.args[3])
    # 开户失败的三条原因来自映射表，源码里没有字面量，单独补上。
    reasons |= set(sso_module._PROVISION_REASON.values())
    assert reasons == INTERNAL_REASONS


# --------------------------------------------------------------------------- #
# 1b. 回跳目标净化：点段/双编码绕过（S-01）
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    [
        "/a/../b",  # 浏览器归一化后是 /b
        "/../../etc/passwd",
        "/%2e%2e/evil",  # 单层编码
        "/%252e%252e/evil",  # 双层编码：只解一层就会漏过去
        "/a/..%2fb",  # 编码的斜杠拼出点段
        "/a/./b",
        "/%2E%2E/%2E%2E/etc/passwd",  # 大写十六进制
    ],
)
def test_safe_local_path_rejects_dot_segments(value: str):
    """点段一律丢弃：它们是「站内路径」外形下唯一能改变目标目录的手段。"""
    assert sso_module._safe_local_path(value) is None


# --------------------------------------------------------------------------- #
# 2. _fail 自身（T-02）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fail_degrades_unknown_public_code(caplog):
    """未知公开码不外泄、也不 500：降级成 ``unavailable`` 并留 error 日志。"""
    with caplog.at_level(logging.ERROR, logger="app.api.v1.auth_sso"):
        response = await sso_module._fail(None, _bare_request(), "brand_new_code", "x")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?sso_error=unavailable"
    assert "不在白名单" in caplog.text
    # state Cookie 必须被清掉，否则下一次授权会带着旧 state。
    assert any(_is_expired_cookie(header) for header in _state_cookie_headers(response))


# --------------------------------------------------------------------------- #
# 3. state / denied（T-03、T-04）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_state_mismatch_is_audited(
    client: httpx.AsyncClient, sso_settings, audit: _FakeAudit
):
    calls: list[str] = []
    _install_iam(_iam_handler(calls=calls))
    _prime_state(client, state="expected")

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=forged")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?sso_error=state"
    assert calls == []  # state 不过关就不该碰 IAM
    assert len(audit.logins) == 1
    entry = audit.logins[0]
    assert entry["reason"] == "state_mismatch"
    assert entry["result"] is AuditResult.FAILURE
    assert entry["user_id"] is None
    # 设计要求 2：审计要能定位来源（IP + UA），但绝不能带凭据。
    assert entry["client_ip"] == "127.0.0.1"
    assert entry["user_agent"].startswith("python-httpx/")
    assert any(_is_expired_cookie(header) for header in _state_cookie_headers(response))


@pytest.mark.asyncio
async def test_access_denied_is_audited_and_log_is_sanitized(
    client: httpx.AsyncClient, sso_settings, audit: _FakeAudit, caplog
):
    """用户拒绝授权也要有审计；``error`` 参数是外部输入，进日志前必须净化。"""
    _install_iam(_iam_handler())
    _prime_state(client)

    with caplog.at_level(logging.WARNING, logger="app.api.v1.auth_sso"):
        response = await client.get(
            "/api/v1/auth/sso/callback?error=access_denied%0d%0aINJECTED&state=state-1"
        )

    assert response.status_code == 303
    # 注入内容不允许出现在跳转地址里。
    assert response.headers["location"] == "/login?sso_error=denied"
    assert len(audit.logins) == 1
    entry = audit.logins[0]
    assert entry["reason"] == "access_denied"
    assert entry["result"] is AuditResult.FAILURE
    # 自由文本不进审计（可能是甲方回显的参数），只在日志里留净化后的摘要。
    assert "error_text" not in entry
    sanitized = [rec.getMessage() for rec in caplog.records if "error=" in rec.getMessage()]
    assert sanitized, "失败路径必须留一条带 error= 的日志"
    for message in sanitized:
        assert "\r" not in message and "\n" not in message
        assert "?" in message  # 控制字符被替换成 ?


@pytest.mark.asyncio
async def test_malformed_callback_has_its_own_internal_reason(
    client: httpx.AsyncClient, sso_settings, audit: _FakeAudit
):
    """既没 ``code`` 也没 ``error``：公开码仍是 denied，但内部原因单列。

    这两种情况在审计里必须分得开——「用户点了拒绝」是正常业务动作，而「回跳被截断/
    被中间设备改写」是链路故障，混成一个 reason 会让告警既不准又没法计数。
    """
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?state=state-1")

    assert response.status_code == 303
    # 公开码不变（前端 9 码词表不允许新增）。
    assert response.headers["location"] == "/login?sso_error=denied"
    assert len(audit.logins) == 1
    assert audit.logins[0]["reason"] == "malformed_callback"


# --------------------------------------------------------------------------- #
# 4. 换票 / 取用户信息（T-05、T-06、T-07、T-11、T-15、C-02）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_token_exchange_failure_is_audited(
    client: httpx.AsyncClient, sso_settings, audit: _FakeAudit
):
    calls: list[str] = []
    _install_iam(_iam_handler(token_code="2002", calls=calls))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=token"
    assert calls == ["getToken"]
    entry = audit.logins[0]
    assert entry["reason"] == "token_exchange_failed"
    assert entry["stage"] == "exchange"
    assert entry["iam_code"] == "2002"
    assert entry["transport"] is False


@pytest.mark.asyncio
async def test_token_exchange_transport_failure_is_audited(
    client: httpx.AsyncClient, sso_settings, audit: _FakeAudit
):
    """IAM 连不上 -> ``unavailable``（前端提示「稍后再试」而不是「登录失败」）。"""
    _install_iam(_iam_handler(transport_fail={"getToken"}))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=unavailable"
    entry = audit.logins[0]
    assert entry["reason"] == "token_exchange_unavailable"
    assert entry["iam_code"] is None  # 传输层失败没有 IAM 返回码
    assert entry["transport"] is True


@pytest.mark.asyncio
async def test_userinfo_failure_is_audited(
    client: httpx.AsyncClient, sso_settings, audit: _FakeAudit
):
    calls: list[str] = []
    _install_iam(_iam_handler(user_info_code="2002", calls=calls))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=userinfo"
    assert calls == ["getToken", "getUserInfo"]
    entry = audit.logins[0]
    assert entry["reason"] == "userinfo_failed"
    assert entry["stage"] == "userinfo"
    assert entry["iam_code"] == "2002"


@pytest.mark.asyncio
async def test_unexpected_token_exchange_exception_is_contained(
    client: httpx.AsyncClient, sso_settings, audit: _FakeAudit, monkeypatch
):
    """C-02（换票分支）：``exchange_code`` 抛非 ``IamError`` 时同样 303，不许 500。"""

    async def boom(self, code):  # noqa: ANN001 - 替身，签名与真实方法一致
        raise KeyError("malformed")

    monkeypatch.setattr(IamClient, "exchange_code", boom)
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?sso_error=unavailable"
    entry = audit.logins[0]
    assert entry["reason"] == "token_exchange_unexpected"
    assert entry["stage"] == "exchange"
    assert entry["error_type"] == "KeyError"


@pytest.mark.asyncio
async def test_unexpected_exception_log_does_not_echo_payload(
    client: httpx.AsyncClient, sso_settings, audit: _FakeAudit, monkeypatch, caplog
):
    """C-02 的日志只留「类型名 + 首行摘要」：``str(exc)`` 会把 token 原文写进日志。

    这里照抄 pydantic ``ValidationError`` 的真实文本形状——凭据落在第二行
    ``input_value='...'`` 里。只取首行就足以把它挡在日志之外，同时保留「哪个类型炸了」。
    """
    secret = "iam-access-SECRET-0123456789"

    async def boom(self, code):  # noqa: ANN001 - 替身，签名与真实方法一致
        raise ValueError(
            "1 validation error for TokenResponse\n"
            "access_token\n"
            f"  Input should be a valid string [input_value='{secret}']"
        )

    monkeypatch.setattr(IamClient, "exchange_code", boom)
    _install_iam(_iam_handler())
    _prime_state(client)

    with caplog.at_level(logging.WARNING, logger="app.api.v1.auth_sso"):
        response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    messages = [rec.getMessage() for rec in caplog.records if "error=" in rec.getMessage()]
    assert messages, "失败路径必须留一条带 error= 的日志"
    joined = " ".join(messages)
    assert secret not in joined
    # 逐字断言 error= 的取值：只截断是不够的（真实令牌往往长到能整段落在 120 字窗口里），
    # 必须是「类型名 + 首行」这个形状，第二行起的内容一个字都不许进来。
    line = next(message for message in messages if " error=" in message)
    error_value = line.split(" error=", 1)[1].split(" client_ip=", 1)[0]
    assert error_value == "ValueError: 1 validation error for TokenResponse"


@pytest.mark.asyncio
async def test_unexpected_userinfo_exception_is_contained(
    client: httpx.AsyncClient, sso_settings, audit: _FakeAudit, monkeypatch
):
    """C-02：客户端抛非 ``IamError`` 异常时必须 303 收口，而不是 500 白屏。"""

    async def boom(self, access_token):  # noqa: ANN001 - 替身，签名与真实方法一致
        raise ValueError("boom")

    monkeypatch.setattr(IamClient, "get_user_info", boom)
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?sso_error=unavailable"
    entry = audit.logins[0]
    assert entry["reason"] == "userinfo_unexpected"
    assert entry["error_type"] == "ValueError"


@pytest.mark.asyncio
async def test_audit_never_carries_secret_material(
    client: httpx.AsyncClient, sso_settings, audit: _FakeAudit
):
    """审计里不得出现授权码 / state / 令牌原文；URL 里只能有 ``sso_error``。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getToken"):
            return httpx.Response(
                200,
                json={
                    "code": "9001",
                    "message": "ok",
                    "data": {
                        "accessToken": "access-SECRET",
                        "refreshToken": "iam-refresh-SECRET",
                        "expiresIn": 3600,
                    },
                },
            )
        # 故意让甲方把回显塞进 message：旧实现会把 str(exc) 写进审计。
        return httpx.Response(
            200,
            json={
                "code": "2002",
                "message": "bad SECRET-CODE / state-1 / access-SECRET / iam-refresh-SECRET",
            },
        )

    _install_iam(handler)
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=SECRET-CODE&state=state-1")

    assert response.headers["location"] == "/login?sso_error=userinfo"
    assert response.headers["location"].count("=") == 1  # 只有一个 query 参数
    blob = json.dumps(audit.logins, default=str)
    for marker in ("SECRET-CODE", "state-1", "access-", "iam-refresh"):
        assert marker not in blob, marker


# --------------------------------------------------------------------------- #
# 5. 认人 / 开户失败（T-12、T-13、T-14）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_local_takeover_is_audited_once_with_snapshots(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit: _FakeAudit
):
    """同名本地账号拒绝接管：**只记一条**审计（旧实现在 _resolve_user 里另记一条）。"""
    local = await _add_user(db_session, username=IAM_USERNAME)
    local_id = local.id
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=conflict"
    assert len(audit.logins) == 1
    entry = audit.logins[0]
    assert entry["reason"] == "account_conflict"
    assert entry["branch"] == "local_takeover"
    assert entry["user_id"] == str(local_id)
    assert entry["username"] == IAM_USERNAME
    # 本地账号不得被自动绑定 uid。
    assert (await _snapshot(db_session, local_id))["sso_uid"] is None
    assert await _count(db_session, User) == 1


@pytest.mark.asyncio
async def test_local_takeover_beats_inactive_status(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit: _FakeAudit
):
    """停用的**本地**同名账号仍报 conflict：不向未认证访客暴露「该账号存在且停用」。"""
    await _add_user(db_session, username=IAM_USERNAME, status=UserStatus.DISABLED.value)
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=conflict"
    assert audit.logins[0]["reason"] == "account_conflict"
    assert audit.logins[0]["branch"] == "local_takeover"


@pytest.mark.asyncio
async def test_uid_mismatch_reports_conflict_with_sso_uid(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit: _FakeAudit
):
    """同名但 uid 已被别的甲方账号占用：拒绝，并在审计里留下两边 uid 线索。"""
    await _add_user(
        db_session,
        username=IAM_USERNAME,
        auth_source=AuthSource.SSO.value,
        sso_uid="iam-other",
    )
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=conflict"
    entry = audit.logins[0]
    assert entry["reason"] == "account_conflict"
    assert entry["branch"] == "uid_mismatch"
    assert entry["sso_uid"] == IAM_UID


@pytest.mark.asyncio
async def test_audit_sso_uid_is_sanitized(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit: _FakeAudit
):
    """A-07：审计里的 ``sso_uid`` 同属外部输入，换行必须在入库前被替换掉。"""
    await _add_user(
        db_session,
        username=IAM_USERNAME,
        auth_source=AuthSource.SSO.value,
        sso_uid="iam-other",
    )
    _install_iam(_iam_handler(user_info={"userId": "iam-0001\r\nforged"}))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=conflict"
    entry = audit.logins[0]
    assert entry["branch"] == "uid_mismatch"
    assert "\r" not in entry["sso_uid"] and "\n" not in entry["sso_uid"]
    assert entry["sso_uid"].startswith("iam-0001?")


@pytest.mark.asyncio
async def test_not_provisioned_leaves_no_user_row(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit: _FakeAudit,
    monkeypatch,
):
    monkeypatch.setattr(settings, "SSO_AUTO_PROVISION", False)
    _install_iam(_iam_handler())
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=not_provisioned"
    entry = audit.logins[0]
    assert entry["reason"] == "not_provisioned"
    assert entry["branch"] == "auto_provision_off"
    assert await _count(db_session, User) == 0
    assert await _count(db_session, RefreshToken) == 0


# --------------------------------------------------------------------------- #
# 6. A-02：停用账号一个字节都不许写（T-08、T-09）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_disabled_sso_account_is_not_written_back(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit: _FakeAudit
):
    """按 sso_uid 命中的停用账号：登录一次后四列全未变，也没有新行。"""
    user = await _add_user(
        db_session,
        username=IAM_USERNAME,
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
        status=UserStatus.DISABLED.value,
    )
    user_id = user.id
    user.display_name = "旧显示名"
    user.email = "old@example.com"
    user.last_login_at = utcnow() - timedelta(days=3)
    await db_session.commit()
    before = await _snapshot(db_session, user_id)

    _install_iam(_iam_handler())
    _prime_state(client)
    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=inactive"
    entry = audit.logins[0]
    assert entry["reason"] == "account_inactive"
    assert entry["branch"] == "inactive_status"
    assert await _snapshot(db_session, user_id) == before
    assert await _count(db_session, User) == 1
    assert await _count(db_session, RefreshToken) == 0


@pytest.mark.asyncio
async def test_disabled_sso_account_with_empty_profile_is_not_filled(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit: _FakeAudit
):
    """A-02 的敏感点：资料为空时，只要状态判定晚于写入，``_apply_profile`` 就会补全。

    上一条用例把 display_name/email 预填成非空，而 ``_apply_profile`` 本来只填空缺，
    于是「四列未变」在回退修复后仍然成立——那是假绿。这里把两列留空：状态判定一旦
    挪回写入之后（且没有 rollback），本用例必红。
    """
    user = await _add_user(
        db_session,
        username=IAM_USERNAME,
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
        status=UserStatus.DISABLED.value,
    )
    user_id = user.id
    user.display_name = None
    user.email = None
    user.last_login_at = utcnow() - timedelta(days=3)
    await db_session.commit()
    before = await _snapshot(db_session, user_id)
    assert before["display_name"] is None and before["email"] is None

    _install_iam(_iam_handler())
    _prime_state(client)
    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=inactive"
    after = await _snapshot(db_session, user_id)
    assert after == before
    assert after["sso_uid"] == IAM_UID  # 本来就是它，重点是下面两列没被补全
    assert after["display_name"] is None
    assert after["email"] is None
    assert await _count(db_session, User) == 1
    assert await _count(db_session, RefreshToken) == 0


@pytest.mark.asyncio
async def test_preseeded_disabled_account_keeps_uid_empty(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit: _FakeAudit
):
    """按用户名命中的管理员预建停用账号：sso_uid 不得被回填（A-02 的脏写点）。"""
    user = await _add_user(
        db_session,
        username=IAM_USERNAME,
        auth_source=AuthSource.SSO.value,
        sso_uid=None,
        status=UserStatus.DISABLED.value,
    )
    user_id = user.id
    user.display_name = "预建账号"
    user.email = "preseed@example.com"
    await db_session.commit()
    before = await _snapshot(db_session, user_id)
    assert before["sso_uid"] is None

    _install_iam(_iam_handler())
    _prime_state(client)
    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/login?sso_error=inactive"
    after = await _snapshot(db_session, user_id)
    assert after == before  # 含 sso_uid 仍为 None
    assert await _count(db_session, RefreshToken) == 0


def test_status_check_precedes_writes():
    """A-02 的源码级守卫：``_ensure_active`` 必须出现在任何写库语句之前。"""
    source = inspect.getsource(sso_module._resolve_user)
    assert source.index("_ensure_active(existing)") < source.index("existing.sso_uid =")
    assert source.index("_ensure_active(user)") < source.index("_apply_profile(user, iam_user)")


# --------------------------------------------------------------------------- #
# 7. A-03：落库失败（T-10）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_session_persist_failure_rolls_back_and_clears_state(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit: _FakeAudit,
    monkeypatch, caplog,
):
    """落库抖动：303 unavailable + 回滚事务 + 清 state Cookie + 不留半截账号。"""
    monkeypatch.setattr(
        sso_module, "store_refresh_token", AsyncMock(side_effect=RuntimeError("db down"))
    )
    _install_iam(_iam_handler())
    _prime_state(client)

    with caplog.at_level(logging.WARNING, logger="app.api.v1.auth_sso"):
        response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?sso_error=unavailable"
    entry = audit.logins[0]
    assert entry["reason"] == "session_persist_failed"
    assert entry["stage"] == "session"
    assert entry["error_type"] == "RuntimeError"
    assert entry["username"] == IAM_USERNAME  # 快照可用：rollback 后 ORM 已不可读
    # 异常原文（可能含 SQL / 连接串）只进日志摘要，不进审计。
    assert "error_text" not in entry
    assert "error=db down" in caplog.text
    # 不能下发新的认证 Cookie（否则前端会以为登录成功）。
    assert "cpumodel_access" not in _set_cookie_headers(response)
    assert any(_is_expired_cookie(header) for header in _state_cookie_headers(response))
    # 半截账号必须被回滚掉：get_db 在 yield 之后会无条件 commit。
    assert await _count(db_session, User) == 0
    assert await _count(db_session, RefreshToken) == 0


# --------------------------------------------------------------------------- #
# 8. A-07：自动开户日志净化（T-23）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_auto_provision_log_is_sanitized(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, caplog
):
    """``sso_uid`` 来自甲方响应，带换行时能伪造整行日志，必须先净化。"""
    _install_iam(_iam_handler(user_info={"userId": "iam-0001\r\nforged"}))
    _prime_state(client)

    with caplog.at_level(logging.INFO, logger="app.api.v1.auth_sso"):
        response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.headers["location"] == "/workspace"
    lines = [rec.getMessage() for rec in caplog.records if "自动开户" in rec.getMessage()]
    assert lines, "自动开户必须留一条日志"
    for line in lines:
        assert "sso_uid=" in line
        assert "\r" not in line and "\n" not in line
        assert "?" in line  # 控制字符被替换


# --------------------------------------------------------------------------- #
# 9. A-04 / A-05：登出（T-17、T-18、T-19）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_logout_without_cookies_sends_no_cookie_headers(
    client: httpx.AsyncClient, sso_settings
):
    """三枚 Cookie 全无：200 直接返回，**不发清 Cookie 头**（否则跨站可强制登出）。"""
    response = await client.post("/api/v1/auth/sso/logout")

    assert response.status_code == 200
    assert response.json()["data"]["logout_url"] is None
    assert response.headers.get_list("set-cookie") == []


@pytest.mark.asyncio
async def test_logout_with_auth_cookies_but_no_csrf_cookie_is_rejected(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    """A-05：缺 ``cpumodel_csrf`` 但另两枚在 -> 403 + 40002，不清 Cookie、不吊销。"""
    await _login_via_sso(client)
    access = client.cookies.get("cpumodel_access")
    refresh = client.cookies.get("cpumodel_refresh")
    jti = str((jwt_handler.decode_token(refresh) or {})["jti"])

    # 只保留 access/refresh：模拟「csrf Cookie 被清掉但会话还在」。
    client.cookies.clear()
    client.cookies.set("cpumodel_access", access, path="/")
    client.cookies.set("cpumodel_refresh", refresh, path="/api/v1/auth")

    response = await client.post("/api/v1/auth/sso/logout")

    assert response.status_code == 403
    assert response.json()["code"] == 40002
    # 清 Cookie 本身就是攻击目的：失败响应里一个 Set-Cookie 都不许有。
    assert response.headers.get_list("set-cookie") == []
    row = await get_refresh_token(db_session, jti)
    assert row is not None and row.revoked_at is None


@pytest.mark.asyncio
async def test_logout_csrf_mismatch_keeps_session(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings
):
    """A-04：CSRF 校验失败 -> 403 + 40002，不清 Cookie、不吊销、不拼 GLO 地址。"""
    await _login_via_sso(client)
    jti = str(
        (jwt_handler.decode_token(client.cookies.get("cpumodel_refresh")) or {})["jti"]
    )

    response = await client.post(
        "/api/v1/auth/sso/logout", headers={"X-CSRF-Token": "wrong-value"}
    )

    assert response.status_code == 403
    assert response.json()["code"] == 40002
    assert response.headers.get_list("set-cookie") == []
    row = await get_refresh_token(db_session, jti)
    assert row is not None and row.revoked_at is None


# --------------------------------------------------------------------------- #
# 9b. 登出清理失败（S-02 的反面）：必须 200 + 清 Cookie + 拼出 GLO 地址
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def per_request_client(db_session: AsyncSession):
    """与生产同构：**每个请求一个 session**（``database/session.py:77-87``）。

    为什么这条用例不能用共享 ``client``：共享夹具全程只有一个 session，rollback 之后
    ``db.get`` 命中 identity map，ORM 对象未必真过期，缺了这一环就复现不出
    ``MissingGreenlet``——测试会「绿灯通过」，而生产照样 500。
    """

    session_factory = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            await session.commit()

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_logout_cleanup_failure_still_clears_cookies(
    per_request_client: httpx.AsyncClient,
    db_session: AsyncSession,
    sso_settings,
    audit: _FakeAudit,
    monkeypatch,
):
    """清理失败（吊销/commit 抛错）也必须 200 + 清三枚 Cookie + 拼出 GLO 地址。

    这是 S-02 的反面：清理链路炸了以后，``rollback`` 会把整个 identity map 里对象置为
    过期，此后**任何** ORM 属性读取都会触发同步懒加载 -> ``MissingGreenlet`` -> 500。
    而 500 响应既不带清 Cookie 头、也拼不出甲方登出地址，用户就彻底退不出去了。
    """
    user = await _add_user(
        db_session,
        username="sso-logout-broken",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
    )
    user_id = str(user.id)
    token = await _seed_sso_session(db_session, user)
    _install_iam(_iam_handler())

    async def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(sso_module, "revoke_refresh_token", _boom)
    csrf = "csrf-token-for-logout"

    response = await per_request_client.post(
        "/api/v1/auth/sso/logout",
        cookies={
            "cpumodel_access": "stale-access",
            "cpumodel_refresh": token,
            "cpumodel_csrf": csrf,
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    logout_url = response.json()["data"]["logout_url"]
    # 语义：仍然要跳甲方 GLO（redirectToLogin=false），而不是降级成不登出甲方。
    assert logout_url and "GLO" in logout_url and "redirectToLogin=false" in logout_url
    assert "redirctToUrl=" in logout_url  # 甲方参数名就是这么拼的，照抄不改
    # 三枚 Cookie 必须都下发删除头，否则浏览器里留着死会话。
    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert name in headers and _is_expired_cookie(headers[name])
    # 审计用快照，不需要 ORM 对象（这一步在读 ``user.id`` 的旧实现里会 500）。
    assert audit.logouts and audit.logouts[0]["user_id"] == user_id


# --------------------------------------------------------------------------- #
# 10. S-02：续期落库落空（T-24、T-25）
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_refresh_rejects_when_alive_persist_missed(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    iam_refresh_settings,
    audit: _FakeAudit,
    monkeypatch,
    caplog,
):
    """IAM 说票据有效，但落库落空（行已吊销）：401 + 40103 + reason + 清 Cookie。"""
    user = await _add_user(
        db_session, username="sso-alive", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(db_session, user)
    _install_iam(_iam_handler())
    monkeypatch.setattr(
        auth_module, "touch_iam_checked_at", AsyncMock(return_value=False)
    )

    with caplog.at_level(logging.WARNING, logger="app.api.v1.auth"):
        response = await client.post(
            "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
        )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == 40103
    assert body["detail"]["reason"] == "session_revoked"
    # 401 + /auth/refresh 会触发 main.py 的清 Cookie：三枚都要删，不能留死会话。
    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert name in headers and _is_expired_cookie(headers[name])
    assert "refresh_persist_missed" in caplog.text
    assert "phase=alive" in caplog.text


@pytest.mark.asyncio
async def test_refresh_rejects_when_refreshed_persist_missed(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    iam_refresh_settings,
    audit: _FakeAudit,
    monkeypatch,
    caplog,
):
    """IAM 续期成功但票据写回落空：同样 401 + 40103，不下发新 Cookie。"""
    user = await _add_user(
        db_session, username="sso-expired", auth_source=AuthSource.SSO.value, sso_uid=IAM_UID
    )
    token = await _seed_sso_session(
        db_session, user, access_expires_at=utcnow() - timedelta(minutes=5)
    )
    _install_iam(_iam_handler())
    monkeypatch.setattr(auth_module, "update_iam_tickets", AsyncMock(return_value=False))

    with caplog.at_level(logging.WARNING, logger="app.api.v1.auth"):
        response = await client.post(
            "/api/v1/auth/refresh", cookies={"cpumodel_refresh": token}
        )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == 40103
    assert body["detail"]["reason"] == "session_revoked"
    headers = _set_cookie_headers(response)
    for name in AUTH_COOKIE_NAMES:
        assert name in headers and _is_expired_cookie(headers[name])
    assert "phase=refreshed" in caplog.text
