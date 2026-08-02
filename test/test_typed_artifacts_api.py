"""Typed project Artifact API tests."""

from __future__ import annotations

import hashlib
from datetime import timedelta

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.common.time import utcnow
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.projects import Organization, Project, ProjectMember
from app.models.users import User, UserRole, UserStatus
from app.storage.base import StorageFile


class RecordingStorage:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.uploads: list[tuple[str, bytes]] = []
        self.objects: dict[str, tuple[bytes, str | None]] = {}

    async def upload(
        self, file_data: bytes, path: str, content_type: str | None = None
    ):
        if self.fail:
            raise RuntimeError("object storage unavailable")
        self.uploads.append((path, file_data))
        self.objects[path] = (file_data, content_type)
        return StorageFile(
            path=path, size=len(file_data), content_type=content_type, etag="etag"
        )

    async def download(self, path: str) -> bytes:
        return self.objects[path][0]

    async def delete(self, path: str) -> bool:
        return True


@pytest_asyncio.fixture
async def artifact_db() -> AsyncSession:
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
async def artifact_context(artifact_db: AsyncSession) -> dict[str, object]:
    owner = User(
        email="artifact-owner@example.com",
        password_hash="hashed",
        display_name="owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    outsider = User(
        email="artifact-outsider@example.com",
        password_hash="hashed",
        display_name="outsider",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    organization = Organization(name="Artifact Lab", slug="artifact-lab")
    artifact_db.add_all([owner, outsider, organization])
    await artifact_db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name="Pocket study",
        status="active",
    )
    artifact_db.add(project)
    await artifact_db.flush()
    artifact_db.add(
        ProjectMember(project_id=project.id, user_id=owner.id, role="owner")
    )
    await artifact_db.commit()
    return {
        "owner": owner,
        "outsider": outsider,
        "organization": organization,
        "project": project,
    }


@pytest_asyncio.fixture
async def artifact_client(
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
):
    from app.api.v1.artifacts import get_artifact_storage

    storage = RecordingStorage()

    async def override_get_db():
        yield artifact_db

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        user = artifact_context.get(token)
        if isinstance(user, User):
            return user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_artifact_storage] = lambda: storage
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client, storage
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_artifact_upload_uses_generated_key_and_deduplicates_by_sha256(
    artifact_client,
    artifact_context: dict[str, object],
):
    client, storage = artifact_client
    project = artifact_context["project"]
    content = b"HEADER    PUBLIC TEST PROTEIN\nEND\n"
    request = {
        "artifact_type": "protein_structure",
        "semantic_type": "protein_structure",
        "storage_key": "attacker/chosen/path",
    }

    first = await client.post(
        f"/api/v1/projects/{project.id}/artifacts",
        headers={"Authorization": "Bearer owner"},
        data=request,
        files={"file": ("protein.pdb", content, "chemical/x-pdb")},
    )
    second = await client.post(
        f"/api/v1/projects/{project.id}/artifacts",
        headers={"Authorization": "Bearer owner"},
        data=request,
        files={"file": ("renamed.pdb", content, "chemical/x-pdb")},
    )

    assert first.status_code == second.status_code == 200
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert second_data["id"] == first_data["id"]
    assert second_data["deduplicated"] is True
    assert len(storage.uploads) == 1
    object_key = storage.uploads[0][0]
    assert object_key.startswith(
        f"organizations/{artifact_context['organization'].id}/projects/{project.id}/artifacts/"
    )
    assert "attacker" not in object_key
    assert first_data["latest_version"]["sha256"] == hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_artifact_versions_are_immutable_and_expired_items_are_hidden(
    artifact_client,
    artifact_context: dict[str, object],
):
    client, _ = artifact_client
    project = artifact_context["project"]
    headers = {"Authorization": "Bearer owner"}
    created = await client.post(
        f"/api/v1/projects/{project.id}/artifacts",
        headers=headers,
        data={"artifact_type": "run_report", "semantic_type": "run_report"},
        files={"file": ("report.json", b'{"version":1}', "application/json")},
    )
    artifact = created.json()["data"]
    first_sha = artifact["latest_version"]["sha256"]

    version = await client.post(
        f"/api/v1/artifacts/{artifact['id']}/versions",
        headers=headers,
        data={"expires_at": (utcnow() - timedelta(seconds=1)).isoformat()},
        files={"file": ("report.json", b'{"version":2}', "application/json")},
    )
    assert version.status_code == 200
    assert version.json()["data"]["latest_version"]["version"] == 2

    detail = await client.get(f"/api/v1/artifacts/{artifact['id']}", headers=headers)
    assert detail.status_code == 200
    versions = detail.json()["data"]["versions"]
    assert len(versions) == 2
    assert versions[0]["sha256"] == first_sha

    listed = await client.get(
        f"/api/v1/projects/{project.id}/artifacts", headers=headers
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["items"] == []

    hidden = await client.get(
        f"/api/v1/projects/{project.id}/artifacts",
        headers={"Authorization": "Bearer outsider"},
    )
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_standard_artifact_metadata_is_returned_in_project_list(
    artifact_client,
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
):
    from app.models.artifacts import Artifact, ArtifactVersion

    client, _ = artifact_client
    project = artifact_context["project"]
    owner = artifact_context["owner"]
    artifact = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure@1",
        standard_type="protein_structure",
        standard_version=1,
        name="target.pdb",
    )
    artifact_db.add(artifact)
    await artifact_db.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename="target.pdb",
        content_type="chemical/x-pdb",
        size_bytes=12,
        sha256="a" * 64,
        storage_key="standard/target.pdb",
        status="available",
    )
    artifact_db.add(version)
    await artifact_db.flush()
    artifact.latest_version_id = version.id
    artifact.latest_version = version
    await artifact_db.commit()

    listed = await client.get(
        f"/api/v1/projects/{project.id}/artifacts",
        headers={"Authorization": "Bearer owner"},
    )

    assert listed.status_code == 200
    item = listed.json()["data"]["items"][0]
    assert item["standard_type"] == "protein_structure"
    assert item["standard_version"] == 1


