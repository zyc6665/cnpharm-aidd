"""Request schemas for compounds, candidates and candidate sets (docs/05 §4, §5)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

CandidateType = Literal["SMALL_MOLECULE", "PEPTIDE"]
MolSource = Literal["IMPORT", "DESIGN", "SCREENING", "MANUAL"]
DedupeStrategy = Literal["INCHIKEY_UPDATE", "INCHIKEY_SKIP", "INCHIKEY_ERROR"]
OnImportError = Literal["SKIP_AND_CONTINUE", "ABORT"]


class CompoundCreate(BaseModel):
    """单个新增化合物（``POST /projects/{id}/compounds``）。

    ``inchikey`` 由服务端计算而非客户端提交：InChIKey 是去重键，允许客户端自定义
    就等于允许绕过 M1-BR-1。客户端只需给 ``smiles``。
    """

    model_config = ConfigDict(extra="forbid")

    smiles: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=128)


class CompoundImportRequest(BaseModel):
    """批量导入（``POST /projects/{id}/compounds:import``，docs/05 §4.1）。

    直接接收上传后的 ``file_id`` 而不是 ``fileUrn``：交付线一期没有对象存储直传
    链路，文件已经通过 ``POST /files/upload`` 落库，再传 URN 只是多一层翻译。
    """

    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(min_length=1, max_length=36)
    dataset_name: str | None = Field(default=None, max_length=128)
    smiles_column: str | None = Field(default=None, max_length=64)
    name_column: str | None = Field(default=None, max_length=64)
    dedupe_strategy: DedupeStrategy = "INCHIKEY_SKIP"
    on_error: OnImportError = "SKIP_AND_CONTINUE"
    #: 导入后是否把成功的化合物加入候选集；给 ``set_name`` 时新建一个候选集承载。
    set_name: str | None = Field(default=None, max_length=128)


class CandidateCreate(BaseModel):
    """项目内新增候选物（小分子或多肽）。"""

    model_config = ConfigDict(extra="forbid")

    candidate_type: CandidateType = "SMALL_MOLECULE"
    smiles: str | None = Field(default=None, max_length=2048)
    peptide_sequence: str | None = Field(default=None, max_length=4096)
    name: str | None = Field(default=None, max_length=128)
    code: str | None = Field(default=None, max_length=128)
    source: MolSource = "MANUAL"
    design_score: float | None = None
    task_id: str | None = Field(default=None, max_length=36)
    attrs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_payload(self) -> "CandidateCreate":
        if self.candidate_type == "SMALL_MOLECULE" and not (self.smiles or "").strip():
            raise ValueError("小分子候选物必须提供 smiles")
        if self.candidate_type == "PEPTIDE" and not (self.peptide_sequence or "").strip():
            raise ValueError("多肽候选物必须提供 peptide_sequence")
        return self


class CandidateUpdate(BaseModel):
    """候选物可编辑字段（名称/代号/评分/属性）。

    结构本身不可改：改结构等于换一个分子，应当新增候选物，否则历史集合里的
    ``snapshot_score`` 与结构就对不上了。
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=128)
    code: str | None = Field(default=None, max_length=128)
    design_score: float | None = None
    attrs: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "CandidateUpdate":
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待更新字段")
        return self


class CandidateSetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    source_task_id: str | None = Field(default=None, max_length=36)


class CandidateSetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    #: 乐观锁版本号（docs/04 §5.6）：提交时必须带当前版本，不匹配返回 40903。
    version: int = Field(ge=1)
    expected_version: int | None = Field(
        default=None,
        validation_alias=AliasChoices("expected_version", "expectedVersion"),
    )

    @model_validator(mode="after")
    def require_change(self) -> "CandidateSetUpdate":
        if not ({"name", "description"} & self.model_fields_set):
            raise ValueError("至少需要提供一个待更新字段")
        return self


class CandidateSetItemsAdd(BaseModel):
    """批量加入候选物（``POST /candidate-sets/{id}/items``，docs/05 §5）。

    ``snapshot_score`` 可由调用方覆盖；不给则取候选物当前的 ``design_score``。
    """

    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[str] = Field(min_length=1, max_length=2000)
    snapshot_score: float | None = None


class CandidateCompareRequest(BaseModel):
    """多候选物比较（``POST /candidates:compare``，≤6 个，docs/01 M3-FR-08）。"""

    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[str] = Field(
        min_length=1,
        max_length=6,
        validation_alias=AliasChoices("candidate_ids", "candidateIds"),
    )
