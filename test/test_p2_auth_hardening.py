# test/test_p2_auth_hardening.py
"""P2 认证与授权加固回归测试。

覆盖 docs/archive/22 P2 的五条：
1. 口令策略：最小 12 位 + bcrypt 72 字节上限（超限是 422 业务校验，不是 500）；
2. refresh jti 存储 / 轮换 / 复用检测；
3. 登录账户级锁定（阈值 / 清零 / Redis 不可用 fail-closed）；
4. token 走 query 清理（SSE 不再接受 ``?token=``）；
5. GPU 只读端点至少要求登录，汇总端点要求管理员。
"""

from __future__ import annotations

import inspect
import sys
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models as _models  # noqa: F401,E402  注册全部表
from app.pwdpolicy import (  # noqa: E402
    MAX_BCRYPT_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    validate_password_policy,
)
from app.auth.password import hash_password  # noqa: E402
from app.auth.dependencies import get_admin_user, get_current_user  # noqa: E402
from app.auth.jwt_handler import jwt_handler  # noqa: E402
from app.cache.memory import MemoryCacheBackend  # noqa: E402
from app.common.exceptions import BusinessException  # noqa: E402
from app.common.time import utcnow  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services import login_throttle  # noqa: E402
from app.services import refresh_token_store as token_store  # noqa: E402
from app.api.v1 import gpu  # noqa: E402
from app.api.v1.users import AdminUserCreate, PasswordChange  # noqa: E402
from app.schemas.users import UserCreate  # noqa: E402

USERNAME = "p2user"
PASSWORD = "Str0ngPassword!2026"
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
        email="p2@example.com",
        password_hash=hash_password(PASSWORD),
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
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client
    app.dependency_overrides.clear()


async def _login(client: httpx.AsyncClient, password: str = PASSWORD) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login",
        json={"username": USERNAME, "password": password},
    )


# ---------------------------------------------------------------------------
# 1. 口令策略
# ---------------------------------------------------------------------------

def test_password_policy_min_length():
    assert MIN_PASSWORD_LENGTH == 12
    with pytest.raises(ValueError):
        validate_password_policy("a" * 11)
    assert validate_password_policy("a" * 12) == "a" * 12


def test_password_policy_bcrypt_72_byte_limit():
    assert MAX_BCRYPT_PASSWORD_BYTES == 72
    # ASCII 72 字节可接受，73 字节拒绝。
    assert validate_password_policy("a" * 72) == "a" * 72
    with pytest.raises(ValueError):
        validate_password_policy("a" * 73)
    # 多字节：24 个汉字 = 72 字节可接受，25 个 = 75 字节拒绝。
    assert validate_password_policy("密" * 24) == "密" * 24
    with pytest.raises(ValueError):
        validate_password_policy("密" * 25)
    # hash 阶段也拒绝而不是静默截断。
    with pytest.raises(ValueError):
        hash_password("密" * 25)


def test_user_create_schema_enforces_policy():
    base = {"email": "new@example.com", "verification_code": "123456"}
    with pytest.raises(ValidationError):
        UserCreate(**base, password="a" * 11)
    ok = UserCreate(**base, password="a" * 12)
    assert ok.password == "a" * 12
    with pytest.raises(ValidationError):
        UserCreate(**base, password="a" * 73)


def test_password_change_schemas_enforce_policy():
    with pytest.raises(ValidationError):
        PasswordChange(old_password="x", new_password="a" * 11)
    with pytest.raises(ValidationError):
        PasswordChange(old_password="x", new_password="a" * 73)
    assert PasswordChange(
        old_password="x", new_password="a" * 12
    ).new_password == "a" * 12
    # 用户管理后台建号同样受约束（>72 字节应 422，而非 hash 阶段 500）。
    with pytest.raises(ValidationError):
        AdminUserCreate(username="newuser", password="a" * 73)


@pytest.mark.asyncio
async def test_login_with_overlong_password_returns_401_not_500(api_client: httpx.AsyncClient):
    response = await _login(api_client, password="密" * 40)
    assert response.status_code == 401, response.text
    assert response.json()["code"] == 40101


# ---------------------------------------------------------------------------
# 2. refresh jti 存储 / 轮换 / 复用检测
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_rotation_and_reuse_detection(db_session: AsyncSession, member: User):
    old_token = jwt_handler.create_refresh_token(member.id)
    old_payload = jwt_handler.decode_token(old_token)
    await token_store.store_refresh_token(
        db_session,
        jti=old_payload["jti"],
        user_id=str(member.id),
        expires_at=token_store.expires_at_from_payload(old_payload),
    )
    await db_session.commit()

    new_token = jwt_handler.create_refresh_token(member.id)
    new_payload = jwt_handler.decode_token(new_token)
    result = await token_store.rotate_refresh_token(
        db_session,
        old_jti=old_payload["jti"],
        user_id=str(member.id),
        new_jti=new_payload["jti"],
        new_expires_at=token_store.expires_at_from_payload(new_payload),
    )
    assert result == token_store.ROTATE_OK
    await db_session.commit()

    old_record = await token_store.get_refresh_token(db_session, old_payload["jti"])
    assert old_record.revoked_at is not None
    assert old_record.replaced_by == new_payload["jti"]

    # 已吊销 jti 再次轮换 -> REUSE。
    reuse = await token_store.rotate_refresh_token(
        db_session,
        old_jti=old_payload["jti"],
        user_id=str(member.id),
        new_jti="jti-should-not-be-used",
        new_expires_at=utcnow() + timedelta(days=1),
    )
    assert reuse == token_store.ROTATE_REUSE


