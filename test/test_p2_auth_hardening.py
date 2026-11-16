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

import asyncio
import hashlib
import inspect
import logging
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DatabaseError, OperationalError
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
from app.models.refresh_tokens import RefreshToken  # noqa: E402
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

    # 同一旧 jti 在竞态窗口内再次轮换 -> RACED：它是「同一用户另一个标签页」
    # 的并发落败方，不是盗用，调用方应回 409 让前端重试。
    raced = await token_store.rotate_refresh_token(
        db_session,
        old_jti=old_payload["jti"],
        user_id=str(member.id),
        new_jti="jti-should-not-be-used",
        new_expires_at=utcnow() + timedelta(days=1),
    )
    assert raced == token_store.ROTATE_RACED
    assert token_store.ROTATE_RACED == "raced"
    assert token_store.ROTATE_RACE_WINDOW_SECONDS == 10

    # 落败方零副作用：没有新行，旧行的 replaced_by/revoked_at 仍是第一次轮换的结果。
    assert await db_session.get(RefreshToken, "jti-should-not-be-used") is None
    old_record = await db_session.get(
        RefreshToken, old_payload["jti"], populate_existing=True
    )
    assert old_record.replaced_by == new_payload["jti"]
    assert (utcnow() - old_record.revoked_at).total_seconds() <= 10
    active = set(
        (
            await db_session.execute(
                select(RefreshToken.jti).where(RefreshToken.revoked_at.is_(None))
            )
        ).scalars()
    )
    assert active == {new_payload["jti"]}


@pytest.mark.asyncio
async def test_rotate_twice_within_race_window_returns_raced(
    db_session: AsyncSession, member: User
):
    """同一旧票在竞态窗口内被轮换两次：第二次是 RACED，且对库零副作用。

    内存 sqlite（StaticPool 只有一条连接）不能真并发；顺序调用之后的库状态与
    「赢家已提交、输家刚到」完全一致，所以这里是确定性构造，不依赖 gather。
    """
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
    ok = await token_store.rotate_refresh_token(
        db_session,
        old_jti=old_payload["jti"],
        user_id=str(member.id),
        new_jti=new_payload["jti"],
        new_expires_at=token_store.expires_at_from_payload(new_payload),
    )
    assert ok == token_store.ROTATE_OK
    await db_session.commit()

    before = (
        await db_session.get(
            RefreshToken, old_payload["jti"], populate_existing=True
        )
    ).revoked_at
    assert before is not None

    raced = await token_store.rotate_refresh_token(
        db_session,
        old_jti=old_payload["jti"],
        user_id=str(member.id),
        new_jti="jti-loser",
        new_expires_at=utcnow() + timedelta(days=1),
    )
    assert raced == token_store.ROTATE_RACED

    after = await db_session.get(
        RefreshToken, old_payload["jti"], populate_existing=True
    )
    # 落败方零副作用：revoked_at 逐字节相等，replaced_by 仍是赢家。
    assert after.revoked_at == before
    assert after.replaced_by == new_payload["jti"]
    assert (utcnow() - after.revoked_at).total_seconds() <= 10
    assert await db_session.get(RefreshToken, "jti-loser") is None


@pytest.mark.asyncio
async def test_reuse_after_race_window_revokes_all_sessions(
    db_session: AsyncSession, member: User
):
    """窗口外被替换的旧票是真复用：仍按 REUSE 处理，并吊销该用户全部会话。

    内存 sqlite（StaticPool 单连接）不能真并发，这里把 ``revoked_at`` 直接推到
    窗口外（-11s）构造「赢家早已提交、旧票隔了一会儿才被拿来用」的确定性状态。
    """
    old_token = jwt_handler.create_refresh_token(member.id)
    old_payload = jwt_handler.decode_token(old_token)
    await token_store.store_refresh_token(
        db_session,
        jti=old_payload["jti"],
        user_id=str(member.id),
        expires_at=token_store.expires_at_from_payload(old_payload),
    )
    # 另一台设备上的活跃会话，用来验证「全端吊销」确实发生。
    other_token = jwt_handler.create_refresh_token(member.id)
    other_payload = jwt_handler.decode_token(other_token)
    await token_store.store_refresh_token(
        db_session,
        jti=other_payload["jti"],
        user_id=str(member.id),
        expires_at=token_store.expires_at_from_payload(other_payload),
    )
    await db_session.commit()

    new_token = jwt_handler.create_refresh_token(member.id)
    new_payload = jwt_handler.decode_token(new_token)
    ok = await token_store.rotate_refresh_token(
        db_session,
        old_jti=old_payload["jti"],
        user_id=str(member.id),
        new_jti=new_payload["jti"],
        new_expires_at=token_store.expires_at_from_payload(new_payload),
    )
    assert ok == token_store.ROTATE_OK
    await db_session.commit()

    reused_row = await db_session.get(
        RefreshToken, old_payload["jti"], populate_existing=True
    )
    reused_row.revoked_at = utcnow() - timedelta(seconds=11)
    await db_session.commit()

    reuse = await token_store.rotate_refresh_token(
        db_session,
        old_jti=old_payload["jti"],
        user_id=str(member.id),
        new_jti="jti-should-not-be-used",
        new_expires_at=utcnow() + timedelta(days=1),
    )
    assert reuse == token_store.ROTATE_REUSE
    assert reuse != token_store.ROTATE_RACED

    revoked = await token_store.revoke_all_for_user(db_session, str(member.id))
    await db_session.commit()
    assert revoked == 2  # 第一次轮换出的新行 + 另一台设备的行
    active = set(
        (
            await db_session.execute(
                select(RefreshToken.jti).where(RefreshToken.revoked_at.is_(None))
            )
        ).scalars()
    )
    assert active == set()


