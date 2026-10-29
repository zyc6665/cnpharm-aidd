"""Executor-neutral standard request/result contracts for Tool Package v2."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.artifact_standards.registry import (
    StandardArtifactRegistryError,
    get_standard_artifact_spec,
    parse_standard_ref,
    validate_relation_type,
)


class StandardExecutionContractError(ValueError):
    """Raised when a standard execution request or result violates its contract."""


class StandardFileRef(BaseModel):
    """A staged input file reference visible to model adapters."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    content_type: str | None = None

    model_config = ConfigDict(extra="forbid")


class StandardInputArtifact(BaseModel):
    """A versioned ArtifactVersion bound to a manifest input slot."""

    artifact_version_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    files: dict[str, StandardFileRef] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class StandardTaskContext(BaseModel):
    """Task identity passed to model adapters for traceability."""

    id: str = Field(min_length=1)
    tool_slug: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


class StandardExecutionContext(BaseModel):
    """Execution context exposed to the runner without infrastructure credentials."""

    variant: str = Field(min_length=1)
    accelerator: str = Field(min_length=1)
    work_dir: str = Field(default=".")
    output_dir: str = Field(default="output")

    model_config = ConfigDict(extra="forbid")


class StandardExecutionRequest(BaseModel):
    """Standard request envelope consumed by Tool Package adapters."""

    request_version: Literal["aidd.sciminer/request"]
    task: StandardTaskContext
    inputs: dict[str, StandardInputArtifact] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    execution: StandardExecutionContext

    model_config = ConfigDict(extra="forbid")


class StandardOutputFile(BaseModel):
    """A file emitted under output_dir for a standard output Artifact role."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    content_type: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("path")
    @classmethod
    def _validate_output_path(cls, value: str) -> str:
        try:
            return safe_output_relative_path(value)
        except StandardExecutionContractError as exc:
            raise ValueError(str(exc)) from exc


class StandardOutputArtifact(BaseModel):
    """A logical output Artifact declared in result.v2."""

    name: str | None = None
    type: str = Field(min_length=1)
    files: dict[str, StandardOutputFile] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class StandardRelationDeclaration(BaseModel):
    """A controlled relationship between output Artifacts."""

    from_ref: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    type: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("type")
    @classmethod
    def _validate_relation_type(cls, value: str) -> str:
        try:
            return validate_relation_type(value)
        except StandardArtifactRegistryError as exc:
            raise ValueError(str(exc)) from exc


OutputArtifactValue = StandardOutputArtifact | list[StandardOutputArtifact]


class StandardExecutionResult(BaseModel):
    """Standard result envelope emitted by Tool Package adapters."""

    result_version: Literal["aidd.sciminer/result"]
    artifacts: dict[str, OutputArtifactValue] = Field(default_factory=dict)
    relations: list[StandardRelationDeclaration] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class DeclaredArtifactOutput(BaseModel):
    """A manifest output slot used to validate a result.v2 envelope."""

    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    cardinality: Literal["one", "many"] = "one"
    required: bool = True

    model_config = ConfigDict(extra="forbid")


def safe_output_relative_path(path: str) -> str:
    """Normalize and validate a result path relative to output_dir."""
    normalized = path.replace("\\", "/").strip()
    parsed = PurePosixPath(normalized)
    if (
        not normalized
        or parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise StandardExecutionContractError(f"Unsafe output path: {path}")
    return parsed.as_posix()


def validate_result_against_declared_outputs(
    result: StandardExecutionResult,
    declared_outputs: list[DeclaredArtifactOutput] | tuple[DeclaredArtifactOutput, ...],
) -> None:
    """Validate output names, cardinality, standard types, and required file roles."""
    declarations = {item.name: item for item in declared_outputs}
    for name in result.artifacts:
        if name not in declarations:
            raise StandardExecutionContractError(f"Unexpected output artifact: {name}")

    for declaration in declared_outputs:
        value = result.artifacts.get(declaration.name)
        if value is None:
            if declaration.required:
                raise StandardExecutionContractError(
                    f"Missing required output artifact: {declaration.name}"
                )
            continue
        if declaration.cardinality == "one":
            if isinstance(value, list):
                raise StandardExecutionContractError(
                    f"Output artifact {declaration.name} must be a single artifact"
                )
            _validate_artifact_against_declaration(declaration, value)
            continue
        if not isinstance(value, list):
            raise StandardExecutionContractError(
                f"Output artifact {declaration.name} must be a list of artifacts"
            )
        for artifact in value:
            _validate_artifact_against_declaration(declaration, artifact)


def iter_declared_output_artifacts(
    result: StandardExecutionResult,
    declared_outputs: list[DeclaredArtifactOutput] | tuple[DeclaredArtifactOutput, ...],
) -> Iterator[tuple[DeclaredArtifactOutput, int | None, StandardOutputArtifact]]:
    """Yield normalized output artifacts in manifest declaration order."""
    validate_result_against_declared_outputs(result, declared_outputs)
    for declaration in declared_outputs:
        value = result.artifacts.get(declaration.name)
        if value is None:
            continue
        if isinstance(value, list):
            for index, artifact in enumerate(value):
                yield declaration, index, artifact
        else:
            yield declaration, None, value


def _validate_artifact_against_declaration(
    declaration: DeclaredArtifactOutput,
    artifact: StandardOutputArtifact,
) -> None:
    try:
        declared_ref = parse_standard_ref(declaration.type)
        artifact_ref = parse_standard_ref(artifact.type)
    except StandardArtifactRegistryError as exc:
        raise StandardExecutionContractError(str(exc)) from exc
    if artifact_ref.ref != declared_ref.ref:
        raise StandardExecutionContractError(
            f"Output artifact {declaration.name} type must be {declared_ref.ref}, "
            f"got {artifact_ref.ref}"
        )

    spec = get_standard_artifact_spec(declared_ref.ref)
    missing_roles = [
        role.role
        for role in spec.file_roles
        if role.required and role.role not in artifact.files
    ]
    if missing_roles:
        raise StandardExecutionContractError(
            f"Output artifact {declaration.name} missing required file roles: "
            + ", ".join(missing_roles)
        )
