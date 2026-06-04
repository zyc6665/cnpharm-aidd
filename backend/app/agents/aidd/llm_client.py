"""LLM client helpers for AIDD graph planning."""

from __future__ import annotations

import httpx

from app.common.secret_crypto import decrypt_secret
from app.models.system_settings import ModelService


async def request_structured_plan(service: ModelService, prompt: str) -> str:
    api_key = decrypt_secret(service.api_key_encrypted) or ""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": service.model_name,
        "messages": [
            {
                "role": "system",
                "content": "You are a strict JSON planner for scientific AIDD tools.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": service.max_tokens,
        "temperature": service.temperature,
    }

    async with httpx.AsyncClient(timeout=service.timeout_seconds) as client:
        response = await client.post(
            f"{service.base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

    return str(data["choices"][0]["message"]["content"])
