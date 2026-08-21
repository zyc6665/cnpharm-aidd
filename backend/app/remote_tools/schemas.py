"""Schemas for the remote-tool.v1 registration contract."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.artifact_standards.registry import is_standard_artifact_ref

try:
    from jsonschema import Draft7Validator

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover - optional runtime dependency guard
    HAS_JSONSCHEMA = False


REMOTE_TOOL_API_VERSION = "aidd.sciminer/remote-tool.v1"


class RemoteToolMetadata(BaseModel):
    """Human-readable and versioning metadata owned by the remote service."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
    description: str = Field(min_length=1)


class RemoteToolArtifactInput(BaseModel):
    """Declared standard Artifact input slot."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    required: bool = True
    role_preferences: list[str] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    readiness_policy: str | None = Field(default=None, max_length=100)
    suggested_preparation_tool: str | None = Field(default=None, max_length=100)

    @field_validator("type")
    @classmethod
    def _validate_standard_ref(cls, value: str) -> str:
        if not is_standard_artifact_ref(value):
            raise ValueError(f"Unknown standard artifact type: {value}")
        return value


class RemoteToolArtifactOutput(BaseModel):
    """Declared standard Artifact output slot."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    cardinality: Literal["one", "many"] = "one"
    required: bool = True
    provided_roles: list[str] | None = Field(default=None)

    @field_validator("type")
    @classmethod
    def _validate_standard_ref(cls, value: str) -> str:
        if not is_standard_artifact_ref(value):
            raise ValueError(f"Unknown standard artifact type: {value}")
        return value


class RemoteToolArtifactContract(BaseModel):
    """Standard Artifact input and output contract."""

    model_config = ConfigDict(extra="forbid")

    inputs: list[RemoteToolArtifactInput] = Field(min_length=1)
    outputs: list[RemoteToolArtifactOutput] = Field(min_length=1)


class RemoteToolEndpoints(BaseModel):
    """Relative endpoint paths exposed by a remote-tool.v1 service."""

    model_config = ConfigDict(extra="forbid")

    invoke: str
    status: str
    logs: str
    cancel: str
    artifacts: str
    examples: str = "/examples"
    health: str = "/health"

    @field_validator("invoke", "status", "logs", "cancel", "artifacts", "examples", "health")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
            raise ValueError("endpoint must be a same-service relative path")
        if ".." in [segment for segment in parsed.path.split("/") if segment]:
            raise ValueError("endpoint must not traverse parent directories")
        return value


class RemoteToolCapabilities(BaseModel):
    """Required remote-tool.v1 runtime capabilities."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    async_: bool = Field(alias="async")
    logs: bool
    cancel: bool
    progress: bool = True

    @model_validator(mode="after")
    def _validate_required_capabilities(self) -> "RemoteToolCapabilities":
        if self.async_ is not True:
            raise ValueError("capabilities.async must be true")
        if self.logs is not True:
            raise ValueError("capabilities.logs must be true")
        if self.cancel is not True:
            raise ValueError("capabilities.cancel must be true")
        return self


class RemoteToolFileExample(BaseModel):
    """Example file supplied by URL or small inline content."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_type: str | None = None
    url: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")
    encoding: Literal["base64", "text"] | None = None
    content: str | None = None


class RemoteToolArtifactExample(BaseModel):
    """Example Artifact input with role-based files."""

    model_config = ConfigDict(extra="forbid")

    type: str
    files: dict[str, RemoteToolFileExample] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _validate_standard_ref(cls, value: str) -> str:
        if not is_standard_artifact_ref(value):
            raise ValueError(f"Unknown standard artifact type: {value}")
        return value


class RemoteToolExample(BaseModel):
    """Runnable example used for smoke testing or demos."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    smoke: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)
    input_artifacts: dict[str, RemoteToolArtifactExample] = Field(default_factory=dict)


class RemoteToolExamplesResponse(BaseModel):
    """Response from the examples endpoint."""

    model_config = ConfigDict(extra="forbid")

    examples: list[RemoteToolExample] = Field(default_factory=list)


class RemoteToolManifest(BaseModel):
    """Top-level remote-tool.v1 manifest."""

    model_config = ConfigDict(extra="forbid")

    api_version: Literal[REMOTE_TOOL_API_VERSION]
    kind: Literal["RemoteTool"]
    metadata: RemoteToolMetadata
    artifacts: RemoteToolArtifactContract
    parameters_schema: dict[str, Any]
    endpoints: RemoteToolEndpoints
    capabilities: RemoteToolCapabilities
    examples: list[RemoteToolExample] = Field(default_factory=list)

    @field_validator("parameters_schema")
    @classmethod
    def _validate_parameters_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "object":
            raise ValueError("parameters_schema.type must be object")
        if HAS_JSONSCHEMA:
            try:
                Draft7Validator.check_schema(value)
            except Exception as exc:
                raise ValueError(f"parameters_schema must be valid JSON Schema Draft-07: {exc}") from exc
        return value
