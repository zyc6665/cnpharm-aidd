"""External database import API tests."""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import (  # noqa: F401
    Artifact,
    ArtifactVersion,
    ArtifactVersionFile,
    File,
    Organization,
    Project,
    ProjectMember,
    User,
)
from app.models.artifacts import Artifact
from app.models.projects import Organization, Project, ProjectMember
from app.models.users import User, UserRole, UserStatus
from app.storage.base import StorageFile


class RecordingStorage:
    def __init__(self):
        self.uploads: dict[str, tuple[bytes, str | None]] = {}

    async def upload(self, file_data: bytes, path: str, content_type: str | None = None):
        self.uploads[path] = (file_data, content_type)
        return StorageFile(path=path, size=len(file_data), content_type=content_type, etag="etag")

    async def download(self, path: str) -> bytes:
        return self.uploads[path][0]

    async def delete(self, path: str) -> bool:
        self.uploads.pop(path, None)
        return True


class FakeExternalProvider:
    async def fetch_ligand(self, identifier: str):
        from app.external_databases.providers import ExternalArtifactFile, ExternalArtifactPayload

        return ExternalArtifactPayload(
            artifact_type="ligand_structure",
            standard_ref="ligand_structure@1",
            name="Aspirin",
            description="Imported from PubChem",
            metadata={
                "ligand_id": f"pubchem:{identifier}",
                "source_database": "pubchem",
                "source_id": identifier,
                "pubchem_cid": identifier,
                "canonical_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
                "structure_3d_source": "pubchem_3d",
                "hydrogens_added": False,
            },
            files=[
                ExternalArtifactFile(
                    role="structure_file",
                    filename="aspirin.sdf",
                    content=b"primary 3d sdf",
                    content_type="chemical/x-mdl-sdfile",
                ),
                ExternalArtifactFile(
                    role="structure_2d_sdf",
                    filename="aspirin.2d.sdf",
                    content=b"2d sdf",
                    content_type="chemical/x-mdl-sdfile",
                ),
                ExternalArtifactFile(
                    role="structure_3d_sdf",
                    filename="aspirin.3d.sdf",
                    content=b"3d sdf",
                    content_type="chemical/x-mdl-sdfile",
                ),
            ],
        )

    async def fetch_protein(self, identifier: str):
        from app.external_databases.providers import ExternalArtifactFile, ExternalArtifactPayload

        return ExternalArtifactPayload(
            artifact_type="protein_structure",
            standard_ref="protein_structure@1",
            name=identifier.upper(),
            description="Imported from RCSB PDB",
            metadata={
                "chain_ids": ["A"],
                "residue_count": 10,
                "atom_count": 80,
                "structure_format": "pdb",
                "source_filename": f"{identifier.upper()}.pdb",
                "source_database": "rcsb",
                "source_id": identifier.upper(),
            },
            files=[
                ExternalArtifactFile(
                    role="structure_file",
                    filename=f"{identifier.upper()}.pdb",
                    content=b"HEADER    TEST PDB\nEND\n",
                    content_type="chemical/x-pdb",
                )
            ],
        )


@pytest_asyncio.fixture
async def external_db_session() -> AsyncSession:
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
async def external_db_context(external_db_session: AsyncSession) -> dict[str, object]:
    owner = User(
        email="external-owner@example.com",
        password_hash="hashed",
        display_name="owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    organization = Organization(name="External Lab", slug="external-lab")
    external_db_session.add_all([owner, organization])
    await external_db_session.flush()
    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name="External import study",
        status="active",
    )
    external_db_session.add(project)
    await external_db_session.flush()
    external_db_session.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    await external_db_session.commit()
    return {"owner": owner, "organization": organization, "project": project}


@pytest_asyncio.fixture
async def external_db_client(
    external_db_session: AsyncSession,
    external_db_context: dict[str, object],
):
    from app.api.v1.external_databases import (
        get_external_database_providers,
        get_external_database_storage,
    )

    storage = RecordingStorage()

    async def override_get_db():
        yield external_db_session

    async def override_get_current_user(authorization: str | None = Header(default=None)) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        user = external_db_context.get(token)
        if isinstance(user, User):
            return user
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_external_database_storage] = lambda: storage
    app.dependency_overrides[get_external_database_providers] = lambda: {
        "pubchem": FakeExternalProvider(),
        "rcsb": FakeExternalProvider(),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client, storage
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pubchem_ligand_import_creates_standard_artifact(
    external_db_client,
    external_db_context: dict[str, object],
    external_db_session: AsyncSession,
):
    client, _ = external_db_client
    project = external_db_context["project"]

    response = await client.post(
        f"/api/v1/projects/{project.id}/external-databases/import",
        headers={"Authorization": "Bearer owner"},
        json={
            "source": "pubchem",
            "entity_type": "ligand",
            "identifier": "2244",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["artifact"]["standard_type"] == "ligand_structure"
    files_by_role = {
        item["role"]: item for item in data["artifact"]["latest_version"]["files"]
    }
    assert set(files_by_role) == {
        "structure_file",
        "structure_2d_sdf",
        "structure_3d_sdf",
        "metadata_json",
    }
    assert files_by_role["structure_file"]["is_primary"] is True

    artifact = await external_db_session.get(
        Artifact,
        data["artifact"]["id"],
        options=[selectinload(Artifact.latest_version)],
    )
    assert artifact is not None
    assert artifact.latest_version.manifest_json["metadata"]["pubchem_cid"] == "2244"
    assert artifact.latest_version.manifest_json["metadata"]["fetched_at"]


@pytest.mark.asyncio
async def test_rcsb_protein_import_creates_required_metadata_json(
    external_db_client,
    external_db_context: dict[str, object],
    external_db_session: AsyncSession,
):
    client, storage = external_db_client
    project = external_db_context["project"]

    response = await client.post(
        f"/api/v1/projects/{project.id}/external-databases/import",
        headers={"Authorization": "Bearer owner"},
        json={"source": "rcsb", "entity_type": "protein", "identifier": "1abc"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    files_by_role = {
        item["role"]: item for item in data["artifact"]["latest_version"]["files"]
    }
    assert data["artifact"]["standard_type"] == "protein_structure"
    assert set(files_by_role) == {"structure_file", "metadata_json"}
    metadata_path = next(
        path for path in storage.uploads if path.endswith("metadata.json")
    )
    metadata = json.loads(storage.uploads[metadata_path][0].decode("utf-8"))
    assert metadata["source_database"] == "rcsb"
    assert metadata["source_id"] == "1ABC"


@pytest.mark.asyncio
async def test_external_database_import_rejects_mismatched_source_and_entity(
    external_db_client,
    external_db_context: dict[str, object],
):
    client, _ = external_db_client
    project = external_db_context["project"]

    response = await client.post(
        f"/api/v1/projects/{project.id}/external-databases/import",
        headers={"Authorization": "Bearer owner"},
        json={"source": "pubchem", "entity_type": "protein", "identifier": "1abc"},
    )

    assert response.status_code == 422
