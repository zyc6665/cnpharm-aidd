"""Versioned Tool Package manifest schema."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TOOL_PACKAGE_API_VERSION = "aidd.sciminer/v1"


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


class ToolPackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_version: Literal[TOOL_PACKAGE_API_VERSION]
    kind: Literal["ToolPackage"]
    metadata: ToolPackageMetadata
    artifacts: ArtifactContract
    variants: list[ToolVariantManifest] = Field(min_length=1)

