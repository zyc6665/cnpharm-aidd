"""Remote tool self-registration discovery tests."""

from __future__ import annotations

import httpx
import pytest

from app.remote_tools.client import RemoteToolDiscoveryClient, RemoteToolDiscoveryResult
from app.remote_tools.diagnostics import RemoteToolStageDiagnostic
from app.remote_tools.registration import (
    remote_manifest_sha256,
    remote_tool_config,
    remote_tool_publish_errors,
)


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


def test_remote_manifest_sha256_is_stable_for_key_order() -> None:
    first = {"metadata": {"slug": "demo", "version": "1.0.0"}, "z": [2, 1]}
    second = {"z": [2, 1], "metadata": {"version": "1.0.0", "slug": "demo"}}

    assert remote_manifest_sha256(first) == remote_manifest_sha256(second)
    assert len(remote_manifest_sha256(first)) == 64


def test_remote_tool_publish_errors_require_matching_successful_smoke_test() -> None:
    assert remote_tool_publish_errors({"type": "docker_image"}) == []
    assert remote_tool_publish_errors({"type": "remote_api", "mode": "remote_tool_v1"}) == [
        "remote_tool_v1 requires successful smoke test before publish"
    ]
    assert remote_tool_publish_errors(
        {
            "type": "remote_api",
            "mode": "remote_tool_v1",
            "manifest_sha256": "new",
            "last_smoke_test": {"status": "success", "manifest_sha256": "old"},
        }
    ) == ["remote_tool_v1 smoke test manifest hash does not match current manifest"]
    assert remote_tool_publish_errors(
        {
            "type": "remote_api",
            "mode": "remote_tool_v1",
            "manifest_sha256": "same",
            "last_smoke_test": {"status": "success", "manifest_sha256": "same"},
        }
    ) == []


def test_remote_tool_config_normalizes_discovery_payload() -> None:
    manifest_payload = {
        "metadata": {"slug": "remote-docking"},
        "endpoints": {"invoke": "/invoke", "health": "/health"},
        "artifacts": {"inputs": [{"name": "protein", "type": "protein_structure@1"}]},
        "parameters_schema": {"type": "object", "properties": {"score": {"type": "number"}}},
        "capabilities": {"workflow": True},
    }
    discovery = RemoteToolDiscoveryResult(
        health={"status": "ok"},
        stages=[
            RemoteToolStageDiagnostic(
                name="fetch_manifest",
                status="success",
                message="Loaded",
            )
        ],
    )

    config = remote_tool_config(
        base_url="https://remote.example.com/",
        manifest_payload=manifest_payload,
        manifest_sha256="f" * 64,
        discovery=discovery,
        publish_on_success=True,
    )

    assert config["type"] == "remote_api"
    assert config["mode"] == "remote_tool_v1"
    assert config["base_url"] == "https://remote.example.com"
    assert config["tool_slug"] == "remote-docking"
    assert config["input_schema"] == manifest_payload["parameters_schema"]
    assert config["remote_health"] == {"status": "ok"}
    assert config["registration_diagnostics"][0]["name"] == "fetch_manifest"
    assert config["pending_publish_on_smoke_success"] is True
