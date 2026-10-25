"""Target / protein / structure / pocket request schemas (docs/05 §5)."""

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


TargetType = Literal["PROTEIN"]
ProteinSource = Literal["IMPORT", "MANUAL"]
StructureSourceType = Literal["PREDICTED", "IMPORTED", "PREPARED"]


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    target_type: TargetType = "PROTEIN"
    uniprot_id: str | None = Field(default=None, max_length=32)
    gene_name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=20_000)

    model_config = ConfigDict(extra="forbid")


class TargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    uniprot_id: str | None = Field(default=None, max_length=32)
    gene_name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=20_000)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("at least one target field is required")
        return self


class ProteinCreate(BaseModel):
    """导入蛋白序列。

    ``sequence`` 与 ``file_id`` 二选一：前者手工粘贴/导入 FASTA 文本，后者指向
    平台上已上传的 FASTA 文件。两者都给时以 ``sequence`` 为准（调用方通常已经
    把文件解析成序列）。
    """

    name: str = Field(min_length=1, max_length=128)
    sequence: str | None = Field(default=None, max_length=2_000_000)
    file_id: str | None = Field(default=None, max_length=36)
    source: ProteinSource = "MANUAL"

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_sequence_source(self):
        if not self.sequence and not self.file_id:
            raise ValueError("sequence or file_id is required")
        return self


class ModelRef(BaseModel):
    """模型引用（docs/03 §3.3 ``toolRef`` 的模型侧写法）。"""

    name: str = Field(min_length=1, max_length=64)
    version: str | None = Field(default=None, max_length=64)

    model_config = ConfigDict(extra="forbid")


class StructurePredict(BaseModel):
    """提交结构预测 / 口袋预测任务的请求体（docs/05 §5.1）。

    ``resource_profile`` 与 ``scale`` 只作预估与上限保护，准入时由调度器按规模重算
    （docs/04 §9 ``resource_profile`` 字段说明）。字段同时接受 docs/05 的
    camelCase 写法与平台既有的 snake_case 写法。
    """

    model_ref: ModelRef | None = Field(
        default=None,
        validation_alias=AliasChoices("model_ref", "modelRef"),
    )
    params: dict[str, Any] = Field(default_factory=dict)
    scale: dict[str, Any] | None = None
    resource_profile: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("resource_profile", "resourceProfile"),
    )
    priority: Literal["low", "normal", "high"] = "normal"

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class StructurePrepareRequest(BaseModel):
    """结构准备：生成可对接的 PDB/PDBQT（docs/05 §5 ``structures/{id}:prepare``）。"""

    tool_slug: str | None = Field(default=None, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)
    priority: Literal["low", "normal", "high"] = "normal"

    model_config = ConfigDict(extra="forbid")


class ProteinUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    sequence: str | None = Field(default=None, max_length=2_000_000)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("at least one protein field is required")
        return self


class StructureImport(BaseModel):
    """导入已有结构。

    ``file_id`` 指向平台已上传的 PDB/mmCIF 文件；``plddt_file_id`` 用于同时上传
    预测置信度文件（预测结构才有）。两者都会复制到结构存储并记录 sha256。
    """

    file_id: str = Field(min_length=1, max_length=36)
    plddt_file_id: str | None = Field(default=None, max_length=36)
    name: str | None = Field(default=None, max_length=128)
    model_name: str | None = Field(default=None, max_length=64)
    model_version: str | None = Field(default=None, max_length=64)
    source_type: StructureSourceType = "IMPORTED"

    model_config = ConfigDict(extra="forbid")


class PocketResidueCreate(BaseModel):
    chain: str = Field(min_length=1, max_length=8)
    residue_seq: int = Field(ge=-99999, le=999999)
    residue_name: str = Field(min_length=1, max_length=8)
    is_key: bool = False
    contribution: float | None = None

    model_config = ConfigDict(extra="forbid")


class PocketCreate(BaseModel):
    """手工登记口袋（例如从外部工具结果导入）。

    口袋预测任务产出的口袋由任务结果回写创建，不走本接口。
    """

    rank: int = Field(ge=1, le=1000)
    score: float | None = None
    volume: float | None = None
    center_x: float | None = None
    center_y: float | None = None
    center_z: float | None = None
    box_size_x: float | None = Field(default=None, gt=0)
    box_size_y: float | None = Field(default=None, gt=0)
    box_size_z: float | None = Field(default=None, gt=0)
    tool_name: str | None = Field(default=None, max_length=64)
    tool_version: str | None = Field(default=None, max_length=64)
    residues: list[PocketResidueCreate] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_center_for_box(self):
        has_box = any(
            value is not None
            for value in (self.box_size_x, self.box_size_y, self.box_size_z)
        )
        has_center = all(
            value is not None for value in (self.center_x, self.center_y, self.center_z)
        )
        if has_box and not has_center:
            raise ValueError("box_size requires center_x/center_y/center_z")
        return self


class PocketSelectRequest(BaseModel):
    """选定/取消选定口袋。``selected=false`` 用于显式取消。"""

    selected: bool = True

    model_config = ConfigDict(extra="forbid")
