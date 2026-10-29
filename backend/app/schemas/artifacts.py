"""Typed Artifact request validation helpers."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.artifact_standards.asset_types import (
    ASSET_ARTIFACT_TYPES,
    is_asset_artifact_type,
)


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

    @field_validator("artifact_type")
    @classmethod
    def validate_artifact_type(cls, value: str) -> str:
        # 入口层快速失败（422）：非法值不落到 DB 变成 500。取值与模型 CHECK 同源
        # （``app.artifact_standards.asset_types``），这里不重复维护一份列表。
        if not is_asset_artifact_type(value):
            raise ValueError(
                "artifact_type 必须是受控资产类型之一: "
                + ", ".join(ASSET_ARTIFACT_TYPES)
            )
        return value

    @model_validator(mode="after")
    def validate_standard_type(self):
        if (self.standard_type is None) != (self.standard_version is None):
            raise ValueError("standard_type and standard_version must be provided together")
        return self
