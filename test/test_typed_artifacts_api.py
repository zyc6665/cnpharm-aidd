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
        self.presign_calls: list[tuple[str, int]] = []

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

    def open_stream(self, path: str, chunk_size: int = 1024 * 1024):
        data = self.objects[path][0]

        async def _iter():
            for start in range(0, len(data), chunk_size):
                yield data[start : start + chunk_size]

        return _iter()

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        self.presign_calls.append((path, expires_in))
        return f"https://presigned.example/{path}?expires={expires_in}"

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
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.api.v1.artifacts import get_artifact_storage

    # Uploads now persist exactly one local copy via store_file_bytes; keep test
    # bytes inside tmp_path instead of the real storage dir.
    monkeypatch.setattr("app.files.storage_path.STORAGE_PATH", tmp_path)
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
async def test_artifact_upload_stores_single_copy_and_deduplicates_by_sha256(
    artifact_client,
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
):
    from app.models.artifacts import ArtifactVersion
    from app.models.files import File as FileModel

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
    # 只有 store_file_bytes 一条写路径：不再向 storage 双写。
    assert storage.uploads == []
    files = (await artifact_db.execute(select(FileModel))).scalars().all()
    assert len(files) == 1
    version_row = (
        await artifact_db.execute(
            select(ArtifactVersion).where(ArtifactVersion.id == first_data["latest_version"]["id"])
        )
    ).scalar_one()
    assert version_row.storage_key == files[0].storage_path
    assert files[0].filename == "protein.pdb"
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
async def test_project_artifacts_list_is_paginated(
    artifact_client,
    artifact_context: dict[str, object],
):
    client, _ = artifact_client
    project = artifact_context["project"]
    headers = {"Authorization": "Bearer owner"}
    for index in range(3):
        created = await client.post(
            f"/api/v1/projects/{project.id}/artifacts",
            headers=headers,
            data={"artifact_type": "protein_structure", "semantic_type": "protein_structure"},
            files={"file": (f"protein-{index}.pdb", f"HEADER {index}\nEND\n".encode(), "chemical/x-pdb")},
        )
        assert created.status_code == 200

    first_page = await client.get(
        f"/api/v1/projects/{project.id}/artifacts?page=1&page_size=2", headers=headers
    )
    second_page = await client.get(
        f"/api/v1/projects/{project.id}/artifacts?page=2&page_size=2", headers=headers
    )

    assert first_page.status_code == second_page.status_code == 200
    first_data = first_page.json()["data"]
    assert first_data["total"] == 3
    assert first_data["page"] == 1
    assert first_data["page_size"] == 2
    assert len(first_data["items"]) == 2
    second_data = second_page.json()["data"]
    assert second_data["total"] == 3
    assert second_data["page"] == 2
    assert len(second_data["items"]) == 1
    assert {item["id"] for item in first_data["items"]}.isdisjoint(
        {item["id"] for item in second_data["items"]}
    )

    too_large = await client.get(
        f"/api/v1/projects/{project.id}/artifacts?page_size=101", headers=headers
    )
    assert too_large.status_code == 422


