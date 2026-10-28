"""数据集登记请求模型（docs/04 §8、docs/05 §4.1）。

数据集只登记「已完成的导入结果」：``file_urn`` 指向 ``files`` 表里已有的文件，
``summary`` 是那次解析的摘要（行数、列名、无效行统计等）。本模块**不做解析**，
因此这里也不接收文件内容——那是既有的 ``POST /projects/{id}/compounds:import``。

``LITERATURE`` / ``EXPERIMENT`` / ``DOCUMENT`` 这类非结构资产不解析，只登记文件 +
结构化属性（docs/02 Q-03）。结构化属性统一落到 ``Dataset.summary`` 这个 JSON 列，
请求侧通过可选的 ``attributes`` 传入，由服务层并入 ``summary``（见
``app.services.datasets.register_dataset``）。

``file_urn`` 的 ``file:`` 前缀**不再是入口硬校验**：外部系统可能给出 ``oss://`` 等
其它形态的 urn，登记仍然成功，只是不会解析出 ``data_files`` 行（兼容旧行为，详见
``app.services.datasets.serialize_dataset`` 的说明）。``file:`` urn 指向的文件是否
存在、是否属于本项目，由服务层在写库前校验。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.models.uploads import DATASET_TYPES

#: 与 ``app.models.uploads.DATASET_TYPES`` **从同一常量派生**，避免两处枚举漂移：
#: 新增类型只改常量即可，``Literal`` 会跟着变大，422 依旧在请求入口发生。
DatasetType = Literal[tuple(DATASET_TYPES)]

#: 库内只存 urn + sha256（docs/04 §1）。保留这个常量供外部引用；解析复用
#: ``app.services.domain_targets`` 的 ``FILE_URN_PREFIX`` / ``urn_file_id``。
FILE_URN_PREFIX = "file:"


class DatasetCreate(BaseModel):
    """登记一个已完成的数据集导入结果。"""

    name: str = Field(min_length=1, max_length=128)
    dataset_type: DatasetType = Field(
        validation_alias=AliasChoices("datasetType", "dataset_type"),
    )
    file_urn: str = Field(
        min_length=1,
        max_length=512,
        validation_alias=AliasChoices("fileUrn", "file_urn"),
    )
    row_count: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("rowCount", "row_count"),
    )
    summary: dict[str, Any] = Field(default_factory=dict)
    #: 结构化属性字段（docs/02 Q-03）。非结构资产（文献/实验数据/文档附件）用它
    #: 承载 DOI、作者、仪器、批次等键值；服务层把它并入 ``summary``，不落新列。
    attributes: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("attributes"),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


__all__ = ["FILE_URN_PREFIX", "DatasetCreate", "DatasetType"]
