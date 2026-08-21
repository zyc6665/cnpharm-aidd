"""Schemas for static platform tool templates."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.artifact_standards.types import (
    is_supported_platform_artifact_type,
    normalize_platform_artifact_type,
)

try:
    from jsonschema import Draft7Validator

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover - optional dependency guard
    HAS_JSONSCHEMA = False


TOOL_TEMPLATE_API_VERSION = "aidd.sciminer/tool-template.v1"
STANDARD_RESULT_VERSION = "aidd.sciminer/result.v2"
SUPPORTED_TEMPLATE_EXECUTOR_TYPES = {"remote_api", "docker_image", "python_script", "ssh_job"}


class ToolTemplateMetadata(BaseModel):
    """Human-readable identity for a reusable tool template."""

    model_config = ConfigDict(extra="forbid")

    template_key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
    description: str = Field(min_length=1)
    family: Literal["drug_discovery"] = "drug_discovery"


class ToolTemplateCapabilityInput(BaseModel):
    """Agent/workflow semantic input declaration."""

    model_config = ConfigDict(extra="forbid")

    semantic_type: str = Field(min_length=1, max_length=100)
    field: str = Field(min_length=1, max_length=100)
    required: bool = True
    accepted_extensions: list[str] = Field(default_factory=list)

    @field_validator("semantic_type")
    @classmethod
    def _validate_semantic_type(cls, value: str) -> str:
        if not is_supported_platform_artifact_type(value):
            raise ValueError(f"Unknown platform artifact semantic type: {value}")
        return normalize_platform_artifact_type(value)


class ToolTemplateCapabilityOutput(BaseModel):
    """Agent/workflow semantic output declaration."""

    model_config = ConfigDict(extra="forbid")
    semantic_type: str = Field(min_length=1, max_length=100)
    source: Literal["output_files", "output_data"] = "output_files"
    match: dict[str, Any] = Field(default_factory=dict)
    path: str | None = Field(default=None, max_length=160)
    required: bool = True

    @field_validator("semantic_type")
    @classmethod
    def _validate_semantic_type(cls, value: str) -> str:
        if not is_supported_platform_artifact_type(value):
            raise ValueError(f"Unknown platform artifact semantic type: {value}")
        return normalize_platform_artifact_type(value)

    @model_validator(mode="after")
    def _require_path_for_output_data(self) -> "ToolTemplateCapabilityOutput":
        if self.source == "output_data" and not self.path:
            raise ValueError("output_data capability outputs require path")
        return self


class ToolTemplateAgentCapability(BaseModel):
    """Existing ToolVersion config `agent_capability` block."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    capability: str = Field(min_length=1, max_length=100)
    stage: str = Field(min_length=1, max_length=100)
    inputs: list[ToolTemplateCapabilityInput] = Field(min_length=1)
    outputs: list[ToolTemplateCapabilityOutput] = Field(min_length=1)
    defaults: dict[str, Any] = Field(default_factory=dict)


class ToolTemplateArtifactInput(BaseModel):
    """Standard Artifact input slot emitted by a tool template."""

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
    def _validate_type(cls, value: str) -> str:
        if not is_supported_platform_artifact_type(value):
            raise ValueError(f"Unknown platform artifact type: {value}")
        return normalize_platform_artifact_type(value)


class ToolTemplateArtifactOutput(BaseModel):
    """Standard Artifact output slot emitted by a tool template."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    cardinality: Literal["one", "many"] = "one"
    required: bool = True
    provided_roles: list[str] = Field(default_factory=list)

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        if not is_supported_platform_artifact_type(value):
            raise ValueError(f"Unknown platform artifact type: {value}")
        return normalize_platform_artifact_type(value)


class ToolTemplateArtifactContract(BaseModel):
    """Standard Artifact slots exposed to workflow and direct-run surfaces."""

    model_config = ConfigDict(extra="forbid")

    inputs: list[ToolTemplateArtifactInput] = Field(default_factory=list)
    outputs: list[ToolTemplateArtifactOutput] = Field(default_factory=list)


class ToolTemplateImplementation(BaseModel):
    """Recommended open-source or internal implementation for a template."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["open_source", "internal_service"]
    provider: str = Field(min_length=1, max_length=160)
    runtime: str = Field(min_length=1, max_length=100)
    project_url: str | None = Field(default=None, max_length=500)
    recommended_executor: Literal[
        "remote_api",
        "docker_image",
        "python_script",
        "ssh_job",
    ]
    notes: str | None = Field(default=None, max_length=500)