@pytest.mark.asyncio
async def test_unknown_standard_type_returns_422_envelope(
    artifact_client,
    artifact_context: dict[str, object],
):
    client, _ = artifact_client
    project = artifact_context["project"]

    response = await client.post(
        f"/api/v1/projects/{project.id}/artifacts",
        headers={"Authorization": "Bearer owner"},
        data={
            "artifact_type": "protein_structure",
            "semantic_type": "protein_structure",
            "standard_type": "mystery_standard",
            "standard_version": "1",
        },
        files={"file": ("protein.pdb", b"HEADER X\nEND\n", "chemical/x-pdb")},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == 422
    assert "Unknown standard artifact type: mystery_standard" in payload["message"]


@pytest.mark.asyncio
async def test_project_artifacts_can_filter_by_delivery_metadata(
    artifact_client,
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
):
    from app.models.artifacts import Artifact, ArtifactVersion

    client, _ = artifact_client
    project = artifact_context["project"]
    owner = artifact_context["owner"]

    matching = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="run_report",
        semantic_type="run_report@1",
        standard_type="run_report",
        standard_version=1,
        name="molp-pc-report",
    )
    other = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="run_report",
        semantic_type="run_report@1",
        standard_type="run_report",
        standard_version=1,
        name="other-report",
    )
    artifact_db.add_all([matching, other])
    await artifact_db.flush()

    matching_version = ArtifactVersion(
        artifact_id=matching.id,
        created_by=owner.id,
        version=1,
        filename="molp-pc-report.json",
        content_type="application/json",
        size_bytes=12,
        sha256="c" * 64,
        storage_key="standard/molp-pc-report.json",
        status="available",
        manifest_json={
            "metadata": {
                "model_name": "MolP-PC",
                "model_version": "MolP-PC 0.1.1",
                "evidence_level": "engineering_smoke_only",
                "endpoint_ref": "local_runtime:molp-pc-property-prediction@0.1.1",
                "applicability_domain_status": "unknown",
            }
        },
    )
    other_version = ArtifactVersion(
        artifact_id=other.id,
        created_by=owner.id,
        version=1,
        filename="other-report.json",
        content_type="application/json",
        size_bytes=12,
        sha256="d" * 64,
        storage_key="standard/other-report.json",
        status="available",
        manifest_json={
            "metadata": {
                "model_name": "OtherModel",
                "model_version": "MolP-PC 0.1.1",
                "evidence_level": "engineering_smoke_only",
                "endpoint_ref": "remote:other-endpoint@1.0",
                "applicability_domain_status": "outside_domain",
            }
        },
    )
    artifact_db.add_all([matching_version, other_version])
    await artifact_db.flush()
    matching.latest_version_id = matching_version.id
    matching.latest_version = matching_version
    other.latest_version_id = other_version.id
    other.latest_version = other_version
    await artifact_db.commit()

    listed = await client.get(
        f"/api/v1/projects/{project.id}/artifacts",
        headers={"Authorization": "Bearer owner"},
        params={
            "metadata_model_version": "MolP-PC 0.1.1",
            "metadata_evidence_level": "engineering_smoke_only",
            "metadata_endpoint_ref": "local_runtime:molp-pc-property-prediction@0.1.1",
            "metadata_applicability_domain_status": "unknown",
        },
    )

    assert listed.status_code == 200
    items = listed.json()["data"]["items"]
    assert [item["name"] for item in items] == ["molp-pc-report"]
    assert items[0]["latest_version"]["manifest_json"]["metadata"]["model_version"] == "MolP-PC 0.1.1"

    listed_by_model_name = await client.get(
        f"/api/v1/projects/{project.id}/artifacts",
        headers={"Authorization": "Bearer owner"},
        params={"metadata_model_name": "MolP-PC"},
    )

    assert listed_by_model_name.status_code == 200
    model_name_items = listed_by_model_name.json()["data"]["items"]
    assert [item["name"] for item in model_name_items] == ["molp-pc-report"]


@pytest.mark.asyncio
async def test_project_artifacts_can_filter_by_type_and_source(
    artifact_client,
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
):
    from app.models.artifacts import Artifact, ArtifactVersion

    client, _ = artifact_client
    project = artifact_context["project"]
    owner = artifact_context["owner"]
    matching = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="molecule_table",
        semantic_type="molecule_table@1",
        standard_type="molecule_table",
        standard_version=1,
        name="rdkit-properties",
        source_task_id="task-rdkit",
    )
    other = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="run_report",
        semantic_type="run_report@1",
        standard_type="run_report",
        standard_version=1,
        name="molp-pc-report",
        source_task_id="task-molp-pc",
    )
    artifact_db.add_all([matching, other])
    await artifact_db.flush()
    matching_version = ArtifactVersion(
        artifact_id=matching.id,
        created_by=owner.id,
        version=1,
        filename="rdkit.csv",
        content_type="text/csv",
        size_bytes=12,
        sha256="e" * 64,
        storage_key="standard/rdkit.csv",
        status="available",
    )
    other_version = ArtifactVersion(
        artifact_id=other.id,
        created_by=owner.id,
        version=1,
        filename="report.json",
        content_type="application/json",
        size_bytes=12,
        sha256="f" * 64,
        storage_key="standard/report.json",
        status="available",
    )
    artifact_db.add_all([matching_version, other_version])
    await artifact_db.flush()
    matching.latest_version_id = matching_version.id
    matching.latest_version = matching_version
    other.latest_version_id = other_version.id
    other.latest_version = other_version
    await artifact_db.commit()

    listed = await client.get(
        f"/api/v1/projects/{project.id}/artifacts",
        headers={"Authorization": "Bearer owner"},
        params={
            "artifact_type": "molecule_table",
            "standard_type": "molecule_table",
            "source_task_id": "task-rdkit",
        },
    )

    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()["data"]["items"]] == [
        "rdkit-properties"
    ]


