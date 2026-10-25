"""数据集登记请求模型（docs/04 §8、docs/05 §4.1）。

数据集只登记「已完成的导入结果」：``file_urn`` 指向 ``files`` 表里已有的文件，
``summary`` 是那次解析的摘要（行数、列名、无效行统计等）。本模块**不做解析**，
因此这里也不接收文件内容——那是既有的 ``POST /projects/{id}/compounds:import``。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

#: 与 ``app.models.uploads.DATASET_TYPES`` 保持同一口径的字面量类型，让 422 在
#: 请求入口就发生，而不是等到写库时才发现类型不认识。
DatasetType = Literal["COMPOUND", "PROTEIN", "ACTIVITY", "LITERATURE", "EXPERIMENT"]

#: 库内只存 urn + sha256（docs/04 §1），URN 必须带 ``file:`` scheme 才能反查文件。
FILE_URN_PREFIX = "file:"


class DatasetCreate(BaseModel):
    """登记一个已完成的数据集导入结果。"""

    name: str = Field(min_length=1, max_length=128)
    dataset_type: DatasetType = Field(
        validation_alias=AliasChoices("datasetType", "dataset_type"),
    )
    file_urn: str = Field(
        min_length=len(FILE_URN_PREFIX) + 1,
        max_length=512,
        validation_alias=AliasChoices("fileUrn", "file_urn"),
    )
    row_count: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("rowCount", "row_count"),
    )
    summary: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("file_urn")
    @classmethod
    def require_file_scheme(cls, value: str) -> str:
        """``file_urn`` 必须是 ``file:`` 前缀，否则 422。

        裸 uuid 或 ``oss://`` 都不能反查文件；放行会在 ``load_dataset`` 时才发现，
        那时已经写了脏数据，因此在入口就拒绝。
        """
        if not value.startswith(FILE_URN_PREFIX):
            raise ValueError(f"file_urn 必须以 {FILE_URN_PREFIX} 开头")
        if not value[len(FILE_URN_PREFIX):].strip():
            raise ValueError("file_urn 缺少文件标识")
        return value


__all__ = ["FILE_URN_PREFIX", "DatasetCreate", "DatasetType"]
