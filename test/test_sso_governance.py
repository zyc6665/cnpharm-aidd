# test/test_sso_governance.py
"""身份治理回归：准入白名单（G-01）、sso_uid 绑定（D-06）、用户名口径（D-07）、
``auth_source`` 枚举（D-08）。

为什么单独成文件：``test/test_sso_flow.py`` 与 ``test/test_sso_failure_paths.py`` 是
本次治理的**冻结基线**（用例数字必须逐字不变），治理新增的用例只能另起文件，免得
「改测试让自己变绿」。harness 照抄基线文件的做法：内存 sqlite + ``MockTransport`` 假
IAM + 直接落库预置账号，不 monkeypatch 生产函数。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models as _models  # noqa: F401,E402  注册全部表
from app.api.v1 import auth_sso as sso_module  # noqa: E402
from app.config import Settings, settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.refresh_tokens import RefreshToken  # noqa: E402
from app.models.users import AuthSource, User, UserRole, UserStatus  # noqa: E402
from app.services.iam_client import IamClient, get_iam_client  # noqa: E402

IAM_UID = "iam-0001"
IAM_USERNAME = "zhangsan"
STATE_COOKIE = "cpumodel_sso_state"
STATE_COOKIE_PATH = "/api/v1/auth/sso"
AUTH_COOKIE_NAMES = ("cpumodel_access", "cpumodel_refresh", "cpumodel_csrf")


# --------------------------------------------------------------------- harness
def _iam_settings() -> Settings:
    return Settings(
        ENVIRONMENT="development",
        SSO_ENABLED=True,
        SSO_BASE_URL="https://iam.example",
        SSO_APP_ID="cnpharm-aidd",
        SSO_CLIENT_SECRET="iam-client-secret-value",
        SSO_REDIRECT_URI="https://platform.example/api/v1/auth/sso/callback",
    )


def _iam_handler(*, orgs=None, username: str = IAM_USERNAME):
    """假甲方 IAM：只覆盖本文件用到的 ``getToken`` / ``getUserInfo``。

    ``orgs`` 用参数注入——准入白名单只能从 ``getUserInfo`` 的这段里判定。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/getToken"):
            return httpx.Response(
                200,
                json={
                    "code": "9001",
                    "data": {"accessToken": "iam-access", "expiresIn": 3600},
                },
            )
        if path.endswith("/getUserInfo"):
            return httpx.Response(
                200,
                json={
                    "code": "9001",
                    "userInfo": {
                        "userId": IAM_UID,
                        "userName": username,
                        "fullname": "张三",
                        "email": f"{username}@example.com",
                        "orgs": [] if orgs is None else orgs,
                    },
                },
            )
        raise AssertionError(f"unexpected path {path}")

    return handler


def _install_iam(handler) -> None:
    fake = IamClient(_iam_settings(), transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_iam_client] = lambda: fake


def _signed_state_cookie(state: str = "state-1", target: str = "/workspace") -> str:
    return sso_module._state_cookie_value(state, target)


def _prime_state(
    http: httpx.AsyncClient, state: str = "state-1", target: str = "/workspace"
) -> None:
    """模拟 authorize 已经把**签名后的** state 写进 Cookie。"""
    http.cookies.set(
        STATE_COOKIE, _signed_state_cookie(state, target), path=STATE_COOKIE_PATH
    )