@pytest.mark.asyncio
async def test_project_artifacts_can_filter_by_latest_version_file_role(
    artifact_client,
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
):
    from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
    from app.models.files import File as FileModel, FileSourceType

    client, _ = artifact_client
    project = artifact_context["project"]
    owner = artifact_context["owner"]
    matching = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="ligand_structure",
        semantic_type="ligand_structure@1",
        standard_type="ligand_structure",
        standard_version=1,
        name="prepared-ligand",
    )
    other = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="ligand_structure",
        semantic_type="ligand_structure@1",
        standard_type="ligand_structure",
        standard_version=1,
        name="raw-ligand",
    )
    artifact_db.add_all([matching, other])
    await artifact_db.flush()
    matching_version = ArtifactVersion(
        artifact_id=matching.id,
        created_by=owner.id,
        version=1,
        filename="prepared.sdf",
        content_type="chemical/x-mdl-sdfile",
        size_bytes=12,
        sha256="1" * 64,
        storage_key="standard/prepared.sdf",
        status="available",
    )
    other_version = ArtifactVersion(
        artifact_id=other.id,
        created_by=owner.id,
        version=1,
        filename="raw.sdf",
        content_type="chemical/x-mdl-sdfile",
        size_bytes=12,
        sha256="2" * 64,
        storage_key="standard/raw.sdf",
        status="available",
    )
    artifact_db.add_all([matching_version, other_version])
    await artifact_db.flush()
    matching.latest_version_id = matching_version.id
    matching.latest_version = matching_version
    other.latest_version_id = other_version.id
    other.latest_version = other_version
    role_file = FileModel(
        project_id=project.id,
        owner_id=owner.id,
        filename="prepared.sdf",
        content_type="chemical/x-mdl-sdfile",
        size_bytes=12,
        sha256="1" * 64,
        storage_path="standard/prepared.sdf",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    raw_file = FileModel(
        project_id=project.id,
        owner_id=owner.id,
        filename="raw.sdf",
        content_type="chemical/x-mdl-sdfile",
        size_bytes=12,
        sha256="2" * 64,
        storage_path="standard/raw.sdf",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    artifact_db.add_all([role_file, raw_file])
    await artifact_db.flush()
    artifact_db.add_all(
        [
            ArtifactVersionFile(
                artifact_version_id=matching_version.id,
                role="structure_3d_sdf",
                file_id=role_file.id,
                is_primary=True,
            ),
            ArtifactVersionFile(
                artifact_version_id=other_version.id,
                role="structure_file",
                file_id=raw_file.id,
                is_primary=True,
            ),
        ]
    )
    await artifact_db.commit()

    listed = await client.get(
        f"/api/v1/projects/{project.id}/artifacts",
        headers={"Authorization": "Bearer owner"},
        params={"file_role": "structure_3d_sdf"},
    )

    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()["data"]["items"]] == [
        "prepared-ligand"
    ]


@pytest.mark.asyncio
async def test_standard_artifact_detail_exposes_role_files_and_downloads_each_role(
    artifact_client,
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
):
    from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
    from app.models.files import File as FileModel, FileSourceType

    client, storage = artifact_client
    project = artifact_context["project"]
    owner = artifact_context["owner"]
    artifact = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="ligand_structure",
        semantic_type="ligand_structure@1",
        standard_type="ligand_structure",
        standard_version=1,
        name="aspirin",
    )
    artifact_db.add(artifact)
    await artifact_db.flush()
    structure_content = b"primary 3d sdf"
    two_d_content = b"2d sdf"
    three_d_content = b"3d sdf"
    storage.objects.update(
        {
            "standard/ligand.sdf": (structure_content, "chemical/x-mdl-sdfile"),
            "standard/ligand.2d.sdf": (two_d_content, "chemical/x-mdl-sdfile"),
            "standard/ligand.3d.sdf": (three_d_content, "chemical/x-mdl-sdfile"),
        }
    )
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename="ligand.sdf",
        content_type="chemical/x-mdl-sdfile",
        size_bytes=len(structure_content),
        sha256=hashlib.sha256(structure_content).hexdigest(),
        storage_key="standard/ligand.sdf",
        status="available",
        manifest_json={
            "type": "run_report@1",
            "metadata": {
                "model_card_ref": "example/MolP-PC/tool-package/docs/model-card.md",
                "verification_record_ref": "example/MolP-PC/tool-package/docs/verification-record.md",
                "evidence_level": "engineering_smoke_only",
            },
        },
    )
    artifact_db.add(version)
    await artifact_db.flush()
    role_files = [
        (
            "structure_file",
            True,
            FileModel(
                project_id=project.id,
                owner_id=owner.id,
                filename="ligand.sdf",
                content_type="chemical/x-mdl-sdfile",
                size_bytes=len(structure_content),
                sha256=hashlib.sha256(structure_content).hexdigest(),
                storage_path="standard/ligand.sdf",
                source_type=FileSourceType.TOOL_OUTPUT.value,
            ),
        ),
        (
            "structure_2d_sdf",
            False,
            FileModel(
                project_id=project.id,
                owner_id=owner.id,
                filename="ligand.2d.sdf",
                content_type="chemical/x-mdl-sdfile",
                size_bytes=len(two_d_content),
                sha256=hashlib.sha256(two_d_content).hexdigest(),
                storage_path="standard/ligand.2d.sdf",
                source_type=FileSourceType.TOOL_OUTPUT.value,
            ),
        ),
        (
            "structure_3d_sdf",
            False,
            FileModel(
                project_id=project.id,
                owner_id=owner.id,
                filename="ligand.3d.sdf",
                content_type="chemical/x-mdl-sdfile",
                size_bytes=len(three_d_content),
                sha256=hashlib.sha256(three_d_content).hexdigest(),
                storage_path="standard/ligand.3d.sdf",
                source_type=FileSourceType.TOOL_OUTPUT.value,
            ),
        ),
    ]
    for sort_order, (role, is_primary, file_record) in enumerate(role_files):
        artifact_db.add(file_record)
        await artifact_db.flush()
        artifact_db.add(
            ArtifactVersionFile(
                artifact_version_id=version.id,
                role=role,
                file_id=file_record.id,
                is_primary=is_primary,
                sort_order=sort_order,
            )
        )
    artifact.latest_version_id = version.id
    artifact.latest_version = version
    await artifact_db.commit()

    detail = await client.get(
        f"/api/v1/artifacts/{artifact.id}", headers={"Authorization": "Bearer owner"}
    )

    assert detail.status_code == 200
    latest_version = detail.json()["data"]["latest_version"]
    assert latest_version["manifest_json"]["metadata"] == {
        "model_card_ref": "example/MolP-PC/tool-package/docs/model-card.md",
        "verification_record_ref": "example/MolP-PC/tool-package/docs/verification-record.md",
        "evidence_level": "engineering_smoke_only",
    }
    latest_files = latest_version["files"]
    assert [item["role"] for item in latest_files] == [
        "structure_file",
        "structure_2d_sdf",
        "structure_3d_sdf",
    ]
    three_d = next(item for item in latest_files if item["role"] == "structure_3d_sdf")
    assert three_d["is_primary"] is False
    assert three_d["download_url"] == (
        f"/api/v1/artifacts/{artifact.id}/versions/{version.id}/files/structure_3d_sdf/download"
    )

    downloaded = await client.get(
        three_d["download_url"], headers={"Authorization": "Bearer owner"}
    )

    assert downloaded.status_code == 200
    assert downloaded.content == three_d_content
    assert "ligand.3d.sdf" in downloaded.headers["content-disposition"]


