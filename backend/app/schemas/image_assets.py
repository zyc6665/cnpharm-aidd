"""管理员镜像资产接口 Schema。"""

from pydantic import BaseModel, ConfigDict, Field


class ImageAssetResponse(BaseModel):
    id: str
    repository: str
    tag: str
    image_reference: str
    manifest_digest: str
    archive_sha256: str
    archive_size_bytes: int
    platform: str
    status: str
    error_message: str | None = None
    created_by: str

    model_config = ConfigDict(from_attributes=True)


class ImageAssetBindingRequest(BaseModel):
    tool_version_id: str
    resource_profile: str = Field(min_length=1, max_length=64)
    entrypoint: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)