async def _add_user(
    db: AsyncSession,
    *,
    username: str,
    auth_source: str = AuthSource.LOCAL.value,
    status: str = UserStatus.ACTIVE.value,
    sso_uid: str | None = None,
    role: str = UserRole.USER.value,
    display_name: str | None = None,
) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        display_name=display_name or username,
        auth_source=auth_source,
        sso_uid=sso_uid,
        role=role,
        status=status,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _count(db: AsyncSession, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


class _FakeAudit:
    """只收 ``log_login``：治理用例关心的是「失败原因进了审计」这件事本身。"""

    def __init__(self) -> None:
        self.logins: list[dict] = []

    def log_login(self, **kwargs) -> None:
        self.logins.append(kwargs)


@pytest.fixture
def audit(monkeypatch):
    fake = _FakeAudit()
    monkeypatch.setattr(sso_module, "get_audit_logger", lambda: fake)
    return fake


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


@pytest.fixture
def sso_settings(monkeypatch):
    """打开 SSO 并固定策略项（不动真实配置文件）。"""
    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    monkeypatch.setattr(settings, "SSO_SUCCESS_PATH", "/workspace")
    monkeypatch.setattr(settings, "SSO_USERNAME_CLAIM", "userName")
    monkeypatch.setattr(settings, "SSO_AUTO_PROVISION", True)
    monkeypatch.setattr(settings, "SSO_ALLOWED_UNIT_CODES", [])
    return settings


# --------------------------------------------------------------- G-01 准入闸
@pytest.mark.asyncio
async def test_empty_whitelist_allows_any_unit(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit
):
    """空白名单 = 不限制（默认，保持既有部署行为）。

    ``orgs`` 里连 unitCode 都没有也必须放行：白名单为空时不该对 IAM 响应提新要求。
    """
    _install_iam(_iam_handler(orgs=[{"deptName": "信息中心"}]))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/workspace"
    assert await _count(db_session, User) == 1
    user = (await db_session.execute(select(User))).scalar_one()
    assert user.sso_uid == IAM_UID


@pytest.mark.asyncio
async def test_callback_rejects_unit_outside_whitelist_new_user(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit, monkeypatch
):
    """白名单非空且不命中：**拒绝开户**，且一行都不落库。"""
    monkeypatch.setattr(sso_settings, "SSO_ALLOWED_UNIT_CODES", ["U2"])
    _install_iam(_iam_handler(orgs=[{"unitCode": "U1"}]))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert "sso_error=conflict" in response.headers["location"]
    assert await _count(db_session, User) == 0
    failure = audit.logins[-1]
    assert failure["reason"] == "unit_not_allowed"
    assert failure["branch"] == "unit_not_allowed"
    assert failure["sso_uid"] == IAM_UID
    assert failure["stage"] == "provision"


@pytest.mark.asyncio
async def test_callback_rejects_unit_outside_whitelist_existing_user(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit, monkeypatch
):
    """**本单存在的理由**：白名单对已开户账号同样生效，否则存量就是后门。

    拒绝时零写入：``last_login_at``/``display_name`` 不变，也不签平台会话。
    """
    await _add_user(
        db_session,
        username="bound-user",
        auth_source=AuthSource.SSO.value,
        sso_uid=IAM_UID,
        display_name="已开户",
    )
    monkeypatch.setattr(sso_settings, "SSO_ALLOWED_UNIT_CODES", ["U2"])
    _install_iam(_iam_handler(orgs=[{"unitCode": "U1"}]))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert "sso_error=conflict" in response.headers["location"]
    assert await _count(db_session, RefreshToken) == 0
    user = (await db_session.execute(select(User))).scalar_one()
    assert user.last_login_at is None
    assert user.display_name == "已开户"
    assert audit.logins[-1]["reason"] == "unit_not_allowed"


@pytest.mark.asyncio
async def test_callback_rejects_preseeded_user_outside_whitelist(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit, monkeypatch
):
    """预建账号（sso_uid 为空）也必须过闸：首次登录的回填路径同样是准入点。

    这条与上面「已绑定账号」分开钉：预建分支会写 ``sso_uid``/资料，闸门若只放在
    「回填之后」就会留下一次成功写入——登录失败却改了库，正是 A-02 修过的坑。
    """
    await _add_user(
        db_session,
        username=IAM_USERNAME,
        auth_source=AuthSource.SSO.value,
        sso_uid=None,
        display_name="预建账号",
    )
    monkeypatch.setattr(sso_settings, "SSO_ALLOWED_UNIT_CODES", ["U2"])
    _install_iam(_iam_handler(orgs=[{"unitCode": "U1"}]))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert "sso_error=conflict" in response.headers["location"]
    user = (await db_session.execute(select(User))).scalar_one()
    assert user.sso_uid is None
    assert user.last_login_at is None
    assert await _count(db_session, RefreshToken) == 0
    assert audit.logins[-1]["reason"] == "unit_not_allowed"
    assert audit.logins[-1]["stage"] == "provision"


@pytest.mark.asyncio
async def test_whitelisted_unit_logs_in_and_backfills(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit, monkeypatch
):
    """命中白名单的预建账号正常登录，并回填 sso_uid（准入闸不能误伤正常路径）。"""
    await _add_user(
        db_session,
        username=IAM_USERNAME,
        auth_source=AuthSource.SSO.value,
        sso_uid=None,
    )
    monkeypatch.setattr(sso_settings, "SSO_ALLOWED_UNIT_CODES", ["U2"])
    _install_iam(_iam_handler(orgs=[{"unitCode": "U2"}]))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/workspace"
    blob = " ".join(response.headers.get_list("set-cookie"))
    for name in AUTH_COOKIE_NAMES:
        assert f"{name}=" in blob
    user = (await db_session.execute(select(User))).scalar_one()
    assert user.sso_uid == IAM_UID
    assert user.last_login_at is not None


@pytest.mark.asyncio
async def test_whitelist_match_is_exact_case_sensitive(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, monkeypatch
):
    """unitCode 是甲方主数据：大小写敏感，不做 lower()/casefold() 宽容匹配。"""
    monkeypatch.setattr(sso_settings, "SSO_ALLOWED_UNIT_CODES", ["u2"])
    _install_iam(_iam_handler(orgs=[{"unitCode": "U2"}]))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert "sso_error=conflict" in response.headers["location"]
    assert await _count(db_session, User) == 0


@pytest.mark.asyncio
async def test_whitelist_matches_any_of_multiple_orgs(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, monkeypatch
):
    """多组织：任一 org 命中即可，不要求「全部命中」。"""
    monkeypatch.setattr(sso_settings, "SSO_ALLOWED_UNIT_CODES", ["U2"])
    _install_iam(_iam_handler(orgs=[{"unitCode": "X"}, {"unitCode": "U2"}]))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/workspace"
    assert await _count(db_session, User) == 1


@pytest.mark.asyncio
async def test_whitelist_ignores_missing_unit_code(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, monkeypatch
):
    """缺字段 / 空对象只能判成「不命中」，不能 KeyError 打成 500。"""
    monkeypatch.setattr(sso_settings, "SSO_ALLOWED_UNIT_CODES", ["U2"])
    _install_iam(_iam_handler(orgs=[{"unitCode": None}, {}]))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert "sso_error=conflict" in response.headers["location"]
    assert await _count(db_session, User) == 0


def test_iam_unit_codes_ignores_non_dict_orgs():
    """``orgs`` 是 ``List[Dict]``，但生产数据脏不得：非 dict 元素整条跳过。"""
    codes = sso_module._iam_unit_codes(
        SimpleNamespace(orgs=["U2", {"unitCode": " U9 "}, {"unitCode": 7}])
    )

    assert codes == {"U9", "7"}


def test_env_example_documents_whitelist_and_provision_default():
    """示例环境文件是运维唯一看得见的"口径文档"：默认值必须写对。"""
    example = PROJECT_ROOT / "backend" / ".env.example"
    contents = example.read_text(encoding="utf-8")

    assert "SSO_ALLOWED_UNIT_CODES=" in contents
    assert "# SSO_AUTO_PROVISION=false" in contents
    assert "SSO_AUTO_PROVISION=true" not in contents
    assert "403 + 40301" not in contents

# --------------------------------------------------- D-06 脏数据防线（auth_source）
@pytest.mark.asyncio
async def test_sso_uid_bound_to_local_account_is_rejected(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit
):
    """脏数据防线：local 账号被手工写上 sso_uid 时，SSO 不许认人。

    否则同一个账号既有口令入口又能走 SSO，而且 IAM 全局登出传导不到平台会话。
    不落库、不签会话，只回 conflict。
    """
    await _add_user(
        db_session,
        username="legacy",
        auth_source=AuthSource.LOCAL.value,
        sso_uid=IAM_UID,
    )
    _install_iam(_iam_handler(orgs=[{"unitCode": "U2"}]))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert "sso_error=conflict" in response.headers["location"]
    assert audit.logins[-1]["branch"] == "uid_auth_source_mismatch"
    blob = " ".join(response.headers.get_list("set-cookie"))
    for name in AUTH_COOKIE_NAMES:
        assert f"{name}=" not in blob
    assert await _count(db_session, RefreshToken) == 0


@pytest.mark.asyncio
async def test_sso_uid_mismatch_reports_conflict_before_inactive(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit
):
    """口径钉：脏数据 + 账号已停用 → 仍报 conflict（不是 inactive）。

    顺序即判据：``_find_by_sso_uid`` 的防线在 ``_ensure_active`` 之前触发。
    """
    await _add_user(
        db_session,
        username="legacy",
        auth_source=AuthSource.LOCAL.value,
        sso_uid=IAM_UID,
        status=UserStatus.DISABLED.value,
    )
    _install_iam(_iam_handler(orgs=[{"unitCode": "U2"}]))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert "sso_error=conflict" in response.headers["location"]
    assert audit.logins[-1]["reason"] == "account_conflict"
    assert audit.logins[-1]["branch"] == "uid_auth_source_mismatch"

# ------------------------------------------------- D-07 用户名口径（56 -> 64）
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a" * 64, "a" * 64),
        # 超长按 64 截断，而不是 56：多截 8 个字符会让合法账号名对不上。
        ("c" * 70, "c" * 64),
        # 先截断再剥两端 ._- —— 顺序不能反，否则 64 位的合法名会被削短。
        ("d" * 64 + "._-", "d" * 64),
    ],
)
def test_normalize_username_keeps_up_to_64_chars(raw: str, expected: str):
    """用户名上限与 ``users.username`` 的 ``String(64)`` 同口径。"""
    assert sso_module._normalize_username(raw) == expected