class ToolTemplateResourceProfile(BaseModel):
    """Resource declaration used by UI hints and queue selection."""

    model_config = ConfigDict(extra="forbid")

    tier: Literal["light", "medium", "heavy"]
    cpu: float = Field(gt=0)
    memory_gb: float = Field(gt=0)
    gpu_required: bool = False
    gpu_memory_gb: float = Field(default=0, ge=0)
    expected_minutes: int = Field(gt=0)
    timeout_minutes: int = Field(gt=0)
    scheduler_hint: Literal["local", "ssh", "api", "future_cluster"]

    @model_validator(mode="after")
    def _validate_resource_consistency(self) -> "ToolTemplateResourceProfile":
        if self.timeout_minutes < self.expected_minutes:
            raise ValueError("resource_profile.timeout_minutes must cover expected_minutes")
        if self.gpu_required and self.gpu_memory_gb <= 0:
            raise ValueError("gpu_required templates must declare gpu_memory_gb")
        return self


class ToolTemplateSampleInput(BaseModel):
    """Runnable sample owned by the template."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)


class ToolTemplateExpectedOutput(BaseModel):
    """Expected standard artifact from a smoke test."""

    model_config = ConfigDict(extra="forbid")

    semantic_type: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=100)
    required: bool = True

    @field_validator("semantic_type")
    @classmethod
    def _validate_semantic_type(cls, value: str) -> str:
        if not is_supported_platform_artifact_type(value):
            raise ValueError(f"Unknown platform artifact semantic type: {value}")
        return normalize_platform_artifact_type(value)


class ToolTemplateSmokeTest(BaseModel):
    """Smoke-test contract that a registered implementation must satisfy."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)
    input_artifacts: dict[str, str] = Field(default_factory=dict)
    expected_result_version: Literal[STANDARD_RESULT_VERSION]
    expected_outputs: list[ToolTemplateExpectedOutput] = Field(min_length=1)


class DrugDiscoveryToolTemplate(BaseModel):
    """Static template for creating a current platform Tool draft."""

    model_config = ConfigDict(extra="forbid")

    api_version: Literal[TOOL_TEMPLATE_API_VERSION]
    kind: Literal["ToolTemplate"]
    metadata: ToolTemplateMetadata
    executor_types: list[Literal["remote_api", "docker_image", "python_script", "ssh_job"]] = Field(
        min_length=1
    )
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    agent_capability: ToolTemplateAgentCapability
    artifacts: ToolTemplateArtifactContract = Field(default_factory=ToolTemplateArtifactContract)
    implementation: ToolTemplateImplementation
    resource_profile: ToolTemplateResourceProfile
    sample_inputs: list[ToolTemplateSampleInput] = Field(min_length=1)
    smoke_test: ToolTemplateSmokeTest

    @field_validator("input_schema", "output_schema")
    @classmethod
    def _validate_json_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "object":
            raise ValueError("template schemas must have type=object")
        if HAS_JSONSCHEMA:
            try:
                Draft7Validator.check_schema(value)
            except Exception as exc:  # pragma: no cover - dependency wraps many errors
                raise ValueError(f"template schema must be valid JSON Schema Draft-07: {exc}") from exc
        return value

    @model_validator(mode="after")
    def _validate_standard_result_contract(self) -> "DrugDiscoveryToolTemplate":
        result_version_schema = self.output_schema.get("properties", {}).get("result_version", {})
        if result_version_schema.get("const") != STANDARD_RESULT_VERSION:
            raise ValueError("output_schema.properties.result_version.const must be aidd.sciminer/result.v2")

        capability_outputs = {output.semantic_type for output in self.agent_capability.outputs}
        expected_outputs = {output.semantic_type for output in self.smoke_test.expected_outputs}
        missing = sorted(expected_outputs - capability_outputs)
        if missing:
            raise ValueError(f"smoke_test.expected_outputs not declared by agent_capability: {missing}")

        if self.metadata.template_key != self.metadata.slug:
            raise ValueError("metadata.template_key and metadata.slug must match for tool import templates")
        return self
