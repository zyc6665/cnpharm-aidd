"""Tool Package management API tests."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.users import User, UserRole, UserStatus


def _manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/v1",
        "kind": "ToolPackage",
        "metadata": {"slug": "lvpocket", "name": "LVpocket", "version": "1.0.0"},
        "artifacts": {
            "inputs": [
                {
                    "name": "protein",
                    "semantic_type": "protein_structure",
                    "artifact_type": "protein_structure",
                }
            ],
            "outputs": [
                {
                    "name": "pockets",
                    "semantic_type": "pocket_result",
                    "artifact_type": "pocket_result",
                }
            ],
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["container"],
                "image": "registry.local/lvpocket:1.0.0",
                "entrypoint": ["/app/run"],
                "resources": {"cpu": 2, "memory_mb": 4096},
                "validation_status": "validated",
                "inputs": ["protein_structure"],
                "outputs": ["pocket_result"],
            }
        ],
    }


def _v2_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "molp-pc-runtime-test",
            "name": "MolP-PC Runtime Test",
            "version": "1.0.0",
        },
        "artifacts": {
            "inputs": [
                {"name": "molecules", "type": "molecule_table@1", "required": True}
            ],
            "outputs": [
                {
                    "name": "properties",
                    "type": "molecule_table@1",
                    "cardinality": "one",
                    "required": True,
                }
            ],
        },
        "parameters_schema": {"type": "object", "properties": {}},
        "adapter": {
            "input": [{"input": "molecules", "method": "mount_molecule_table"}],
            "output": [
                {
                    "output": "properties",
                    "method": "collect_prediction_table",
                    "validator_profile": "molecule_table_v1_core",
                }
            ],
        },
        "exposure": {"agent": True, "workflow": True, "direct_run": True},
        "runtime": {
            "python": "3.8",
            "cuda": "11.3",
            "executor_support": ["ssh_docker_exec", "slurm", "k8s_job"],
            "selection_policy": (
                "prefer container image by immutable digest; fallback to conda_pack"
            ),
            "artifacts": {
                "primary": {
                    "kind": "container",
                    "image": "registry.example/sciminer/molp-pc-runtime:1.0.0",
                    "image_digest": f"sha256:{'d' * 64}",
                    "includes": ["python", "cuda_runtime", "dependencies"],
                },
                "fallback": {
                    "kind": "conda_pack",
                    "uri": "artifacts://model-envs/molp-pc/1.0.0/env.tar.gz",
                    "sha256": "e" * 64,
                    "includes": ["python", "dependencies"],
                },
            },
            "weights": {
                "manifest_uri": "artifacts://model-weights/molp-pc/1.0.0/weights.json",
                "manifest_sha256": "f" * 64,
            },
            "cache_policy": {
                "key_fields": [
                    "metadata.slug",
                    "metadata.version",
                    "runtime.artifacts.selected.digest_or_sha256",
                    "runtime.weights.manifest_sha256",
                ],
                "mutable_host_paths_forbidden": True,
            },
        },
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["remote_job"],
                "entrypoint": ["runner/entrypoint.sh"],
                "resources": {"cpu": 2, "memory_mb": 4096},
                "validation_status": "unvalidated",
                "hardware_validated": False,
            }
        ],
    }


@pytest_asyncio.fixture
async def package_db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def package_users(package_db: AsyncSession) -> dict[str, User]:
    users = {
        "admin": User(
            email="package-admin@example.com",
            password_hash="hashed",
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
        ),
        "user": User(
            email="package-user@example.com",
            password_hash="hashed",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        ),
    }
    package_db.add_all(users.values())
    await package_db.commit()
    return users


@pytest_asyncio.fixture
async def package_client(package_db: AsyncSession, package_users: dict[str, User]):
    async def override_get_db():
        yield package_db

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in package_users:
            return package_users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_creates_and_reads_validated_tool_package(
    package_client: httpx.AsyncClient,
):
    created = await package_client.post(
        "/api/v1/tool-packages",
        headers={"Authorization": "Bearer admin"},
        json={"manifest": _manifest()},
    )

    assert created.status_code == 200
    data = created.json()["data"]
    assert data["slug"] == "lvpocket"
    assert data["status"] == "draft"
    assert data["current_version"]["validation_status"] == "valid"
    assert data["current_version"]["is_signed"] is False

    fetched = await package_client.get(
        f"/api/v1/tool-packages/{data['id']}",
        headers={"Authorization": "Bearer admin"},
    )
    assert fetched.status_code == 200
    assert (
        fetched.json()["data"]["current_version"]["manifest"]["metadata"]["version"]
        == "1.0.0"
    )


@pytest.mark.asyncio
async def test_admin_lists_tool_packages(package_client: httpx.AsyncClient):
    first_manifest = _manifest()
    second_manifest = _manifest()
    second_manifest["metadata"] = {
        "slug": "gcdm-standard",
        "name": "GCDM Standard",
        "version": "1.0.0",
    }

    for manifest in (first_manifest, second_manifest):
        response = await package_client.post(
            "/api/v1/tool-packages",
            headers={"Authorization": "Bearer admin"},
            json={"manifest": manifest},
        )
        assert response.status_code == 200

    response = await package_client.get(
        "/api/v1/tool-packages",
        headers={"Authorization": "Bearer admin"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert [item["slug"] for item in payload["items"]] == [
        "gcdm-standard",
        "lvpocket",
    ]
    assert payload["total"] == 2
    assert payload["items"][0]["current_version"]["validation_status"] == "valid"


@pytest.mark.asyncio
async def test_admin_creates_v2_tool_package_with_runtime_metadata(
    package_client: httpx.AsyncClient,
):
    created = await package_client.post(
        "/api/v1/tool-packages",
        headers={"Authorization": "Bearer admin"},
        json={"manifest": _v2_manifest()},
    )

    assert created.status_code == 200
    data = created.json()["data"]
    manifest = data["current_version"]["manifest"]
    assert data["slug"] == "molp-pc-runtime-test"
    assert manifest["api_version"] == "aidd.sciminer/tool-package.v2"
    assert manifest["runtime"]["artifacts"]["primary"]["image_digest"] == f"sha256:{'d' * 64}"
    assert manifest["runtime"]["weights"]["manifest_sha256"] == "f" * 64


@pytest.mark.asyncio
async def test_unsigned_tool_package_cannot_be_published(
    package_client: httpx.AsyncClient,
):
    created = await package_client.post(
        "/api/v1/tool-packages",
        headers={"Authorization": "Bearer admin"},
        json={"manifest": _manifest()},
    )
    package_id = created.json()["data"]["id"]

    response = await package_client.post(
        f"/api/v1/tool-packages/{package_id}/publish",
        headers={"Authorization": "Bearer admin"},
    )

    assert response.status_code == 422
    assert "签名" in response.json()["message"]


@pytest.mark.asyncio
async def test_signed_valid_tool_package_can_be_published(
    package_client: httpx.AsyncClient,
):
    created = await package_client.post(
        "/api/v1/tool-packages",
        headers={"Authorization": "Bearer admin"},
        json={"manifest": _manifest(), "signature": "cosign:sha256:test-signature"},
    )
    package_id = created.json()["data"]["id"]

    response = await package_client.post(
        f"/api/v1/tool-packages/{package_id}/publish",
        headers={"Authorization": "Bearer admin"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "published"


@pytest.mark.asyncio
async def test_regular_user_cannot_create_tool_package(
    package_client: httpx.AsyncClient,
):
    response = await package_client.post(
        "/api/v1/tool-packages",
        headers={"Authorization": "Bearer user"},
        json={"manifest": _manifest()},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_tool_package_api_can_be_disabled_by_release_flag(
    package_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.config import settings

    monkeypatch.setattr(settings, "TOOL_PACKAGE_V1_ENABLED", False)

    response = await package_client.post(
        "/api/v1/tool-packages",
        headers={"Authorization": "Bearer admin"},
        json={"manifest": _manifest()},
    )

    assert response.status_code == 404
    assert "功能未启用" in response.json()["detail"]
