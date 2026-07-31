"""Typed Artifact request validation helpers."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ArtifactMetadata(BaseModel):
    artifact_type: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    semantic_type: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    description: str | None = Field(default=None, max_length=10_000)
    expires_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")
