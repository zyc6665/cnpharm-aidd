"""Tool Package management API schemas."""

from pydantic import BaseModel, Field

from app.tool_packages.schemas import AnyToolPackageManifest


class ToolPackageCreate(BaseModel):
    manifest: AnyToolPackageManifest
    signature: str | None = Field(default=None, min_length=1, max_length=4096)