@pytest.mark.asyncio
async def test_project_artifact_lineage_graph_includes_versions_tasks_and_workflow_nodes(
    artifact_client,
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
):
    from app.models.artifacts import Artifact, ArtifactLineage, ArtifactVersion
    from app.models.tasks import Task, TaskInput, TaskStatus
    from app.models.tools import Tool, ToolStatus, ToolVersion

    client, _ = artifact_client
    project = artifact_context["project"]
    owner = artifact_context["owner"]
    tool = Tool(
        owner_id=owner.id,
        name="LVpocket",
        slug="lvpocket-pocket-prediction",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    artifact_db.add(tool)
    await artifact_db.flush()
    tool_version = ToolVersion(tool_id=tool.id, version="1.0.0", config={"type": "ssh_job"})
    artifact_db.add(tool_version)
    await artifact_db.flush()
    tool.current_version_id = tool_version.id
    task = Task(
        user_id=owner.id,
        tool_id=tool.id,
        tool_version_id=tool_version.id,
        name="Workflow Pocket Node",
        status=TaskStatus.SUCCESS.value,
        extra_data={"project_id": project.id},
    )
    artifact_db.add(task)
    await artifact_db.flush()
    artifact_db.add(
        TaskInput(
            task_id=task.id,
            params={
                "workflow_run_id": "run-1",
                "workflow_definition_id": "workflow-1",
                "workflow_node_id": "pocket_prediction",
                "workflow_node_type": "tool",
            },
            file_ids=[],
        )
    )
    source = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure@1",
        standard_type="protein_structure",
        standard_version=1,
        name="protein.pdb",
    )
    output = Artifact(
        project_id=project.id,
        created_by=owner.id,
        artifact_type="binding_pocket",
        semantic_type="binding_pocket@1",
        standard_type="binding_pocket",
        standard_version=1,
        name="pocket.pdb",
        source_task_id=task.id,
    )
    artifact_db.add_all([source, output])
    await artifact_db.flush()
    source_version = ArtifactVersion(
        artifact_id=source.id,
        created_by=owner.id,
        version=1,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=12,
        sha256="a" * 64,
        storage_key="standard/protein.pdb",
        status="available",
    )
    output_version = ArtifactVersion(
        artifact_id=output.id,
        created_by=owner.id,
        version=1,
        filename="pocket.pdb",
        content_type="chemical/x-pdb",
        size_bytes=16,
        sha256="b" * 64,
        storage_key="standard/pocket.pdb",
        status="available",
    )
    artifact_db.add_all([source_version, output_version])
    await artifact_db.flush()
    source.latest_version_id = source_version.id
    output.latest_version_id = output_version.id
    artifact_db.add(
        ArtifactLineage(
            project_id=project.id,
            input_version_id=source_version.id,
            output_version_id=output_version.id,
            created_by=owner.id,
            relation_type="derived_from",
        )
    )
    await artifact_db.commit()

    graph_response = await client.get(
        f"/api/v1/projects/{project.id}/artifact-lineage",
        headers={"Authorization": "Bearer owner"},
    )
    hidden_response = await client.get(
        f"/api/v1/projects/{project.id}/artifact-lineage",
        headers={"Authorization": "Bearer outsider"},
    )

    assert graph_response.status_code == 200
    graph = graph_response.json()["data"]
    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    edge_keys = {
        (edge["source"], edge["target"], edge["kind"])
        for edge in graph["edges"]
    }
    assert nodes_by_id[f"artifact:{output.id}"]["standard_type"] == "binding_pocket"
    assert nodes_by_id[f"version:{output_version.id}"]["filename"] == "pocket.pdb"
    assert nodes_by_id[f"task:{task.id}"]["tool_slug"] == tool.slug
    assert nodes_by_id["workflow-node:run-1:pocket_prediction"]["workflow_node_id"] == (
        "pocket_prediction"
    )
    assert (
        f"version:{source_version.id}",
        f"version:{output_version.id}",
        "derived_from",
    ) in edge_keys
    assert (f"task:{task.id}", f"version:{output_version.id}", "produced_by") in edge_keys
    assert (
        "workflow-node:run-1:pocket_prediction",
        f"task:{task.id}",
        "runs_task",
    ) in edge_keys
    assert graph["summary"]["artifacts"] == 2
    assert graph["summary"]["lineage_edges"] == 1
    assert hidden_response.status_code == 404


