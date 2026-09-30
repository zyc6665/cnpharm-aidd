"""Typed Artifact request validation helpers."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArtifactMetadata(BaseModel):
    artifact_type: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    semantic_type: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    standard_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    standard_version: int | None = Field(default=None, ge=1)
    description: str | None = Field(default=None, max_length=10_000)
    expires_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_standard_type(self):
        if (self.standard_type is None) != (self.standard_version is None):
            raise ValueError("standard_type and standard_version must be provided together")
        return self
