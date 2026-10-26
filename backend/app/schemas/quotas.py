"""项目配额的请求体（docs/04 §5.3、docs/05 §3 ``PUT /projects/{id}/quota``）。

两套命名都收
------------
规格文档用 camelCase（``dailyQuotaMinutes``），而平台既有端点与库列用 snake_case
（``daily_quota_minutes``）。这里用 ``AliasChoices`` 同时接受两者，且
``populate_by_name=True`` 让 ``model_dump()`` 仍按字段名输出 snake_case——
服务层只认 snake_case 一个口径，命名差异在 schema 边界上就消化掉，不往下传。

为什么不允许「一个字段都不传」
------------------------------
PUT 语义是「设置」，空请求体要么是客户端 bug，要么是想「恢复默认」。后者不该
用空 PUT 表达（会让人以为配额被重置了，实际什么都没改），所以直接 422。
"""

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

#: 与 ``app.models.quotas.QUOTA_PERIODS`` 同值；此处独立声明是为了让 schema
#: 不依赖 models 层（schema 只表达契约，不 import 任何 ORM 模块）。
QuotaPeriod = Literal["DAILY", "MONTHLY", "NONE"]


class ProjectQuotaUpdate(BaseModel):
    """部分更新项目配额：只传要改的字段。"""

    max_concurrent_dcu: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("max_concurrent_dcu", "maxConcurrentDcu"),
    )
    max_concurrent_cpu_tasks: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices(
            "max_concurrent_cpu_tasks", "maxConcurrentCpuTasks"
        ),
    )
    daily_quota_minutes: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("daily_quota_minutes", "dailyQuotaMinutes"),
    )
    max_single_task_minutes: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("max_single_task_minutes", "maxSingleTaskMinutes"),
    )
    quota_period: QuotaPeriod | None = Field(
        default=None,
        validation_alias=AliasChoices("quota_period", "quotaPeriod"),
    )
    #: **放宽拒绝线，不是告警阈值**：``1.00`` = 用完即拒；``1.20`` = 用到 120% 才拒。
    #: 超额本身不产生告警/指标（见 ``app.models.quotas`` 模块 docstring）。
    #: 下界与上界在服务层校验（``ValidationException``，422），这里只做类型约束。
    overdraft_ratio: float | None = Field(
        default=None,
        validation_alias=AliasChoices("overdraft_ratio", "overdraftRatio"),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("至少需要修改一项配额字段")
        return self
