"""OpenAI-compatible model service helpers."""

from __future__ import annotations

import httpx

from app.common.secret_crypto import decrypt_secret
from app.models.system_settings import ModelService


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
        return False, str(exc)

    content = ""
    try:
        content = str(data["choices"][0]["message"].get("content") or "")
    except Exception:
        content = "响应格式可用，但未返回标准 choices 内容"

    return True, f"模型服务连接成功: {content}".strip()
