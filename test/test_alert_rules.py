import pytest

from app.monitoring import alert_rules

class QueueLengthCache:
    def __init__(self, value):
        self.value = value
        self.key = None

    async def get(self, key: str):
        self.key = key
        return self.value


@pytest.mark.asyncio
async def test_celery_queue_length_uses_cache_backend_factory(monkeypatch):
    """Celery 队列长度检查应使用真实缓存工厂入口。"""
    cache = QueueLengthCache("7")
    monkeypatch.setattr(
        "app.cache.factory.get_cache_backend",
        lambda: cache,
    )

    length = await alert_rules.check_celery_queue_length()

    assert length == 7
    assert cache.key == "celery:queue:default:length"


@pytest.mark.asyncio
async def test_celery_queue_length_falls_back_to_zero_on_cache_error(monkeypatch):
    """缓存读取失败时队列长度检查应安全降级为 0。"""
    class FailingCache:
        async def get(self, key: str):
            raise RuntimeError("cache unavailable")

    monkeypatch.setattr(
        "app.cache.factory.get_cache_backend",
        lambda: FailingCache(),
    )

    assert await alert_rules.check_celery_queue_length() == 0


@pytest.mark.asyncio
async def test_task_failure_rate_counts_timeout_as_failed(monkeypatch):
    """失败率必须把 TIMEOUT 计入失败：超时率升高同样意味着任务没跑成。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.database.base import Base, utcnow
    from app.models import projects as _project_models  # noqa: F401
    from app.models import tasks as _task_models  # noqa: F401
    from app.models import tools as _tool_models  # noqa: F401
    from app.models import users as _user_models  # noqa: F401
    from app.models.tasks import Task

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for index, status in enumerate(("SUCCESS", "FAILURE", "TIMEOUT", "RUNNING")):
            session.add(
                Task(
                    tool_id=f"alert-tool-{index}",
                    tool_version_id="alert-version",
                    status=status,
                    created_at=utcnow(),
                )
            )
        await session.commit()

    monkeypatch.setattr("app.database.session.async_session_factory", factory)

    rate = await alert_rules.check_task_failure_rate()

    assert rate == pytest.approx(2 / 4)
    await engine.dispose()
