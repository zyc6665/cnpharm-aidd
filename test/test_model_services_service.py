import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.secret_crypto import decrypt_secret
from app.database.base import Base
from app.models.system_settings import ModelService
from app.schemas.system_settings import ModelServiceCreate, ModelServiceUpdate
from app.services.model_services import (
    create_model_service,
    list_model_services,
    set_default_model_service,
    update_model_service,
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_model_service_encrypts_and_masks_key(session_factory):
    async with session_factory() as session:
        created = await create_model_service(
            session,
            ModelServiceCreate(
                name="DeepSeek",
                base_url="https://api.deepseek.com/v1",
                api_key="sk-secret",
                model_name="deepseek-chat",
                is_default=True,
            ),
        )
        await session.commit()

        stored = await session.get(ModelService, created.id)

    assert stored is not None
    assert stored.api_key_encrypted != "sk-secret"
    assert decrypt_secret(stored.api_key_encrypted) == "sk-secret"
    assert created.has_api_key is True
    assert created.api_key_masked == "sk-****cret"


@pytest.mark.asyncio
async def test_update_without_api_key_preserves_existing_secret(session_factory):
    async with session_factory() as session:
        created = await create_model_service(
            session,
            ModelServiceCreate(
                name="Primary",
                base_url="https://api.example.com/v1",
                api_key="sk-original",
                model_name="model-a",
            ),
        )
        await session.commit()

        updated = await update_model_service(
            session,
            created.id,
            ModelServiceUpdate(name="Primary Updated", model_name="model-b"),
        )
        await session.commit()

        stored = await session.get(ModelService, created.id)

    assert updated.name == "Primary Updated"
    assert stored is not None
    assert decrypt_secret(stored.api_key_encrypted) == "sk-original"


@pytest.mark.asyncio
async def test_set_default_model_service_clears_other_defaults(session_factory):
    async with session_factory() as session:
        first = await create_model_service(
            session,
            ModelServiceCreate(
                name="First",
                base_url="https://one.example.com/v1",
                api_key="sk-one",
                model_name="one",
                is_default=True,
            ),
        )
        second = await create_model_service(
            session,
            ModelServiceCreate(
                name="Second",
                base_url="https://two.example.com/v1",
                api_key="sk-two",
                model_name="two",
            ),
        )
        await set_default_model_service(session, second.id)
        await session.commit()

        result = await session.execute(select(ModelService).order_by(ModelService.name))
        services = result.scalars().all()
        listed = await list_model_services(session)

    assert [(service.name, service.is_default) for service in services] == [
        ("First", False),
        ("Second", True),
    ]
    assert [item.id for item in listed] == [second.id, first.id]


@pytest.mark.asyncio
async def test_first_enabled_service_becomes_default(session_factory):
    async with session_factory() as session:
        created = await create_model_service(
            session,
            ModelServiceCreate(
                name="First",
                base_url="https://one.example.com/v1",
                model_name="one",
            ),
        )

    assert created.is_default is True


@pytest.mark.asyncio
async def test_deleting_default_promotes_another_enabled_service(session_factory):
    async with session_factory() as session:
        first = await create_model_service(
            session,
            ModelServiceCreate(
                name="First",
                base_url="https://one.example.com/v1",
                model_name="one",
                is_default=True,
            ),
        )
        second = await create_model_service(
            session,
            ModelServiceCreate(
                name="Second",
                base_url="https://two.example.com/v1",
                model_name="two",
            ),
        )
        from app.services.model_services import delete_model_service

        await delete_model_service(session, first.id)
        await session.commit()
        stored = await session.get(ModelService, second.id)

    assert stored is not None
    assert stored.is_default is True


@pytest.mark.asyncio
async def test_disabling_default_promotes_another_enabled_service(session_factory):
    async with session_factory() as session:
        first = await create_model_service(
            session,
            ModelServiceCreate(
                name="First",
                base_url="https://one.example.com/v1",
                model_name="one",
                is_default=True,
            ),
        )
        second = await create_model_service(
            session,
            ModelServiceCreate(
                name="Second",
                base_url="https://two.example.com/v1",
                model_name="two",
            ),
        )

        await update_model_service(
            session,
            first.id,
            ModelServiceUpdate(is_enabled=False),
        )
        await session.commit()
        stored_first = await session.get(ModelService, first.id)
        stored_second = await session.get(ModelService, second.id)

    assert stored_first is not None and stored_first.is_default is False
    assert stored_second is not None and stored_second.is_default is True
