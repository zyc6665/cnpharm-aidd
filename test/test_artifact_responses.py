from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.artifacts import (  # noqa: E402
    Artifact,
    ArtifactVersion,
    ArtifactVersionFile,
)
from app.models.files import File as FileModel  # noqa: E402
from app.services.artifact_responses import (  # noqa: E402
    artifact_data,
    content_disposition,
    matches_delivery_metadata,
)


def _artifact_with_manifest_metadata(metadata: dict) -> Artifact:
    artifact = Artifact(
        id="artifact-1",
        project_id="project-1",
        created_by="user-1",
        artifact_type="run_report",
        semantic_type="run_report@1",
        standard_type="run_report",
        standard_version=1,
        name="report.json",
    )
    version = ArtifactVersion(
        id="version-1",
        artifact_id=artifact.id,
        created_by="user-1",
        version=1,
        filename="report.json",
        content_type="application/json",
        size_bytes=12,
        sha256="a" * 64,
        storage_key="standard/report.json",
        status="available",
        manifest_json={"metadata": metadata},
    )
    artifact.latest_version = version
    artifact.latest_version_id = version.id
    return artifact


def test_artifact_data_includes_role_file_download_urls() -> None:
    artifact = _artifact_with_manifest_metadata({})
    file_record = FileModel(
        id="file-1",
        filename="ligand.3d.sdf",
        content_type="chemical/x-mdl-sdfile",
        size_bytes=42,
        sha256="b" * 64,
        storage_path="standard/ligand.3d.sdf",
    )
    artifact.latest_version.files = [
        ArtifactVersionFile(
            id="link-1",
            artifact_version_id=artifact.latest_version.id,
            role="structure_3d_sdf",
            file_id=file_record.id,
            file=file_record,
            is_primary=False,
            sort_order=1,
        )
    ]

    data = artifact_data(artifact)

    role_file = data["latest_version"]["files"][0]
    assert role_file["role"] == "structure_3d_sdf"
    assert role_file["download_url"] == (
        "/api/v1/artifacts/artifact-1/versions/version-1"
        "/files/structure_3d_sdf/download"
    )


def test_matches_delivery_metadata_reads_latest_version_manifest() -> None:
    artifact = _artifact_with_manifest_metadata(
        {
            "model_name": "MolP-PC",
            "model_version": "0.1.1",
            "evidence_level": "engineering_smoke_only",
            "endpoint_ref": "local:molp-pc@0.1.1",
            "applicability_domain_status": "unknown",
        }
    )

    assert matches_delivery_metadata(
        artifact,
        model_name="MolP-PC",
        model_version="0.1.1",
        evidence_level="engineering_smoke_only",
        endpoint_ref="local:molp-pc@0.1.1",
        applicability_domain_status="unknown",
    ) is True
    assert matches_delivery_metadata(
        artifact,
        model_name="OtherModel",
        model_version=None,
        evidence_level=None,
        endpoint_ref=None,
        applicability_domain_status=None,
    ) is False


def test_content_disposition_quotes_safe_ascii_and_encodes_utf8() -> None:
    value = content_disposition('ligand "3d".sdf')

    assert 'filename="ligand 3d.sdf"' in value
    assert "filename*=UTF-8''ligand%20%223d%22.sdf" in value
