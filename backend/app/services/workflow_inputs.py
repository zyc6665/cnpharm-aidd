"""Workflow input file validation helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.common.time import utcnow
from app.models.artifacts import Artifact, ArtifactVersion, ArtifactVersionFile
from app.models.files import File as FileModel
from app.models.users import User
from app.files.file_records import is_file_usable
from app.services.semantic_types import normalize_semantic_type


WORKFLOW_ARTIFACT_VERSION_PREFIX = "artifact_version:"
WORKFLOW_INPUT_TYPE_ALIASES = {
    "protein_pdb": "protein_structure@1",
    "protein_structure": "protein_structure@1",
    "pocket_pdb": "binding_pocket@1",
    "pocket_structure": "binding_pocket@1",
    "generated_ligand": "ligand_structure@1",
    "ligand_pdb": "ligand_structure@1",
    "smiles_csv": "molecule_table@1",
    "ranking_csv": "molecule_table@1",
    "binding_pocket": "binding_pocket@1",
    "ligand_structure": "ligand_structure@1",
    "molecule_table": "molecule_table@1",
    "run_report": "run_report@1",
}


async def validate_input_files(
    db: AsyncSession,
    *,
    current_user: User,
    input_files: dict[str, str],
    project_id: str | None,
) -> dict[str, str]:
    normalized = {
        normalize_semantic_type(str(semantic_type)): str(file_id)
        for semantic_type, file_id in input_files.items()
        if file_id
    }
    for semantic_type, file_id in normalized.items():
        if file_id.startswith(WORKFLOW_ARTIFACT_VERSION_PREFIX):
            version_id = file_id[len(WORKFLOW_ARTIFACT_VERSION_PREFIX):]
            version = await load_project_artifact_version(
                db,
                version_id=version_id,
                project_id=project_id,
            )
            if version.status != "available":
                raise ValidationException(f"Workflow input ArtifactVersion is not available: {semantic_type}")
            if version.expires_at is not None and version.expires_at <= utcnow():
                raise ValidationException(f"Workflow input ArtifactVersion has expired: {semantic_type}")
            if not artifact_matches_workflow_input_type(version, semantic_type):
                raise ValidationException(f"Workflow input ArtifactVersion type does not match: {semantic_type}")
            normalized[semantic_type] = file_id
            continue

        file_record = await db.get(FileModel, file_id)
        if not file_record:
            raise NotFoundException(f"Workflow input file not found: {semantic_type}")
        if not is_file_usable(file_record):
            raise NotFoundException(f"Workflow input file not found: {semantic_type}")
        if file_record.owner_id != current_user.id and current_user.role != "admin":
            raise ForbiddenException(f"No permission to use workflow input file: {semantic_type}")
    return normalized


async def load_project_artifact_version(
    db: AsyncSession,
    *,
    version_id: str,
    project_id: str | None,
) -> ArtifactVersion:
    if not project_id or not version_id:
        raise NotFoundException("Workflow input ArtifactVersion not found")
    result = await db.execute(
        select(ArtifactVersion)
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
        .options(
            selectinload(ArtifactVersion.artifact),
            selectinload(ArtifactVersion.files).selectinload(ArtifactVersionFile.file),
        )
        .where(ArtifactVersion.id == version_id, Artifact.project_id == project_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise NotFoundException("Workflow input ArtifactVersion not found")
    return version


def artifact_matches_workflow_input_type(version: ArtifactVersion, expected: str) -> bool:
    artifact = version.artifact
    if artifact is None:
        return False
    expected_values = {
        expected,
        normalize_semantic_type(expected),
        _canonical_workflow_type(expected),
    }
    actual_values = {
        str(artifact.semantic_type or ""),
        normalize_semantic_type(str(artifact.semantic_type or "")),
        _canonical_workflow_type(str(artifact.semantic_type or "")),
    }
    if artifact.standard_type and artifact.standard_version:
        standard_ref = f"{artifact.standard_type}@{artifact.standard_version}"
        actual_values.add(standard_ref)
        actual_values.add(normalize_semantic_type(str(artifact.standard_type)))
        actual_values.add(_canonical_workflow_type(str(artifact.standard_type)))
    return bool(expected_values & actual_values)


def _canonical_workflow_type(value: str) -> str:
    normalized = str(value or "").strip()
    return WORKFLOW_INPUT_TYPE_ALIASES.get(normalized, normalize_semantic_type(normalized))
