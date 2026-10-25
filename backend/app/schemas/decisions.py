"""Request schemas for decision records (docs/05 §3.3, docs/04 §9.5).

字段同时接受 snake_case 与 camelCase：``docs/05`` 的示例是 camelCase，而平台既有
接口（``serialize_candidate`` 等）返回 snake_case，前端两种写法都在用。别名只解决
**入参**，出参仍按仓库惯例输出 snake_case，避免同一个响应里出现两套命名。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

DecisionPoint = Literal["DP1", "DP2", "DP3", "DP4", "DP5"]
DecisionSubjectType = Literal["TARGET", "POCKET", "CANDIDATE_SET", "STRUCTURE"]


class DecisionSnapshotItem(BaseModel):
    """成员快照的一行：候选物 + 决策当时的评分与排名。

    快照由前端在结果页提交，服务端只做归属校验（见
    ``app.services.decisions.create_decision``），不重新计算评分——重新算出来的
    是「现在」的分，而决策记录要保存的是「当时」的分。
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(
        min_length=1,
        max_length=36,
        validation_alias=AliasChoices("candidate_id", "candidateId"),
    )
    score: float | None = None
    rank: int | None = Field(default=None, ge=1)


class DecisionCreate(BaseModel):
    """提交一次研发决策（``POST /projects/{id}/decisions``，docs/05 §3.3）。

    ``reason`` 必填且不能是空白：决策记录的价值全在「为什么这么选」，一条没有理由
    的记录在复盘时等于没有记录。``snapshot`` 同样必填——理由可以事后补，当时的分
    不能事后重建（候选集合会被改写，``candidate_set_items`` 的成员会变）。
    """

    model_config = ConfigDict(extra="forbid")

    decision_point: DecisionPoint = Field(
        validation_alias=AliasChoices("decision_point", "decisionPoint"),
    )
    subject_type: DecisionSubjectType = Field(
        validation_alias=AliasChoices("subject_type", "subjectType"),
    )
    subject_id: str = Field(
        min_length=1,
        max_length=36,
        validation_alias=AliasChoices("subject_id", "subjectId"),
    )
    selected_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("selected_ids", "selectedIds"),
    )
    excluded_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("excluded_ids", "excludedIds"),
    )
    basis_task_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("basis_task_ids", "basisTaskIds"),
    )
    basis_metrics: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("basis_metrics", "basisMetrics"),
    )
    reason: str = Field(min_length=1, max_length=4000)
    snapshot: list[DecisionSnapshotItem] = Field(
        validation_alias=AliasChoices("snapshot",),
    )

    @model_validator(mode="after")
    def validate_verdicts(self) -> "DecisionCreate":
        if not self.reason.strip():
            raise ValueError("决策理由不能为空")
        if not self.selected_ids and not self.excluded_ids:
            raise ValueError("selected_ids 与 excluded_ids 不能同时为空")
        if not self.snapshot:
            raise ValueError("snapshot 不能为空：决策记录必须保存成员快照")

        snapshot_ids = [item.candidate_id for item in self.snapshot]
        if len(set(snapshot_ids)) != len(snapshot_ids):
            raise ValueError("snapshot 中的 candidate_id 不能重复")

        verdict_ids = set(self.selected_ids) | set(self.excluded_ids)
        if set(self.selected_ids) & set(self.excluded_ids):
            raise ValueError("同一个 candidate_id 不能同时入选与淘汰")
        if not set(snapshot_ids) <= verdict_ids:
            # docs/05 §3.3 的示例里 snapshot 只覆盖部分成员（快照可以是子集），但反
            # 过来不行：一条既没入选也没淘汰的快照行无法落成 decision_item 的 verdict。
            raise ValueError("snapshot 中的 candidate_id 必须出现在 selected_ids 或 excluded_ids 中")
        return self


__all__ = [
    "DecisionCreate",
    "DecisionPoint",
    "DecisionSnapshotItem",
    "DecisionSubjectType",
]