@pytest.mark.asyncio
async def test_artifact_version_download_uses_storage_and_project_acl(
    artifact_client,
    artifact_context: dict[str, object],
):
    client, _ = artifact_client
    project = artifact_context["project"]
    content = b"HEADER    DOWNLOADABLE PROTEIN\nEND\n"
    created = await client.post(
        f"/api/v1/projects/{project.id}/artifacts",
        headers={"Authorization": "Bearer owner"},
        data={
            "artifact_type": "protein_structure",
            "semantic_type": "protein_structure",
        },
        files={"file": ("protein.pdb", content, "chemical/x-pdb")},
    )
    artifact = created.json()["data"]
    version = artifact["latest_version"]

    downloaded = await client.get(
        f"/api/v1/artifacts/{artifact['id']}/versions/{version['id']}/download",
        headers={"Authorization": "Bearer owner"},
    )
    hidden = await client.get(
        f"/api/v1/artifacts/{artifact['id']}/versions/{version['id']}/download",
        headers={"Authorization": "Bearer outsider"},
    )

    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["content-type"].startswith("chemical/x-pdb")
    assert "protein.pdb" in downloaded.headers["content-disposition"]
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_storage_failure_leaves_no_artifact_metadata(
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
):
    from app.models.artifacts import Artifact, ArtifactVersion
    from app.services.artifacts import create_artifact

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await create_artifact(
            artifact_db,
            storage=RecordingStorage(fail=True),
            project=artifact_context["project"],
            user=artifact_context["owner"],
            filename="failed.pdb",
            content=b"failed",
            content_type="chemical/x-pdb",
            artifact_type="protein_structure",
            semantic_type="protein_structure",
        )

    assert await artifact_db.scalar(select(func.count(Artifact.id))) == 0
    assert await artifact_db.scalar(select(func.count(ArtifactVersion.id))) == 0