@pytest.mark.asyncio
async def test_64_char_preseeded_username_can_login(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit
):
    """64 字符预建账号能登录：截到 56 会查不到人，再由自动开户建出第二个账号。"""
    long_name = "p" * 64
    await _add_user(
        db_session,
        username=long_name,
        auth_source=AuthSource.SSO.value,
        sso_uid=None,
    )
    _install_iam(_iam_handler(username=long_name))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/workspace"
    assert await _count(db_session, User) == 1
    user = (await db_session.execute(select(User))).scalar_one()
    assert user.sso_uid == IAM_UID


@pytest.mark.asyncio
async def test_iam_username_longer_than_64_is_clipped(
    client: httpx.AsyncClient, db_session: AsyncSession, sso_settings, audit
):
    """IAM 给的超长账号名截到 64 位落库：既不能超列宽，也不能只留 56 位。"""
    _install_iam(_iam_handler(username="c" * 70))
    _prime_state(client)

    response = await client.get("/api/v1/auth/sso/callback?code=c1&state=state-1")

    assert response.status_code == 303
    user = (await db_session.execute(select(User))).scalar_one()
    assert user.username == "c" * 64

# --------------------------------------------- D-08 响应模型只认三种认证源
def _user_payload(**overrides):
    """UserResponse 的最小合法负载：改一个字段就能测 schema，不必起库。"""
    payload = {
        "id": "u-1",
        "username": "zhangsan",
        "auth_source": AuthSource.LOCAL.value,
        "email": "zhangsan@example.com",
        "display_name": "张三",
        "avatar_url": None,
        "role": "user",
        "status": "active",
        "daily_task_limit": 50,
        "max_file_size_mb": 100,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_user_response_rejects_unknown_auth_source():
    """响应模型不是「随便什么字符串」：多一个认证源就会炸，而不是漏给前端。"""
    from pydantic import ValidationError

    from app.schemas.users import UserResponse

    with pytest.raises(ValidationError):
        UserResponse.model_validate(_user_payload(auth_source="iam"))


@pytest.mark.parametrize(
    "source",
    [AuthSource.LOCAL.value, AuthSource.LDAP.value, AuthSource.SSO.value],
)
def test_user_response_accepts_known_auth_sources(source: str):
    """三值联合：local / ldap / sso 都必须过（含 SSO 账号）。"""
    from app.schemas.users import UserResponse

    assert UserResponse.model_validate(_user_payload(auth_source=source)).auth_source == source
