"""External scientific database import APIs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.database.session import get_db
from app.external_databases.imports import (
    ExternalDatabaseImportError,
    persist_external_database_payload,
)
from app.external_databases.providers import (
    ExternalDatabaseProvider,
    ExternalDatabaseProviderError,
    default_external_database_providers,
)
from app.models.users import User
from app.schemas.external_databases import ExternalDatabaseImportRequest
from app.services.artifact_responses import artifact_data
from app.services.project_access import require_project_role
from app.storage.factory import get_storage_backend


router = APIRouter()


def get_external_database_storage():
    return get_storage_backend()


def get_external_database_providers() -> dict[str, ExternalDatabaseProvider]:
    return default_external_database_providers()


@router.get("/external-databases/sources", response_model=dict)
async def list_external_database_sources():
    return success_response(
        data={
            "sources": [
                {
                    "id": "pubchem",
                    "name": "PubChem",
                    "entity_types": ["ligand"],
                    "identifier_label": "CID",
                },
                {
                    "id": "rcsb",
                    "name": "RCSB PDB",
                    "entity_types": ["protein"],
                    "identifier_label": "PDB ID",
                },
            ]
        }
    )


@router.post("/projects/{project_id}/external-databases/import", response_model=dict)
async def import_external_database_artifact(
    project_id: str,
    data: ExternalDatabaseImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage=Depends(get_external_database_storage),
    providers: dict[str, ExternalDatabaseProvider] = Depends(get_external_database_providers),
):
    project, _ = await require_project_role(
        db,
        project_id=project_id,
        user=current_user,
        allowed_roles={"owner", "editor"},
    )
    provider = providers.get(data.source)
    if provider is None:
        raise HTTPException(status_code=400, detail="不支持的外部数据库来源")
    try:
        if data.entity_type == "ligand":
            payload = await provider.fetch_ligand(data.identifier)
        else:
            payload = await provider.fetch_protein(data.identifier)
        result = await persist_external_database_payload(
            db,
            storage=storage,
            project=project,
            user=current_user,
            source=data.source,
            identifier=data.identifier,
            payload=payload,
            board_id=data.board_id,
            position=data.position.model_dump() if data.position else None,
        )
    except (ExternalDatabaseProviderError, ExternalDatabaseImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return success_response(
        data={
            "artifact": artifact_data(result.artifact, include_versions=True),
            "board_node": result.board_node,
        },
        message="外部数据库记录已导入",
    )
