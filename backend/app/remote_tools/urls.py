"""Remote tool URL helpers."""

from __future__ import annotations

from typing import Any


class RemoteToolUrlError(ValueError):
    """Remote tool URL cannot be resolved from config."""


def remote_endpoint_url(
    config: dict[str, Any],
    endpoint_name: str,
    *,
    remote_run_id: str | None = None,
) -> str:
    base_url = str(config.get("base_url") or "").rstrip("/")
    if not base_url:
        raise RemoteToolUrlError("Missing base_url in remote_tool_v1 config")

    endpoints = config.get("endpoints") or {}
    path = endpoints.get(endpoint_name)
    if not isinstance(path, str) or not path.startswith("/"):
        raise RemoteToolUrlError(
            f"Missing endpoint path for remote tool endpoint: {endpoint_name}"
        )
    if remote_run_id is not None:
        path = path.replace("{remote_run_id}", remote_run_id)
    return f"{base_url}{path}"


def remote_result_url(base_url: str, url: str) -> str:
    if url.startswith("/"):
        return f"{base_url.rstrip('/')}{url}"
    return url
