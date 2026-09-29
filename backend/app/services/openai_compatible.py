"""OpenAI-compatible model service helpers."""

from __future__ import annotations

import logging

import httpx

from app.common.secret_crypto import decrypt_secret
from app.models.system_settings import ModelService

logger = logging.getLogger(__name__)


async def list_openai_compatible_models(
    service: ModelService,
    *,
    api_key: str | None = None,
) -> tuple[bool, list[str], str]:
    """Read the provider model catalog without exposing credentials."""
    try:
        key = api_key or decrypt_secret(service.api_key_encrypted) or ""
        headers = {"Accept": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        url = f"{service.base_url.rstrip('/')}/models"
        async with httpx.AsyncClient(timeout=service.timeout_seconds) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning(
            "OpenAI-compatible model discovery failed for service=%s base_url=%s: %s",
            service.name,
            service.base_url,
            exc,
        )
        return False, [], str(exc)

    raw_models = data.get("data") if isinstance(data, dict) else None
    models = sorted(
        {
            str(item.get("id"))
            for item in (raw_models or [])
            if isinstance(item, dict) and item.get("id")
        }
    )
    if not models:
        return False, [], "服务未返回可用模型"
    return True, models, f"已发现 {len(models)} 个模型"


def _extract_chat_completion_content(data: object) -> str:
    """从 OpenAI-compatible 响应中提取首条消息内容。"""
    if not isinstance(data, dict):
        return "响应格式可用，但未返回标准 choices 内容"

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return "响应格式可用，但未返回标准 choices 内容"

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return "响应格式可用，但未返回标准 choices 内容"

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return "响应格式可用，但未返回标准 choices 内容"

    content = message.get("content")
    return str(content or "")


async def test_openai_compatible_service(
    service: ModelService,
    *,
    api_key: str | None = None,
) -> tuple[bool, str]:
    key = api_key or decrypt_secret(service.api_key_encrypted) or ""
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    url = f"{service.base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": service.model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "temperature": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=service.timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning(
            "OpenAI-compatible service test failed for service=%s model=%s base_url=%s: %s",
            service.name,
            service.model_name,
            service.base_url,
            exc,
        )
        return False, str(exc)

    content = _extract_chat_completion_content(data)
    return True, f"模型服务连接成功: {content}".strip()
