import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import get_admin_user, get_current_user
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import users as _users_models  # noqa: F401
from app.models.system_settings import ModelService
from app.models.users import User


@pytest_asyncio.fixture
async def admin_client(tmp_path: Path):
    db_path = tmp_path / "model-services-api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    admin = User(
        id=str(uuid.uuid4()),
        email="admin@test.local",
        password_hash="bcrypt-placeholder",
        display_name="admin",
        role="admin",
        status="active",
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def override_current_user():
        return admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_admin_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_model_service_admin_crud_never_returns_plaintext_key(admin_client):
    client, session_factory = admin_client

    create_response = await client.post(
        "/api/v1/system/model-services",
        json={
            "name": "DeepSeek",
            "provider_type": "openai_compatible",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-secret",
            "model_name": "deepseek-chat",
            "is_default": True,
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert created["has_api_key"] is True
    assert created["api_key_masked"] == "sk-****cret"
    assert "sk-secret" not in create_response.text
    assert "api_key_encrypted" not in created

    list_response = await client.get("/api/v1/system/model-services")
    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["id"] == created["id"]
    assert "sk-secret" not in list_response.text

    update_response = await client.put(
        f"/api/v1/system/model-services/{created['id']}",
        json={"name": "DeepSeek Default", "model_name": "deepseek-reasoner"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["name"] == "DeepSeek Default"

    async with session_factory() as session:
        stored = await session.get(ModelService, created["id"])

    assert stored is not None
    assert stored.api_key_encrypted is not None
    assert "sk-secret" not in stored.api_key_encrypted

    default_response = await client.post(
        f"/api/v1/system/model-services/{created['id']}/set-default"
    )
    assert default_response.status_code == 200
    assert default_response.json()["data"]["is_default"] is True

    delete_response = await client.delete(f"/api/v1/system/model-services/{created['id']}")
    assert delete_response.status_code == 200

    empty_response = await client.get("/api/v1/system/model-services")
    assert empty_response.json()["data"]["items"] == []
