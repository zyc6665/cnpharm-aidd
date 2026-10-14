"""Tool Package management API schemas."""

from pydantic import BaseModel, ConfigDict, Field

from app.tool_packages.schemas import AnyToolPackageManifest


class ToolPackageCreate(BaseModel):
    manifest: AnyToolPackageManifest
    signature: str | None = Field(default=None, min_length=1, max_length=4096)


class ToolPackageKubernetesRegistrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_version_id: str = Field(min_length=1, max_length=36)
    target_tool_id: str | None = Field(default=None, min_length=1, max_length=36)
    category_id: str | None = Field(default=None, min_length=1, max_length=36)
    tool_version: str = Field(min_length=1, max_length=50)
    variant_name: str = Field(min_length=1, max_length=100)
    resource_profile: str = Field(min_length=1, max_length=100)
