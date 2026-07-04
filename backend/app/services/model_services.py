"""Model service settings service layer."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.common.exceptions import NotFoundException, ValidationException
from app.common.secret_crypto import decrypt_secret, encrypt_secret, mask_secret
from app.models.system_settings import ModelService
from app.schemas.system_settings import (
    ModelServiceCreate,
    ModelServiceResponse,
    ModelServiceTestResponse,
    ModelServiceUpdate,
)


def serialize_model_service(service: ModelService) -> ModelServiceResponse:
    decrypted = decrypt_secret(service.api_key_encrypted)
    return ModelServiceResponse(
        id=service.id,
        name=service.name,
        provider_type=service.provider_type,
        base_url=service.base_url,
        model_name=service.model_name,
        is_default=bool(service.is_default),
        is_enabled=bool(service.is_enabled),
        timeout_seconds=service.timeout_seconds,
        max_tokens=service.max_tokens,
        temperature=service.temperature,
        has_api_key=bool(decrypted),
        api_key_masked=mask_secret(decrypted),
        last_test_status=service.last_test_status,
        last_test_message=service.last_test_message,
        last_tested_at=service.last_tested_at,
        created_at=service.created_at,
        updated_at=service.updated_at,
    )


async def _load_model_service(db: AsyncSession, service_id: str) -> ModelService:
    service = await db.get(ModelService, service_id)
    if not service:
        raise NotFoundException("模型服务不存在")
    return service


async def _clear_default_services(db: AsyncSession) -> None:
    result = await db.execute(select(ModelService).where(ModelService.is_default.is_(True)))
    for service in result.scalars().all():
        service.is_default = False


async def list_model_services(db: AsyncSession) -> list[ModelServiceResponse]:
    result = await db.execute(
        select(ModelService).order_by(
            ModelService.is_default.desc(),
            ModelService.created_at.desc(),
            ModelService.name.asc(),
        )
    )
    return [serialize_model_service(service) for service in result.scalars().all()]


async def create_model_service(
    db: AsyncSession,
    data: ModelServiceCreate,
) -> ModelServiceResponse:
    if data.is_default:
        await _clear_default_services(db)

    service = ModelService(
        name=data.name,
        provider_type=data.provider_type,
        base_url=data.base_url.rstrip("/"),
        api_key_encrypted=encrypt_secret(data.api_key),
        model_name=data.model_name,
        is_default=data.is_default,
        is_enabled=data.is_enabled,
        timeout_seconds=data.timeout_seconds,
        max_tokens=data.max_tokens,
        temperature=data.temperature,
    )
    db.add(service)
    await db.flush()
    await db.refresh(service)
    return serialize_model_service(service)


async def update_model_service(
    db: AsyncSession,
    service_id: str,
    data: ModelServiceUpdate,
) -> ModelServiceResponse:
    service = await _load_model_service(db, service_id)
    update_data = data.model_dump(exclude_unset=True)

    if update_data.get("is_default") is True:
        await _clear_default_services(db)

    for key, value in update_data.items():
        if key == "api_key":
            if value:
                service.api_key_encrypted = encrypt_secret(value)
            continue
        if key == "base_url" and isinstance(value, str):
            value = value.rstrip("/")
        setattr(service, key, value)

    await db.flush()
    await db.refresh(service)
    return serialize_model_service(service)


async def delete_model_service(db: AsyncSession, service_id: str) -> None:
    service = await _load_model_service(db, service_id)
    await db.delete(service)
    await db.flush()


async def set_default_model_service(
    db: AsyncSession,
    service_id: str,
) -> ModelServiceResponse:
    service = await _load_model_service(db, service_id)
    if not service.is_enabled:
        raise ValidationException("不能将已禁用的模型服务设为默认")

    await _clear_default_services(db)
    service.is_default = True
    await db.flush()
    await db.refresh(service)
    return serialize_model_service(service)


async def get_default_model_service(db: AsyncSession) -> ModelService:
    result = await db.execute(
        select(ModelService)
        .where(ModelService.is_default.is_(True), ModelService.is_enabled.is_(True))
        .order_by(ModelService.created_at.desc())
        .limit(1)
    )
    service = result.scalar_one_or_none()
    if not service:
        raise ValidationException("请先在管理员后台配置默认模型服务")
    return service


async def test_model_service(
    db: AsyncSession,
    service_id: str,
) -> ModelServiceTestResponse:
    from app.services.openai_compatible import test_openai_compatible_service

    service = await _load_model_service(db, service_id)
    if service.provider_type != "openai_compatible":
        raise ValidationException(f"不支持的模型服务类型: {service.provider_type}")

    success, message = await test_openai_compatible_service(service)
    service.last_test_status = "success" if success else "failure"
    service.last_test_message = message
    service.last_tested_at = utcnow()
    await db.flush()
    await db.refresh(service)

    return ModelServiceTestResponse(
        id=service.id,
        success=success,
        message=message,
        last_test_status=service.last_test_status,
        last_tested_at=service.last_tested_at,
    )
