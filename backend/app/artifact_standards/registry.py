"""Load and validate platform-controlled standard Artifact definitions."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


class StandardArtifactRegistryError(ValueError):
    """Raised when a standard Artifact type or relation is unknown or malformed."""


class StandardArtifactRef(BaseModel):
    """A versioned standard Artifact reference such as ``binding_pocket@1``."""

    type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")

    @property
    def ref(self) -> str:
        return f"{self.type}@{self.version}"


class FileRoleSpec(BaseModel):
    """Required or optional file role within a logical standard Artifact."""

    role: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    required: bool = True
    primary: bool = False
    allowed_formats: list[str] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    recommended_name: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("allowed_formats", "content_types")
    @classmethod
    def _dedupe_ordered(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class StandardArtifactSpec(BaseModel):
    """A platform-controlled logical Artifact type definition."""

    type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)
    file_roles: list[FileRoleSpec] = Field(min_length=1)
    metadata_schema: dict[str, Any] = Field(default_factory=dict)
    validators: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @property
    def ref(self) -> str:
        return f"{self.type}@{self.version}"

    @field_validator("file_roles")
    @classmethod
    def _validate_file_roles(cls, roles: list[FileRoleSpec]) -> list[FileRoleSpec]:
        role_names = [role.role for role in roles]
        if len(role_names) != len(set(role_names)):
            raise ValueError("file role names must be unique")
        if sum(1 for role in roles if role.primary) > 1:
            raise ValueError("only one file role can be primary")
        return roles


class RelationSpec(BaseModel):
    """A controlled relationship type between standard Artifact versions."""

    type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


def parse_standard_ref(value: str) -> StandardArtifactRef:
    """Parse and validate a versioned standard Artifact reference."""
    if "@" not in value:
        raise StandardArtifactRegistryError(f"Unknown standard artifact type: {value}")
    artifact_type, raw_version = value.rsplit("@", 1)
    try:
        ref = StandardArtifactRef(type=artifact_type, version=int(raw_version))
    except Exception as exc:
        raise StandardArtifactRegistryError(f"Invalid standard artifact ref: {value}") from exc
    if ref.ref not in load_standard_artifact_specs():
        raise StandardArtifactRegistryError(f"Unknown standard artifact type: {value}")
    return ref


def is_standard_artifact_ref(value: str) -> bool:
    """Return whether a value is a known standard Artifact reference."""
    try:
        parse_standard_ref(value)
    except StandardArtifactRegistryError:
        return False
    return True


def get_standard_artifact_spec(ref: str) -> StandardArtifactSpec:
    """Return a standard Artifact spec by ``type@version``."""
    specs = load_standard_artifact_specs()
    if ref not in specs:
        raise StandardArtifactRegistryError(f"Unknown standard artifact type: {ref}")
    return specs[ref]


@lru_cache(maxsize=1)
def load_standard_artifact_specs() -> dict[str, StandardArtifactSpec]:
    """Load all platform-controlled standard Artifact specs from repository files."""
    specs: dict[str, StandardArtifactSpec] = {}
    for path in sorted(SCHEMA_DIR.glob("*.v*.yaml")):
        data = _load_yaml_object(path)
        spec = StandardArtifactSpec.model_validate(data)
        if spec.ref in specs:
            raise StandardArtifactRegistryError(f"Duplicate standard artifact type: {spec.ref}")
        specs[spec.ref] = spec
    return specs


@lru_cache(maxsize=1)
def load_relation_specs() -> dict[str, RelationSpec]:
    """Load controlled Artifact relation type definitions."""
    path = SCHEMA_DIR / "relations.yaml"
    data = _load_yaml_object(path)
    raw_relations = data.get("relations") if isinstance(data, dict) else None
    if not isinstance(raw_relations, list):
        raise StandardArtifactRegistryError("relations.yaml must contain a relations list")
    relations: dict[str, RelationSpec] = {}
    for item in raw_relations:
        relation = RelationSpec.model_validate(item)
        if relation.type in relations:
            raise StandardArtifactRegistryError(f"Duplicate relation type: {relation.type}")
        relations[relation.type] = relation
    return relations


def validate_relation_type(value: str) -> str:
    """Return a relation type if it is controlled by the platform registry."""
    if value not in load_relation_specs():
        raise StandardArtifactRegistryError(f"Unknown relation type: {value}")
    return value


def _load_yaml_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise StandardArtifactRegistryError(f"Missing standard registry file: {path.name}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise StandardArtifactRegistryError(f"{path.name} must contain a YAML object")
    return data
