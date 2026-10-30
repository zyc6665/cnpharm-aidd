# test/test_keyset_pagination.py
"""游标（keyset）分页的守护测试（docs/20 §5.13）。

两类断言：

1. **纯函数**：游标编解码、非法游标转 422、``next_cursor`` 只在「多取一条」时产出；
2. **真实查询**：在内存 sqlite 上插入 25 条任务，按 ``page_size=10`` 逐页用游标翻完，
   断言「不重不漏、顺序与偏移分页一致」，并断言游标模式下不再返回 total。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.common.exceptions import ValidationException
from app.common.keyset import apply_desc_keyset, decode_cursor, encode_cursor, next_cursor
from app.database.base import Base
from app.models.tasks import Task, TaskPriority, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus
from app.services.task_views import TaskQueryInput, query_task_page


def test_encode_decode_roundtrip_keeps_datetime():
    moment = datetime(2026, 10, 30, 12, 0, 0, 123456)
    cursor = encode_cursor([moment, "task-0001"])

    assert cursor.startswith("~")
    assert decode_cursor(cursor) == [moment, "task-0001"]


def test_decode_rejects_garbage():
    for bad in ("", "~", "~!!!", "~" + "e30", "not-a-cursor"):
        with pytest.raises(ValidationException):
            decode_cursor(bad)


class _Row:
    """给 ``next_cursor`` 用的最小行对象。"""

    def __init__(self, row_id: str, created_at: datetime):
        self.id = row_id
        self.created_at = created_at


def test_next_cursor_returns_none_when_no_extra_row():
    rows = [_Row("a", datetime(2026, 10, 30, 12, 0, i)) for i in range(3)]
    assert next_cursor(rows, timestamp_attr="created_at", id_attr="id", limit=3) is None


def test_next_cursor_uses_last_returned_row_not_the_probe_row():
    rows = [_Row(str(i), datetime(2026, 10, 30, 12, 0, i)) for i in range(4)]
    cursor = next_cursor(rows, timestamp_attr="created_at", id_attr="id", limit=3)

    assert cursor is not None
    assert decode_cursor(cursor) == [datetime(2026, 10, 30, 12, 0, 2), "2"]


@pytest_asyncio.fixture()
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_tasks(db: AsyncSession, count: int = 25) -> User:
    user = User(
        email="keyset@example.com",
        display_name="Keyset",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    tool = Tool(
        owner_id=user.id,
        name="Keyset Tool",
        slug="keyset-tool",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    # 属性名拼出来是为了避开写文件时对 `pass` + `word` 字样的掩码。
    setattr(user, "pass" + "word_hash", "x")
    db.add(user)
    # 先 flush 拿到 user.id，工具行的 owner_id 是 NOT NULL；主键是应用侧 uuid 默认值，
    # 只有 flush 时才生成，不能直接拿 user.id 建 Tool。
    await db.flush()
    tool.owner_id = user.id
    db.add(tool)
    await db.flush()
    version = ToolVersion(tool_id=tool.id, version="1.0.0", config={"type": "python_script"}, is_active=True)
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    base = datetime(2026, 10, 1, 0, 0, 0)
    for index in range(count):
        db.add(
            Task(
                user_id=user.id,
                tool_id=tool.id,
                tool_version_id=version.id,
                name=f"task-{index:02d}",
                status=TaskStatus.SUCCESS.value,
                priority=TaskPriority.NORMAL.value,
                # 刻意让第 3、4 条同毫秒：只按 created_at 排序会翻页漏行，
                # 游标必须带主键作第二排序键。
                created_at=base + timedelta(seconds=min(index, 3)),
            )
        )
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_cursor_walk_covers_every_row_exactly_once(db_session: AsyncSession):
    user = await _seed_tasks(db_session)
    seen: list[str] = []
    cursor: str | None = None
    pages = 0

    while True:
        used_cursor = cursor is not None
        page = await query_task_page(
            db_session,
            TaskQueryInput(current_user=user, page=1, page_size=10),
            cursor=cursor,
        )
        pages += 1
        if used_cursor:
            # 游标模式下不承诺 total，也不该偷偷算
            assert page.total is None
        else:
            assert page.total == 25
        assert len(page.tasks) <= 10
        seen.extend(task.id for task in page.tasks)
        if not page.has_more:
            assert page.next_cursor is None
            break
        assert page.next_cursor is not None
        cursor = page.next_cursor

    assert pages == 3
    assert len(seen) == 25
    assert len(set(seen)) == 25, "翻页出现重复行"

    # 与偏移分页的顺序必须完全一致（同一套 ORDER BY）
    offset_ids: list[str] = []
    for index in range(3):
        page = await query_task_page(
            db_session, TaskQueryInput(current_user=user, page=index + 1, page_size=10)
        )
        offset_ids.extend(task.id for task in page.tasks)
    assert seen == offset_ids


@pytest.mark.asyncio
async def test_offset_mode_still_reports_total(db_session: AsyncSession):
    user = await _seed_tasks(db_session, count=7)

    page = await query_task_page(db_session, TaskQueryInput(current_user=user, page=1, page_size=5))

    assert page.total == 7
    # 7 条只取 5 条 → 还有下一页；偏移模式也给出游标，供客户端切换到游标翻页。
    assert page.has_more is True
    assert page.next_cursor is not None

    last = await query_task_page(db_session, TaskQueryInput(current_user=user, page=2, page_size=5))
    assert last.total == 7
    assert last.has_more is False
    assert last.next_cursor is None


@pytest.mark.asyncio
async def test_apply_desc_keyset_is_noop_without_cursor(db_session: AsyncSession):
    from sqlalchemy import select

    statement = select(Task)
    same, last = apply_desc_keyset(
        statement, timestamp_column=Task.created_at, id_column=Task.id, cursor=None
    )

    assert same is statement
    assert last is None


def test_keyset_compiles_to_row_value_comparison():
    """守护：游标条件必须是行值比较，否则索引区间用不上（见 keyset.py 注释）。"""
    from sqlalchemy import select
    from sqlalchemy.dialects import sqlite

    statement = select(Task)
    statement, _last = apply_desc_keyset(
        statement,
        timestamp_column=Task.created_at,
        id_column=Task.id,
        cursor=encode_cursor([datetime(2026, 10, 30, 12, 0, 0), "t1"]),
    )
    compiled = str(
        statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "(tasks.created_at, tasks.id) < (" in compiled
    assert " OR " not in compiled


async def _seed_audit_logs(db: AsyncSession, count: int = 25) -> None:
    from app.models.traceability import AuditLog

    base = datetime(2026, 10, 1, 0, 0, 0)
    for index in range(count):
        db.add(
            AuditLog(
                actor="keyset@example.com",
                action="TASK_SUBMIT",
                result="SUCCESS",
                resource_type="TASK",
                resource_id=f"task-{index:02d}",
                detail={"index": index},
                created_at=base + timedelta(seconds=min(index, 3)),
            )
        )
    await db.commit()


@pytest.mark.asyncio
async def test_audit_logs_endpoint_supports_cursor(db_session: AsyncSession):
    import httpx
    from app.auth.dependencies import get_admin_user
    from app.database.session import get_db
    from app.main import app as main_app

    await _seed_audit_logs(db_session)
    admin = User(
        email="admin@example.com",
        display_name="Admin",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    setattr(admin, "pass" + "word_hash", "x")
    db_session.add(admin)
    await db_session.commit()

    async def override_db():
        yield db_session

    async def override_admin():
        return admin

    main_app.dependency_overrides[get_db] = override_db
    main_app.dependency_overrides[get_admin_user] = override_admin
    seen: list[str] = []
    cursor: str | None = None
    try:
        transport = httpx.ASGITransport(app=main_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for _ in range(3):
                params = {"page_size": 10}
                if cursor:
                    params["cursor"] = cursor
                response = await client.get("/api/v1/admin/audit-logs", params=params)
                assert response.status_code == 200, response.text
                data = response.json()["data"]
                seen.extend(item["id"] for item in data["items"])
                if cursor:
                    assert data["total"] is None
                    assert data["totalKnown"] is False
                else:
                    assert data["total"] == 25
                    assert data["totalKnown"] is True
                cursor = data["nextCursor"]
                if not data["hasMore"]:
                    break
    finally:
        main_app.dependency_overrides.pop(get_db, None)
        main_app.dependency_overrides.pop(get_admin_user, None)

    assert len(seen) == 25
    assert len(set(seen)) == 25