@pytest.mark.asyncio
async def test_concurrent_rotate_on_file_sqlite_returns_ok_and_raced(tmp_path):
    """真并发最佳努力用例：文件库上两个会话同时轮换同一个旧 jti。

    内存 sqlite（StaticPool 单连接）无法真并发，故退到 ``tmp_path`` 文件库；即便如此
    SQLite 的写锁也可能直接抛 ``database is locked``，此时 skip —— 竞态语义由 T1/T5
    的确定性构造覆盖。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'race.db'}")
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        user_id = "race-user"
        async with session_factory() as setup:
            setup.add(
                User(
                    id=user_id,
                    username="raceuser",
                    email="race@example.com",
                    auth_source="local",
                    role=UserRole.USER.value,
                    status=UserStatus.ACTIVE.value,
                )
            )
            await token_store.store_refresh_token(
                setup,
                jti="race-old",
                user_id=user_id,
                expires_at=utcnow() + timedelta(days=1),
            )
            await setup.commit()

        async def attempt(new_jti: str) -> str:
            async with session_factory() as session:
                # 先抢写锁：抢到的先读先写即赢家，另一个等锁释放后才看到已提交的吊销。
                await session.execute(text("BEGIN IMMEDIATE"))
                result = await token_store.rotate_refresh_token(
                    session,
                    old_jti="race-old",
                    user_id=user_id,
                    new_jti=new_jti,
                    new_expires_at=utcnow() + timedelta(days=1),
                )
                await session.commit()
                return result

        results = await asyncio.gather(
            attempt("race-new-a"), attempt("race-new-b"), return_exceptions=True
        )
        if any(isinstance(r, (OperationalError, DatabaseError)) for r in results):
            pytest.skip(
                "SQLite 文件库无法稳定提供两个并发写事务（database is locked）；"
                "竞态语义由 T1/T3/T5 确定性覆盖"
            )
        assert sorted(results) == [token_store.ROTATE_OK, token_store.ROTATE_RACED]

        winner_jti = (
            "race-new-a" if results[0] == token_store.ROTATE_OK else "race-new-b"
        )
        async with session_factory() as check:
            old_row = await check.get(
                RefreshToken, "race-old", populate_existing=True
            )
            assert old_row.revoked_at is not None
            assert old_row.replaced_by == winner_jti
            new_rows = (
                (
                    await check.execute(
                        select(RefreshToken.jti).where(
                            RefreshToken.revoked_at.is_(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert list(new_rows) == [winner_jti]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_classify_lost_update_distinguishes_raced_and_reuse(
    db_session: AsyncSession, member: User
):
    """两条「已吊销」路径共用的判定：窗口内 RACED → 窗口外 REUSE → 行没了 INVALID。

    内存 sqlite（StaticPool 单连接）不能真并发；顺序调用后的库状态与「赢家已提交、
    输家刚到」完全一致，所以这里是确定性构造。
    """
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
    assert (
        await token_store.rotate_refresh_token(
            db_session,
            old_jti=old_payload["jti"],
            user_id=str(member.id),
            new_jti=new_payload["jti"],
            new_expires_at=token_store.expires_at_from_payload(new_payload),
        )
        == token_store.ROTATE_OK
    )
    await db_session.commit()

    assert (
        await token_store._classify_lost_update(
            db_session, old_jti=old_payload["jti"], user_id=str(member.id)
        )
        == token_store.ROTATE_RACED
    )

    row = await db_session.get(
        RefreshToken, old_payload["jti"], populate_existing=True
    )
    row.revoked_at = utcnow() - timedelta(seconds=11)
    await db_session.commit()
    assert (
        await token_store._classify_lost_update(
            db_session, old_jti=old_payload["jti"], user_id=str(member.id)
        )
        == token_store.ROTATE_REUSE
    )

    await db_session.delete(
        await db_session.get(
            RefreshToken, old_payload["jti"], populate_existing=True
        )
    )
    await db_session.commit()
    assert (
        await token_store._classify_lost_update(
            db_session, old_jti=old_payload["jti"], user_id=str(member.id)
        )
        == token_store.ROTATE_INVALID
    )


# ---------------------------------------------------------------------------
# 待办 1：条件 UPDATE 落空（rowcount == 0）这条生产主路径的接线
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("revoked_ago_seconds", "replaced_by", "expected"),
    [
        (1, "lost-update-winner", token_store.ROTATE_RACED),
        (11, "lost-update-winner", token_store.ROTATE_REUSE),
        (1, None, token_store.ROTATE_REUSE),
    ],
    ids=["within-window", "after-window", "no-winner-pointer"],
)
@pytest.mark.asyncio
async def test_rotate_lost_update_is_wired_through_rowcount_branch(
    db_session: AsyncSession,
    member: User,
    monkeypatch,
    revoked_ago_seconds: int,
    replaced_by,
    expected: str,
):
    """条件 UPDATE 落空后的分支必须真的被执行到，且按库内真值分类。

    SQLite 下造不出「两个事务同时 UPDATE 同一行」：``BEGIN IMMEDIATE`` 那种抢锁只会让
    落败方在**前置检查**那一行就返回，走不到 ``rowcount == 0``。这里换成让前置读取看到
    一份「活跃快照」（等价于「赢家在我读完之后才提交」），库内真实行按三种结局构造。
    """
    old_jti = "lost-update-old"
    winner_jti = "lost-update-winner"
    new_jti = "lost-update-new"
    db_session.add(
        RefreshToken(
            jti=old_jti,
            user_id=member.id,
            expires_at=utcnow() + timedelta(days=1),
            revoked_at=utcnow() - timedelta(seconds=revoked_ago_seconds),
            replaced_by=replaced_by,
        )
    )
    db_session.add(
        RefreshToken(
            jti=winner_jti,
            user_id=member.id,
            expires_at=utcnow() + timedelta(days=1),
        )
    )
    await db_session.commit()
    before = int(
        (await db_session.execute(select(func.count()).select_from(RefreshToken))).scalar_one()
    )

    # 前置读取看到的是「赢家提交之前」的活跃快照；之后再读都走真实数据库。
    snapshot = SimpleNamespace(
        jti=old_jti,
        user_id=member.id,
        revoked_at=None,
        replaced_by=None,
        expires_at=utcnow() + timedelta(days=1),
        iam_access_token_enc=None,
        iam_refresh_token_enc=None,
        iam_access_expires_at=None,
        iam_checked_at=None,
    )
    real_get = db_session.get
    seen: list[tuple[str, dict]] = []

    async def fake_get(entity, ident, **kwargs):
        seen.append((ident, dict(kwargs)))
        if entity is RefreshToken and ident == old_jti and len(seen) == 1:
            return snapshot
        return await real_get(entity, ident, **kwargs)

    monkeypatch.setattr(db_session, "get", fake_get)

    # 插桩：接线被改回 `return ROTATE_REUSE` 时这里会变成空列表。
    classify_calls: list[str] = []
    real_classify = token_store._classify_lost_update

    async def spy_classify(db, *, old_jti, user_id):
        classify_calls.append(old_jti)
        return await real_classify(db, old_jti=old_jti, user_id=user_id)

    monkeypatch.setattr(token_store, "_classify_lost_update", spy_classify)

    result = await token_store.rotate_refresh_token(
        db_session,
        old_jti=old_jti,
        user_id=member.id,
        new_jti=new_jti,
        new_expires_at=utcnow() + timedelta(days=1),
    )

    assert result == expected
    # rowcount 分支真的被执行过：前置检查分支不会调 _classify_lost_update。
    assert classify_calls == [old_jti]
    # 前置读取 + _classify_lost_update 的回读；回读必须带 populate_existing（见实现注释）。
    assert [ident for ident, _ in seen] == [old_jti, old_jti]
    assert seen[1][1].get("populate_existing") is True

    db_session.expire_all()
    after = int(
        (await db_session.execute(select(func.count()).select_from(RefreshToken))).scalar_one()
    )
    rows = {
        row.jti: row
        for row in (await db_session.execute(select(RefreshToken))).scalars().all()
    }
    # 落败方不建行、不改行：库里仍是赢家写的状态。
    assert after == before
    assert new_jti not in rows
    assert rows[old_jti].revoked_at is not None
    assert rows[old_jti].replaced_by == replaced_by
    assert rows[winner_jti].revoked_at is None
    assert rows[winner_jti].replaced_by is None


@pytest.mark.asyncio
async def test_classify_lost_update_reads_db_not_stale_identity_map(
    db_session: AsyncSession, member: User
):
    """落败方的 identity map 里是「活跃」对象时，分类必须读数据库真值而非内存假象。

    ORM 的 synchronize_session 会把 UPDATE 的 values 就地写进内存对象（实测：条件 UPDATE
    rowcount=0 时，内存里的 revoked_at 仍被改成 now、replaced_by 被改成新 jti）。少了
    ``populate_existing``，-11s 的真复用会被误判成窗口内竞态（RACED），正是这类回归的
    放行口。
    """
    old_jti = "stale-map-old"
    winner_jti = "stale-map-winner"
    db_session.add(
        RefreshToken(
            jti=old_jti,
            user_id=member.id,
            expires_at=utcnow() + timedelta(days=1),
        )
    )
    await db_session.commit()

    # 内存里持有活跃对象（clean），随后库内被「别人」吊销 —— 生产上赢家提交后的落败方。
    # 必须留住强引用：``Session.identity_map`` 是弱引用表，只写 ``await get(...)`` 的
    # 话对象当场被回收，回读照样打数据库，这条用例就测不到 identity map 了。
    cached = await db_session.get(RefreshToken, old_jti, populate_existing=True)
    assert cached is not None
    await db_session.execute(
        text(
            "UPDATE refresh_tokens SET revoked_at = :revoked_at, replaced_by = :replaced_by "
            "WHERE jti = :jti"
        ),
        {
            "revoked_at": utcnow() - timedelta(seconds=11),
            "replaced_by": winner_jti,
            "jti": old_jti,
        },
    )

    # 与 rotate_refresh_token 相同的条件 UPDATE：rowcount == 0。
    lost = await db_session.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == old_jti, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow(), replaced_by="loser-new")
    )
    assert lost.rowcount == 0

    classified = await token_store._classify_lost_update(
        db_session, old_jti=old_jti, user_id=member.id
    )
    assert classified == token_store.ROTATE_REUSE


def test_race_loser_clamps_negative_elapsed():
    """时钟回拨（revoked_at 在未来）仍算窗口内落败，不能判成盗用。

    ``revoked_at`` 是 naive UTC（``app.common.time.utcnow``），这里必须用同一个
    ``utcnow()`` 构造，否则 -1s 会漂成 -8h，红得莫名其妙。
    """
    record = SimpleNamespace(
        revoked_at=utcnow() + timedelta(seconds=5), replaced_by="someone-else"
    )
    assert token_store._is_race_loser(record) is True


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
async def test_refresh_api_reuse_revokes_all_sessions(
    api_client: httpx.AsyncClient, db_session: AsyncSession
):
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

    # 窗口外真复用：把旧行的 revoked_at 推到竞态窗口之外（-11s）。留在窗口内会被
    # 判成并发落败（409 / ROTATE_RACED），那不是本用例要守的安全底线。
    old_payload = jwt_handler.decode_token(old_refresh)
    old_row = await db_session.get(
        RefreshToken, old_payload["jti"], populate_existing=True
    )
    old_row.revoked_at = utcnow() - timedelta(seconds=11)
    await db_session.commit()

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


@pytest.mark.asyncio
async def test_refresh_raced_returns_409_without_revoking_other_sessions(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
):
    """并发刷新落败方回 409 / 40104：不吊销全端、不清票据、不下发 Cookie。

    内存 sqlite（StaticPool 只有一条连接）不能真并发。这里用「赢家已经提交、同一张
    旧票在 10 秒窗口内再次出现」预置出竞态态 —— 库里的状态与真实并发里晚到的那一方
    看到的完全一致，属于确定性构造。
    """
    caplog.set_level(logging.WARNING, logger="app.api.v1.auth")

    device_a = await _login(api_client)
    refresh_a = device_a.json()["data"]["refresh_token"]
    device_b = await _login(api_client)
    refresh_b = device_b.json()["data"]["refresh_token"]
    assert refresh_a and refresh_b

    # 设备 A 先正常刷新一次（这次的赢家）
    api_client.cookies.clear()
    first = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_a}
    )
    assert first.status_code == 200, first.text
    refresh_a2 = first.cookies.get(REFRESH_COOKIE)
    assert refresh_a2 and refresh_a2 != refresh_a

    old_jti = str(jwt_handler.decode_token(refresh_a)["jti"])
    new_jti = str(jwt_handler.decode_token(refresh_a2)["jti"])

    # 同一张旧票在窗口内再来一次：并发落败方，必须是 409 而不是 401。
    api_client.cookies.clear()
    raced = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_a}
    )
    assert raced.status_code == 409, raced.text
    body = raced.json()
    assert body["code"] == 40104
    assert body["message"] == "会话正在其他窗口刷新，请稍后重试"
    assert body["detail"]["reason"] == "token_rotated"
    assert body["data"] is None
    # 409 不写 Cookie：否则会盖掉赢家刚写入的新票据。
    assert raced.headers.get_list("set-cookie") == []

    # 409 之后 get_db 已回滚并 expire 了全部对象，必须重新取行再断言。
    old_row = await db_session.get(RefreshToken, old_jti, populate_existing=True)
    assert old_row.revoked_at is not None
    assert old_row.replaced_by == new_jti

    # 活跃行恰好两条：赢家 A2 与设备 B —— 没有被「全端吊销」。
    active = set(
        (
            await db_session.execute(
                select(RefreshToken.jti).where(RefreshToken.revoked_at.is_(None))
            )
        ).scalars()
    )
    b_jti = str(jwt_handler.decode_token(refresh_b)["jti"])
    assert active == {new_jti, b_jti}

    # 两台设备都还能继续刷新。
    api_client.cookies.clear()
    again_a = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_a2}
    )
    assert again_a.status_code == 200, again_a.text
    api_client.cookies.clear()
    again_b = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_b}
    )
    assert again_b.status_code == 200, again_b.text

    # 日志：一条 raced warning，带 jti 指纹，但不含任何明文令牌。
    raced_logs = [
        record
        for record in caplog.records
        if record.name == "app.api.v1.auth"
        and "event=refresh_raced" in record.getMessage()
    ]
    assert len(raced_logs) == 1
    message = raced_logs[0].getMessage()
    assert "reason=token_rotated" in message
    fingerprint = message.split("old_jti_fp=")[1].split()[0]
    assert fingerprint == hashlib.sha256(old_jti.encode("utf-8")).hexdigest()[:12]
    assert len(fingerprint) == 12
    assert refresh_a not in caplog.text
    assert old_jti not in caplog.text


@pytest.mark.asyncio
async def test_reuse_after_race_window_revokes_all_sessions_via_api(
    api_client: httpx.AsyncClient, db_session: AsyncSession
):
    """窗口外的旧票是真复用：端点仍回 401 并吊销该用户全部会话。

    与 store 段的同名用例互补：这条守住端点的安全底线，不许被 409 分支弱化。
    """
    device_a = await _login(api_client)
    refresh_a = device_a.json()["data"]["refresh_token"]
    device_b = await _login(api_client)
    refresh_b = device_b.json()["data"]["refresh_token"]

    api_client.cookies.clear()
    first = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_a}
    )
    assert first.status_code == 200, first.text
    refresh_a2 = first.cookies.get(REFRESH_COOKIE)
    assert refresh_a2 and refresh_a2 != refresh_a

    # 把旧行的吊销时间推到竞态窗口之外（-11s），它就不再是并发落败，而是盗用。
    old_jti = str(jwt_handler.decode_token(refresh_a)["jti"])
    old_row = await db_session.get(RefreshToken, old_jti, populate_existing=True)
    old_row.revoked_at = utcnow() - timedelta(seconds=11)
    await db_session.commit()

    api_client.cookies.clear()
    reuse = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_a}
    )
    assert reuse.status_code == 401, reuse.text
    assert "刷新令牌已被使用" in reuse.json()["message"]

    # 全端吊销：赢家 A2 与设备 B 都被踢。
    api_client.cookies.clear()
    after_a = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_a2}
    )
    assert after_a.status_code == 401, after_a.text

    api_client.cookies.clear()
    after_b = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_b}
    )
    assert after_b.status_code == 401, after_b.text


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