@pytest.mark.asyncio
async def test_artifact_version_download_presigns_large_and_trajectory_files(
    artifact_client,
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
):
    from app.models.artifacts import ArtifactVersion

    client, storage = artifact_client
    project = artifact_context["project"]

    async def upload(name: str, content: bytes) -> dict[str, object]:
        response = await client.post(
            f"/api/v1/projects/{project.id}/artifacts",
            headers={"Authorization": "Bearer owner"},
            data={"artifact_type": "protein_structure", "semantic_type": "protein_structure"},
            files={"file": (name, content, "application/octet-stream")},
        )
        assert response.status_code == 200
        return response.json()["data"]

    async def version_row(artifact: dict[str, object]) -> ArtifactVersion:
        return (
            await artifact_db.execute(
                select(ArtifactVersion).where(
                    ArtifactVersion.id == artifact["latest_version"]["id"]
                )
            )
        ).scalar_one()

    large = await upload("large.pdb", b"HEADER LARGE\nEND\n")
    large_row = await version_row(large)
    large_row.size_bytes = 100 * 1024 * 1024 + 1
    await artifact_db.flush()
    large_response = await client.get(
        f"/api/v1/artifacts/{large['id']}/versions/{large['latest_version']['id']}/download",
        headers={"Authorization": "Bearer owner"},
    )
    assert large_response.status_code == 302
    from urllib.parse import unquote

    assert unquote(large_response.headers["location"]) == (
        f"https://presigned.example/{large_row.storage_key}?expires=900"
    )

    trajectory = await upload("trajectory.dcd", b"trajectory-bytes")
    trajectory_row = await version_row(trajectory)
    trajectory_response = await client.get(
        f"/api/v1/artifacts/{trajectory['id']}/versions/{trajectory['latest_version']['id']}/download",
        headers={"Authorization": "Bearer owner"},
    )
    assert trajectory_response.status_code == 302
    assert (trajectory_row.storage_key, 900) in storage.presign_calls


