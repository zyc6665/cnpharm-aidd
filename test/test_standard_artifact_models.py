"""Standard multi-file Artifact ORM model tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models import files as _files_models  # noqa: F401
from app.models import artifacts as _artifacts_models  # noqa: F401
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.files import File as FileModel, FileSourceType


@pytest.mark.asyncio
async def test_standard_artifact_version_can_reference_multiple_file_roles():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        artifact = Artifact(
            project_id="project-1",
            created_by="user-1",
            artifact_type="binding_pocket",
            semantic_type="binding_pocket",
            standard_type="binding_pocket",
            standard_version=1,
            source_task_id="task-1",
            name="Top pocket",
        )
        session.add(artifact)
        await session.flush()
        version = ArtifactVersion(
            artifact_id=artifact.id,
            created_by="user-1",
            version=1,
            filename="manifest.json",
            content_type="application/json",
            size_bytes=2,
            sha256="0" * 64,
            storage_key="legacy/manifest.json",
            validation_status="passed",
            validation_errors=[],
            manifest_json={"type": "binding_pocket@1"},
            summary_json={"pocket_count": 1},
            metrics_json={"score": 0.91},
        )
        session.add(version)
        await session.flush()
        files = [
            FileModel(
                filename="residue.pdb",
                content_type="chemical/x-pdb",
                size_bytes=7,
                sha256="1" * 64,
                storage_path="/tmp/residue.pdb",
                source_type=FileSourceType.TOOL_OUTPUT.value,
            ),
            FileModel(
                filename="atom.pdb",
                content_type="chemical/x-pdb",
                size_bytes=4,
                sha256="2" * 64,
                storage_path="/tmp/atom.pdb",
                source_type=FileSourceType.TOOL_OUTPUT.value,
            ),
        ]
        session.add_all(files)
        await session.flush()
        session.add_all(
            [
                ArtifactVersionFile(
                    artifact_version_id=version.id,
                    role="residue_pocket_pdb",
                    file_id=files[0].id,
                    is_primary=True,
                    sort_order=0,
                ),
                ArtifactVersionFile(
                    artifact_version_id=version.id,
                    role="atom_pocket_pdb",
                    file_id=files[1].id,
                    is_primary=False,
                    sort_order=1,
                ),
            ]
        )
        artifact.latest_version_id = version.id
        await session.commit()

        loaded = (
            await session.execute(
                select(ArtifactVersion)
                .options(selectinload(ArtifactVersion.files))
                .where(ArtifactVersion.id == version.id)
            )
        ).scalar_one()

        assert loaded.validation_status == "passed"
        assert loaded.manifest_json == {"type": "binding_pocket@1"}
        assert [item.role for item in loaded.files] == [
            "residue_pocket_pdb",
            "atom_pocket_pdb",
        ]
        assert loaded.files[0].is_primary is True

    await engine.dispose()
