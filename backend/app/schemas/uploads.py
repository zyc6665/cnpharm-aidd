"""分片上传会话请求模型（docs/05 §4.2）。

字段口径沿用 docs/05 的 camelCase（前端直接提交 `projectId`/`contentType`），
同时兼容平台内部既有的 snake_case 调用方——用 ``AliasChoices`` 同时接受两种写法，
而不是二选一，避免前端与既有服务层各写一套。
"""

from __future__ import annotations

from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

#: 单文件上限 2GB（docs/04 §13.2、docs/16 §4.1）。与分片大小 16MB 相乘正好 ≤128 片，
#: 因此 ``parts`` 这个 JSON 列不会膨胀。
MAX_UPLOAD_BYTES = 2 * 1024**3


class UploadSessionCreate(BaseModel):
    """创建分片上传会话。

    ``size`` 由客户端声明，服务端用它算 ``partCount`` 与配额校验；真实字节数在
    第 2~5 片上报时逐片累加核对。``sha256`` 可选，客户端预先算好则 complete 时校验。
    """

    project_id: str = Field(
        min_length=1,
        max_length=36,
        validation_alias=AliasChoices("projectId", "project_id"),
    )
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, le=MAX_UPLOAD_BYTES)
    content_type: Optional[str] = Field(
        default=None,
        max_length=128,
        validation_alias=AliasChoices("contentType", "content_type"),
    )
    sha256: Optional[str] = Field(default=None, max_length=64)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class UploadPartRef(BaseModel):
    """已上报分片的引用（``POST /uploads/{id}:complete`` 的 ``parts`` 元素）。"""

    part_number: int = Field(
        ge=1,
        validation_alias=AliasChoices("partNumber", "part_number"),
    )
    etag: Optional[str] = Field(default=None, max_length=128)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class UploadCompleteRequest(BaseModel):
    """合并请求。

    ``parts`` 必须覆盖 ``1..partCount``；缺片时返回 422（docs/05 §4.2 的 42204）。
    """

    parts: list[UploadPartRef] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "MAX_UPLOAD_BYTES",
    "UploadCompleteRequest",
    "UploadPartRef",
    "UploadSessionCreate",
]