@pytest.mark.asyncio
async def test_revoke_all_for_user(db_session: AsyncSession, member: User):
    for _ in range(2):
        token = jwt_handler.create_refresh_token(member.id)
        payload = jwt_handler.decode_token(token)
        await token_store.store_refresh_token(
            db_session,
            jti=payload["jti"],
            user_id=str(member.id),
            expires_at=token_store.expires_at_from_payload(payload),
        )
    await db_session.commit()

    revoked = await token_store.revoke_all_for_user(db_session, str(member.id))
    await db_session.commit()
    assert revoked == 2


@pytest.mark.asyncio
async def test_refresh_api_reuse_revokes_all_sessions(api_client: httpx.AsyncClient):
    login = await _login(api_client)
    old_refresh = login.json()["data"]["refresh_token"]
    assert old_refresh

    api_client.cookies.clear()
    first = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert first.status_code == 200, first.text
    new_refresh = first.cookies.get(REFRESH_COOKIE)
    assert new_refresh and new_refresh != old_refresh

    # 复用旧 refresh -> 401，并吊销该用户全部 refresh。
    api_client.cookies.clear()
    reuse = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert reuse.status_code == 401, reuse.text

    # 因复用入侵响应，最新 refresh 也已被吊销。
    api_client.cookies.clear()
    after = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_refresh}
    )
    assert after.status_code == 401, after.text


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(api_client: httpx.AsyncClient):
    login = await _login(api_client)
    refresh_token = login.json()["data"]["refresh_token"]
    csrf_token = api_client.cookies.get(CSRF_COOKIE)

    logout = await api_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token}
    )
    assert logout.status_code == 200, logout.text

    api_client.cookies.clear()
    response = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# 3. 登录账户级锁定（阈值 / 清零 / fail-closed）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_throttle_service_threshold_and_reset():
    backend = MemoryCacheBackend()
    for _ in range(login_throttle.MAX_FAILURES - 1):
        await login_throttle.register_failure(USERNAME, "1.1.1.1", backend=backend)
    assert not await login_throttle.is_locked(USERNAME, "1.1.1.1", backend=backend)

    await login_throttle.register_failure(USERNAME, "1.1.1.1", backend=backend)
    assert await login_throttle.is_locked(USERNAME, "1.1.1.1", backend=backend)
    with pytest.raises(BusinessException) as exc:
        await login_throttle.ensure_not_locked(USERNAME, "1.1.1.1", backend=backend)
    assert exc.value.http_status == 429

    await login_throttle.reset(USERNAME, "1.1.1.1", backend=backend)
    assert not await login_throttle.is_locked(USERNAME, "1.1.1.1", backend=backend)


@pytest.mark.asyncio
async def test_login_throttle_fail_closed_when_backend_broken():
    class BrokenBackend:
        async def exists(self, key):  # noqa: ARG002
            raise RuntimeError("redis down")

    with pytest.raises(BusinessException) as exc:
        await login_throttle.ensure_not_locked(
            USERNAME, "1.1.1.1", backend=BrokenBackend()
        )
    assert exc.value.http_status == 503
    assert "暂不可用" in exc.value.message


@pytest.mark.asyncio
async def test_login_api_locks_after_threshold(
    api_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    backend = MemoryCacheBackend()
    monkeypatch.setattr(login_throttle, "_get_backend", lambda: backend)

    for _ in range(login_throttle.MAX_FAILURES):
        bad = await _login(api_client, password="WrongPassword!000")
        assert bad.status_code == 401, bad.text

    blocked = await _login(api_client)
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["code"] == 42901


@pytest.mark.asyncio
async def test_successful_login_clears_failure_counter(
    api_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    backend = MemoryCacheBackend()
    monkeypatch.setattr(login_throttle, "_get_backend", lambda: backend)

    for _ in range(3):
        bad = await _login(api_client, password="WrongPassword!000")
        assert bad.status_code == 401

    ok = await _login(api_client)
    assert ok.status_code == 200, ok.text
    assert not await login_throttle.is_locked(USERNAME, "127.0.0.1", backend=backend)

    # 清零后：再失败 4 次仍未锁定（说明计数确实被重置）。
    for _ in range(4):
        bad = await _login(api_client, password="WrongPassword!000")
        assert bad.status_code == 401
    still_ok = await _login(api_client)
    assert still_ok.status_code == 200, still_ok.text


# ---------------------------------------------------------------------------
# 4. token 走 query 清理（SSE）
# ---------------------------------------------------------------------------

def test_sse_endpoint_has_no_token_query_parameter():
    from app.api.v1.tasks import stream_task_events

    params = inspect.signature(stream_task_events).parameters
    assert "token" not in params


def test_tasks_module_no_longer_imports_query_token_helper():
    import app.api.v1.tasks as tasks_module

    assert not hasattr(tasks_module, "_load_user_from_query_token")


# ---------------------------------------------------------------------------
# 5. GPU 端点鉴权
# ---------------------------------------------------------------------------

def test_gpu_readonly_endpoints_require_login_summary_requires_admin():
    deps = {
        route.path: {dep.call for dep in route.dependant.dependencies}
        for route in gpu.router.routes
    }
    assert get_current_user in deps["/gpu/info"]
    assert get_current_user in deps["/gpu/stats"]
    assert get_current_user in deps["/gpu/stats/{gpu_index}"]
    assert get_current_user in deps["/gpu/health"]
    assert get_admin_user in deps["/gpu/summary"]


@pytest.mark.asyncio
async def test_gpu_info_without_credentials_is_unauthorized():
    async def override_get_db():
        yield None

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/api/v1/gpu/info")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 401, response.text
