"""Admin APIs for static tool templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.tool_route_utils import create_or_update_tool_from_import
from app.auth.dependencies import get_admin_user
from app.common.exceptions import ValidationException
from app.common.responses import success_response
from app.database.session import get_db
from app.models.users import User
from app.schemas.tool_templates import (
    ToolTemplateDraftCreate,
    ToolTemplateSummaryResponse,
)
from app.schemas.tools import ToolImportRequest
from app.tool_templates.loader import (
    ToolTemplateLoadError,
    build_tool_import_config_from_template,
    load_tool_template,
    load_tool_templates,
)
from app.tool_templates.schemas import DrugDiscoveryToolTemplate


router = APIRouter()


@router.get("", response_model=dict)
async def list_tool_templates(
    current_user: User = Depends(get_admin_user),
) -> dict:
    """List static drug-discovery tool templates for admin registration."""
    _ = current_user
    templates = load_tool_templates("drug_discovery")
    return success_response(
        data=[_template_summary(template) for template in templates],
        message="工具模板列表获取成功",
    )


@router.post("/{template_key}/draft", response_model=dict)
async def create_tool_draft_from_template(
    template_key: str,
    request: ToolTemplateDraftCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a Tool draft from a static template and executor config."""
    try:
        template = load_tool_template(template_key)
        config = build_tool_import_config_from_template(
            template,
            executor_type=request.executor_type,
            executor_config=request.executor_config,
        )
    except ToolTemplateLoadError as exc:
        raise ValidationException(str(exc)) from exc

    result = await create_or_update_tool_from_import(
        db,
        current_user,
        ToolImportRequest(
            config=config,
            category_id=request.category_id,
            publish=request.publish,
        ),
    )
    return success_response(data=result, message="工具模板草稿创建成功")


def _template_summary(template: DrugDiscoveryToolTemplate) -> dict:
    payload = ToolTemplateSummaryResponse(
        template_key=template.metadata.template_key,
        slug=template.metadata.slug,
        name=template.metadata.name,
        version=template.metadata.version,
        description=template.metadata.description,
        family=template.metadata.family,
        executor_types=list(template.executor_types),
        capability=template.agent_capability.capability,
        stage=template.agent_capability.stage,
        inputs=[item.model_dump(mode="json") for item in template.agent_capability.inputs],
        outputs=[item.model_dump(mode="json") for item in template.agent_capability.outputs],
        implementation=template.implementation.model_dump(mode="json"),
        resource_profile=template.resource_profile.model_dump(mode="json"),
    )
    return payload.model_dump()
