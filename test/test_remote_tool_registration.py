"""Remote tool self-registration discovery tests."""

from __future__ import annotations

import httpx
import pytest

from app.remote_tools.client import RemoteToolDiscoveryClient


def valid_remote_tool_manifest() -> dict:
    return {
        "api_version": "aidd.sciminer/remote-tool.v1",
        "kind": "RemoteTool",
        "metadata": {
            "slug": "lvpocket-api",
            "name": "LVpocket API",
            "version": "1.0.0",
            "description": "Pocket prediction service",
        },
        "artifacts": {
            "inputs": [
                {"name": "protein", "type": "protein_structure@1", "required": True}
            ],
            "outputs": [
                {
                    "name": "pocket",
                    "type": "binding_pocket@1",
                    "cardinality": "one",
                    "required": True,
                }
            ],
        },
        "parameters_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "endpoints": {
            "invoke": "/invoke",
            "status": "/runs/{remote_run_id}",
            "logs": "/runs/{remote_run_id}/logs",
            "cancel": "/runs/{remote_run_id}/cancel",
            "artifacts": "/runs/{remote_run_id}/artifacts",
            "examples": "/examples",
            "health": "/health",
        },
        "capabilities": {"async": True, "logs": True, "cancel": True, "progress": True},
    }


@pytest.mark.asyncio
async def test_remote_tool_client_discovers_manifest_health_and_examples():
    seen_paths: list[str] = []
    seen_request_ids: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        seen_request_ids.append(request.headers.get("X-Sciminer-Request-Id"))
        if request.url.path == "/.well-known/sciminer-tool.json":
            return httpx.Response(200, json=valid_remote_tool_manifest())
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "healthy"})
        if request.url.path == "/examples":
            return httpx.Response(
                200,
                json={
                    "examples": [
                        {
                            "name": "default",
                            "smoke": True,
                            "parameters": {},
                            "input_artifacts": {},
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = RemoteToolDiscoveryClient(
        "https://model.example.com/",
        transport=httpx.MockTransport(handler),
    )

    result = await client.discover()

    assert result.manifest is not None
    assert result.manifest.metadata.slug == "lvpocket-api"
    assert result.health == {"status": "healthy"}
    assert result.examples is not None
    assert result.examples.examples[0].name == "default"
    assert seen_paths == ["/.well-known/sciminer-tool.json", "/health", "/examples"]
    assert all(seen_request_ids)
    assert [(stage.name, stage.status) for stage in result.stages] == [
        ("fetch_manifest", "success"),
        ("validate_manifest", "success"),
        ("health_check", "success"),
        ("fetch_examples", "success"),
    ]


@pytest.mark.asyncio
async def test_remote_tool_client_returns_diagnostics_when_manifest_fetch_fails():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "warming up"})

    client = RemoteToolDiscoveryClient(
        "https://model.example.com",
        transport=httpx.MockTransport(handler),
    )

    result = await client.discover()

    assert result.manifest is None
    assert [(stage.name, stage.status) for stage in result.stages] == [
        ("fetch_manifest", "failure")
    ]
    assert "503" in result.stages[0].message


@pytest.mark.asyncio
async def test_remote_tool_client_keeps_draft_diagnostics_when_health_fails():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/sciminer-tool.json":
            return httpx.Response(200, json=valid_remote_tool_manifest())
        if request.url.path == "/health":
            return httpx.Response(500, json={"status": "failed"})
        if request.url.path == "/examples":
            return httpx.Response(200, json={"examples": []})
        return httpx.Response(404)

    client = RemoteToolDiscoveryClient(
        "https://model.example.com",
        transport=httpx.MockTransport(handler),
    )

    result = await client.discover()

    assert result.manifest is not None
    assert [(stage.name, stage.status) for stage in result.stages] == [
        ("fetch_manifest", "success"),
        ("validate_manifest", "success"),
        ("health_check", "failure"),
        ("fetch_examples", "success"),
    ]
    assert "500" in result.stages[2].message
