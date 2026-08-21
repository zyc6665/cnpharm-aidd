"""Remote tool v1 manifest contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.remote_tools.schemas import RemoteToolManifest


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
                {
                    "name": "protein",
                    "type": "protein_structure@1",
                    "required": True,
                }
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
        "parameters_schema": {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0.5,
                }
            },
            "additionalProperties": False,
        },
        "endpoints": {
            "invoke": "/invoke",
            "status": "/runs/{remote_run_id}",
            "logs": "/runs/{remote_run_id}/logs",
            "cancel": "/runs/{remote_run_id}/cancel",
            "artifacts": "/runs/{remote_run_id}/artifacts",
            "examples": "/examples",
            "health": "/health",
        },
        "capabilities": {
            "async": True,
            "logs": True,
            "cancel": True,
            "progress": True,
        },
    }


def test_remote_tool_manifest_accepts_minimum_valid_contract():
    manifest = RemoteToolManifest.model_validate(valid_remote_tool_manifest())

    assert manifest.api_version == "aidd.sciminer/remote-tool.v1"
    assert manifest.metadata.slug == "lvpocket-api"
    assert manifest.endpoints.invoke == "/invoke"
    assert manifest.artifacts.outputs[0].type == "binding_pocket@1"


def test_remote_tool_manifest_preserves_output_provided_roles():
    payload = valid_remote_tool_manifest()
    payload["artifacts"]["outputs"][0]["provided_roles"] = ["prepared_pdb", "receptor_pdbqt"]

    manifest = RemoteToolManifest.model_validate(payload)

    assert manifest.artifacts.outputs[0].provided_roles == ["prepared_pdb", "receptor_pdbqt"]


def test_remote_tool_manifest_requires_logs_endpoint():
    payload = valid_remote_tool_manifest()
    del payload["endpoints"]["logs"]

    with pytest.raises(ValidationError) as exc_info:
        RemoteToolManifest.model_validate(payload)

    assert "logs" in str(exc_info.value)


def test_remote_tool_manifest_rejects_unknown_standard_artifact_type():
    payload = valid_remote_tool_manifest()
    payload["artifacts"]["outputs"][0]["type"] = "unknown_table@1"

    with pytest.raises(ValidationError) as exc_info:
        RemoteToolManifest.model_validate(payload)

    assert "Unknown standard artifact type" in str(exc_info.value)


def test_remote_tool_manifest_rejects_absolute_endpoint_paths():
    payload = valid_remote_tool_manifest()
    payload["endpoints"]["invoke"] = "https://other.example.com/invoke"

    with pytest.raises(ValidationError) as exc_info:
        RemoteToolManifest.model_validate(payload)

    assert "relative path" in str(exc_info.value)


def test_remote_tool_manifest_rejects_non_object_parameter_schema():
    payload = valid_remote_tool_manifest()
    payload["parameters_schema"] = {"type": "string"}

    with pytest.raises(ValidationError) as exc_info:
        RemoteToolManifest.model_validate(payload)

    assert "parameters_schema.type must be object" in str(exc_info.value)


def test_remote_tool_manifest_requires_async_logs_and_cancel_capabilities():
    payload = valid_remote_tool_manifest()
    payload["capabilities"]["cancel"] = False

    with pytest.raises(ValidationError) as exc_info:
        RemoteToolManifest.model_validate(payload)

    assert "capabilities.cancel must be true" in str(exc_info.value)