@pytest.mark.asyncio
async def test_artifact_version_download_streams_from_storage_and_checks_acl(
    artifact_client,
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
):
    from app.api.v1 import artifacts as artifacts_api
    from app.logging.audit import AuditAction, AuditResult
    from app.models.artifacts import ArtifactVersion

    client, storage = artifact_client
    project = artifact_context["project"]
    audit_events: list[dict[str, object]] = []

    class AuditRecorder:
        def log_file_operation(self, **kwargs):
            audit_events.append(kwargs)

    monkeypatch.setattr(
        artifacts_api,
        "get_audit_logger",
        lambda: AuditRecorder(),
        raising=False,
    )
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
    version_row = (
        await artifact_db.execute(
            select(ArtifactVersion).where(ArtifactVersion.id == version["id"])
        )
    ).scalar_one()
    # The upload wrote a local file; expose the same bytes through the injected
    # storage double so the download endpoint exercises its real streaming path.
    storage.objects[version_row.storage_key] = (content, "chemical/x-pdb")

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
    assert audit_events == [
        {
            "user_id": artifact_context["owner"].id,
            "action": AuditAction.FILE_DOWNLOAD,
            "file_id": version["id"],
            "file_name": "protein.pdb",
            "result": AuditResult.SUCCESS,
            "file_size": len(content),
            "project_id": project.id,
            "artifact_id": artifact["id"],
            "artifact_version_id": version["id"],
            "role": "primary",
        },
        {
            "user_id": artifact_context["outsider"].id,
            "action": AuditAction.FILE_DOWNLOAD,
            "file_id": version["id"],
            "file_name": "protein.pdb",
            "result": AuditResult.DENIED,
            "file_size": len(content),
            "project_id": project.id,
            "artifact_id": artifact["id"],
            "artifact_version_id": version["id"],
            "role": "primary",
            "reason": "project_access_denied",
        }
    ]
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_storage_failure_leaves_no_artifact_metadata(
    artifact_db: AsyncSession,
    artifact_context: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
):
    from app.models.artifacts import Artifact, ArtifactVersion
    from app.services.artifacts import create_artifact

    async def failing_store(*args, **kwargs):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr("app.services.artifacts.store_file_bytes", failing_store)

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await create_artifact(
            artifact_db,
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
