"""Versioned Tool Package manifest schema."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.artifact_standards.registry import validate_standard_artifact_roles


TOOL_PACKAGE_API_VERSION = "aidd.sciminer/v1"
TOOL_PACKAGE_V2_API_VERSION = "aidd.sciminer/tool-package.v2"


class Accelerator(str, Enum):
    CPU = "cpu"
    NVIDIA_CUDA = "nvidia_cuda"
    HAIGUANG_DCU = "haiguang_dcu"


class ValidationStatus(str, Enum):
    VALIDATED = "validated"
    ADAPTED_PENDING_HARDWARE_VALIDATION = "adapted_pending_hardware_validation"
    UNVALIDATED = "unvalidated"


class ToolPackageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
    description: str | None = None


class ArtifactDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    semantic_type: str = Field(min_length=1, max_length=100)
    artifact_type: str = Field(min_length=1, max_length=100)
    required: bool = True


class ArtifactContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: list[ArtifactDeclaration] = Field(default_factory=list)
    outputs: list[ArtifactDeclaration] = Field(default_factory=list)


class ArtifactInputV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    required: bool = True
    role_preferences: list[str] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    readiness_policy: str | None = Field(default=None, max_length=100)
    suggested_preparation_tool: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_file_roles(self) -> "ArtifactInputV2":
        self.role_preferences = validate_standard_artifact_roles(self.type, self.role_preferences)
        self.required_roles = validate_standard_artifact_roles(self.type, self.required_roles)
        return self


class ArtifactOutputV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    cardinality: Literal["one", "many"] = "one"
    required: bool = True
    provided_roles: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_file_roles(self) -> "ArtifactOutputV2":
        self.provided_roles = validate_standard_artifact_roles(self.type, self.provided_roles)
        return self


class ArtifactContractV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: list[ArtifactInputV2] = Field(default_factory=list)
    outputs: list[ArtifactOutputV2] = Field(default_factory=list)


class ResourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu: float = Field(default=1, gt=0)
    memory_mb: int = Field(default=1024, gt=0)
    devices: list[str] = Field(default_factory=list)
    driver: str | None = None
    gpu_memory_mb: int | None = Field(default=None, gt=0)


class ToolVariantManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    accelerator: Accelerator
    executor_types: list[Literal["container", "cli", "remote_job"]] = Field(min_length=1)
    image: str | None = None
    entrypoint: list[str] = Field(min_length=1)
    resources: ResourceSpec = Field(default_factory=ResourceSpec)
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED
    hardware_validated: bool = False
    inputs: list[str] = Field(min_length=1)
    outputs: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def require_image_for_container(self) -> "ToolVariantManifest":
        if "container" in self.executor_types and not self.image:
            raise ValueError("container executor requires image")
        return self


class ToolVariantManifestV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    accelerator: Accelerator
    executor_types: list[Literal["container", "cli", "remote_job"]] = Field(min_length=1)
    image: str | None = None
    entrypoint: list[str] = Field(min_length=1)
    resources: ResourceSpec = Field(default_factory=ResourceSpec)
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED
    hardware_validated: bool = False

    @model_validator(mode="after")
    def require_image_for_container(self) -> "ToolVariantManifestV2":
        if "container" in self.executor_types and not self.image:
            raise ValueError("container executor requires image")
        return self


class AdapterInputDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str = Field(min_length=1, max_length=100)
    method: str = Field(min_length=1, max_length=160)


class AdapterOutputDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: str = Field(min_length=1, max_length=100)
    method: str = Field(min_length=1, max_length=160)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    validator_profile: str | None = Field(default=None, max_length=160)


class AdapterDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: list[AdapterInputDeclaration] = Field(default_factory=list)
    output: list[AdapterOutputDeclaration] = Field(default_factory=list)


class ExposureDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: bool = True
    workflow: bool = True
    direct_run: bool = True


class RuntimeArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["container", "conda_pack", "venv_pack"]
    image: str | None = Field(default=None, min_length=1, max_length=500)
    image_digest: str | None = Field(default=None, max_length=80)
    uri: str | None = Field(default=None, min_length=1, max_length=500)
    sha256: str | None = Field(default=None, max_length=64)
    includes: list[str] = Field(default_factory=list)


class RuntimeArtifactsManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: RuntimeArtifactManifest
    fallback: RuntimeArtifactManifest


class RuntimeWeightsManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_uri: str = Field(min_length=1, max_length=500)
    manifest_sha256: str = Field(max_length=64)


class RuntimeCachePolicyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_fields: list[str] = Field(min_length=1)
    mutable_host_paths_forbidden: bool = True


class RuntimeEnvManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    python: str = Field(min_length=1, max_length=32)
    cuda: str | None = Field(default=None, min_length=1, max_length=32)
    executor_support: list[Literal["ssh_docker_exec", "slurm", "k8s_job"]] = Field(
        min_length=1
    )
    selection_policy: str = Field(min_length=1, max_length=500)
    artifacts: RuntimeArtifactsManifest
    weights: RuntimeWeightsManifest
    cache_policy: RuntimeCachePolicyManifest


class ToolPackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_version: Literal[TOOL_PACKAGE_API_VERSION]
    kind: Literal["ToolPackage"]
    metadata: ToolPackageMetadata
    artifacts: ArtifactContract
    variants: list[ToolVariantManifest] = Field(min_length=1)


class ToolPackageV2Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_version: Literal[TOOL_PACKAGE_V2_API_VERSION]
    kind: Literal["ToolPackage"]
    metadata: ToolPackageMetadata
    artifacts: ArtifactContractV2
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    adapter: AdapterDeclaration = Field(default_factory=AdapterDeclaration)
    exposure: ExposureDeclaration = Field(default_factory=ExposureDeclaration)
    runtime: RuntimeEnvManifest
    variants: list[ToolVariantManifestV2] = Field(min_length=1)


AnyToolPackageManifest = ToolPackageManifest | ToolPackageV2Manifest
