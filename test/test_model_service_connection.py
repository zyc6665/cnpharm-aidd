import sys
import logging
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models.system_settings import ModelService
from app.schemas.system_settings import ModelServiceCreate
from app.services import openai_compatible
from app.services.model_services import create_model_service, test_model_service as run_model_service_test


@pytest.mark.asyncio
async def test_model_service_connection_updates_success(monkeypatch):
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
        autocommit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def fake_test(service):
        return True, f"connected:{service.model_name}"

    monkeypatch.setattr(openai_compatible, "test_openai_compatible_service", fake_test)

    async with session_factory() as session:
        created = await create_model_service(
            session,
            ModelServiceCreate(
                name="Default",
                base_url="https://api.example.com/v1",
                api_key="sk-test",
                model_name="model",
            ),
        )
        result = await run_model_service_test(session, created.id)
        await session.commit()
        stored = await session.get(ModelService, created.id)

    await engine.dispose()

    assert result.success is True
    assert result.message == "connected:model"
    assert stored is not None
    assert stored.last_test_status == "success"
    assert stored.last_test_message == "connected:model"


@pytest.mark.asyncio
async def test_openai_compatible_connection_posts_chat_completion(monkeypatch):
    captured = {}

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "pong"}}]}

    class DummyClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return DummyResponse()

    monkeypatch.setattr(openai_compatible.httpx, "AsyncClient", DummyClient)

    service = ModelService(
        name="Default",
        provider_type="openai_compatible",
        base_url="https://api.example.com/v1/",
        api_key_encrypted=None,
        model_name="model",
        timeout_seconds=30,
        max_tokens=256,
        temperature=0.3,
    )

    success, message = await openai_compatible.test_openai_compatible_service(
        service,
        api_key="sk-direct",
    )

    assert success is True
    assert "pong" in message
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-direct"
    assert captured["json"]["model"] == "model"
    assert captured["json"]["max_tokens"] == 8


def test_openai_compatible_response_content_fallbacks_are_explicit():
    assert openai_compatible._extract_chat_completion_content({}) == (
        "响应格式可用，但未返回标准 choices 内容"
    )
    assert openai_compatible._extract_chat_completion_content({"choices": []}) == (
        "响应格式可用，但未返回标准 choices 内容"
    )
    assert openai_compatible._extract_chat_completion_content(
        {"choices": [{"message": {"content": "pong"}}]}
    ) == "pong"


@pytest.mark.asyncio
async def test_openai_compatible_connection_failure_is_observable(monkeypatch, caplog):
    class FailingClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers):
            raise RuntimeError("connection failed")

    monkeypatch.setattr(openai_compatible.httpx, "AsyncClient", FailingClient)

    service = ModelService(
        name="Default",
        provider_type="openai_compatible",
        base_url="https://api.example.com/v1/",
        api_key_encrypted=None,
        model_name="model",
        timeout_seconds=30,
        max_tokens=256,
        temperature=0.3,
    )

    with caplog.at_level(logging.WARNING, logger="app.services.openai_compatible"):
        success, message = await openai_compatible.test_openai_compatible_service(
            service,
            api_key="sk-secret",
        )

    assert success is False
    assert message == "connection failed"
    assert "OpenAI-compatible service test failed for service=Default" in caplog.text
    assert "model=model" in caplog.text
    assert "https://api.example.com/v1/" in caplog.text
    assert "sk-secret" not in caplog.text


@pytest.mark.asyncio
async def test_openai_compatible_model_discovery_returns_sorted_ids(monkeypatch):
    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "z-model"}, {"id": "a-model"}, {"id": "z-model"}]}

    class DummyClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, headers):
            assert url == "https://api.example.com/v1/models"
            assert headers["Authorization"] == "Bearer sk-direct"
            return DummyResponse()

    monkeypatch.setattr(openai_compatible.httpx, "AsyncClient", DummyClient)
    service = ModelService(
        name="Default",
        provider_type="openai_compatible",
        base_url="https://api.example.com/v1/",
        api_key_encrypted=None,
        model_name="model",
        timeout_seconds=30,
    )

    success, models, message = await openai_compatible.list_openai_compatible_models(
        service,
        api_key="sk-direct",
    )

    assert success is True
    assert models == ["a-model", "z-model"]
    assert message == "已发现 2 个模型"
