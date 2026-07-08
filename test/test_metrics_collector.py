import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.files import File, FileSourceType
from app.monitoring.metrics_collector import MetricsCollector


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield session_factory

    await engine.dispose()


class FakeScalarResult:
    def __init__(self, value: int):
        self.value = value

    def scalar(self) -> int:
        return self.value


class FakeDbSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        return FakeScalarResult(3)


class FakeMetrics:
    def __init__(self):
        self.active_users = None
        self.file_storage_metrics = None

    def set_active_users(self, registered: int, guest: int) -> None:
        self.active_users = {"registered": registered, "guest": guest}

    def set_file_storage_metrics(
        self,
        *,
        storage_backend: str,
        used_bytes: int,
        file_counts: dict,
    ) -> None:
        self.file_storage_metrics = {
            "storage_backend": storage_backend,
            "used_bytes": used_bytes,
            "file_counts": file_counts,
        }


class FailingCache:
    async def keys(self, pattern: str):
        raise RuntimeError(f"cache unavailable for {pattern}")


class CapturingCache:
    def __init__(self):
        self.pattern = None

    async def keys(self, pattern: str):
        self.pattern = pattern
        return ["guest:one", "guest:two"]


def make_db_session():
    return FakeDbSession()


@pytest.mark.asyncio
async def test_user_metrics_logs_guest_cache_failures(caplog):
    metrics = FakeMetrics()
    collector = MetricsCollector(
        metrics=metrics,
        db_session_factory=make_db_session,
        cache_client=FailingCache(),
    )

    with caplog.at_level("WARNING", logger="app.monitoring.metrics_collector"):
        result = await collector._collect_user_metrics()

    assert result == {"active_registered": 3, "active_guests": 0}
    assert metrics.active_users == {"registered": 3, "guest": 0}
    assert any("Guest session metrics collection failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_user_metrics_counts_current_guest_cache_prefix():
    cache = CapturingCache()
    metrics = FakeMetrics()
    collector = MetricsCollector(
        metrics=metrics,
        db_session_factory=make_db_session,
        cache_client=cache,
    )

    result = await collector._collect_user_metrics()

    assert cache.pattern == "guest:*"
    assert result == {"active_registered": 3, "active_guests": 2}
    assert metrics.active_users == {"registered": 3, "guest": 2}


@pytest.mark.asyncio
async def test_file_metrics_sum_size_bytes(db_session_factory):
    async with db_session_factory() as session:
        session.add_all(
            [
                File(
                    filename="input.txt",
                    content_type="text/plain",
                    size_bytes=100,
                    sha256="sha-input",
                    storage_backend="local",
                    storage_path="/tmp/input.txt",
                    source_type=FileSourceType.UPLOAD.value,
                ),
                File(
                    filename="output.txt",
                    content_type="text/plain",
                    size_bytes=300,
                    sha256="sha-output",
                    storage_backend="local",
                    storage_path="/tmp/output.txt",
                    source_type=FileSourceType.TOOL_OUTPUT.value,
                ),
            ]
        )
        await session.commit()

    metrics = FakeMetrics()
    collector = MetricsCollector(
        metrics=metrics,
        db_session_factory=db_session_factory,
    )

    result = await collector._collect_file_metrics()

    assert result == {
        "total_files": 2,
        "total_size_bytes": 400,
        "by_source": {
            FileSourceType.UPLOAD.value: 1,
            FileSourceType.TOOL_OUTPUT.value: 1,
        },
    }
    assert metrics.file_storage_metrics == {
        "storage_backend": "default",
        "used_bytes": 400,
        "file_counts": {
            FileSourceType.UPLOAD.value: 1,
            FileSourceType.TOOL_OUTPUT.value: 1,
        },
    }
