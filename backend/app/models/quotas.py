"""项目算力配额（docs/04 §5.3、docs/03 §5.6.3③、docs/05 §3/§9）。

为什么配额是「软上限」
--------------------
配额存在的目的是**让算力分配可预期**，不是做硬性拒绝。因此：

* 超额**不回杀**已经在跑的任务——一个跑了 6 小时的 MD 任务因为配额到点被 kill，
  代价远高于多花的那点算力，而且用户完全无法预期；
* 超额只做两件事：**阻塞新提交**（`app.services.project_quotas.check_submission_allowed`）
  与**打一条 WARNING 日志**（跨过 100% 时）。日志里没有站内信/邮件/指标通道——
  那需要新建推送设施，超出本期范围。用户侧可见信号是提交被拒时的 `429` `detail`
  与 `GET /projects/{id}/quota` 的 `exceeded`。

`overdraft_ratio` **不是告警阈值，它只放宽拒绝线**。`1.00` = 一用完就拒，
`1.20` = 可以用到 120% 才拒；告警线固定在 100%（`daily_quota_minutes` 本身）。
docs/04:261 的「超 20% 后告警」由此落地为「100% 起告警（日志）、
`limit × ratio` 起拒绝」，两者不是同一条线，改注释别改回去。

为什么按「算力分钟」而不是任务个数
--------------------------------
按任务个数计量时，一个 10 万条的批量筛选与一个单分子对接等价，配额形同虚设。
算力分钟按 `实际时长 × 实际卡数/核数` 折算（系数见 `app.services.project_quotas`），
失败与取消同样核销——否则可以反复失败来白嫖算力。

表名用复数 `project_quotas`，与 `projects` / `project_members` / `idempotency_keys`
等既有表保持一致。
"""

from decimal import Decimal

from sqlalchemy import Column, ForeignKey, Index, Integer, Numeric, String

from app.database.base import Base, TimestampMixin, UUIDMixin

#: 配额周期：日 / 月 / 不限。XL 层任务（≥1 万件）建议项目级改用 `MONTHLY`，
#: 否则一个 XL 就能把日配额一次性打穿（docs/04 §5.3）。
QUOTA_PERIOD_DAILY = "DAILY"
QUOTA_PERIOD_MONTHLY = "MONTHLY"
QUOTA_PERIOD_NONE = "NONE"
QUOTA_PERIODS = (QUOTA_PERIOD_DAILY, QUOTA_PERIOD_MONTHLY, QUOTA_PERIOD_NONE)

#: 各字段默认值集中在此，模型默认值、`get_or_create` 与迁移脚本共用一份口子，
#: 避免「建表默认 2、业务代码默认 4」这种漂移。
DEFAULT_MAX_CONCURRENT_DCU = 2
DEFAULT_MAX_CONCURRENT_CPU_TASKS = 10
DEFAULT_DAILY_QUOTA_MINUTES = 0
DEFAULT_MAX_SINGLE_TASK_MINUTES = 1440
DEFAULT_QUOTA_PERIOD = QUOTA_PERIOD_DAILY
DEFAULT_OVERDRAFT_RATIO = Decimal("1.00")


class ProjectQuota(Base, UUIDMixin, TimestampMixin):
    """项目配额（一个项目一份，`project_id` 唯一）。"""

    __tablename__ = "project_quotas"
    # 唯一约束只放在 `__table_args__`（与 `models/decisions.py`、`models/idempotency.py`
    # 同一约定）：列上再写 `unique=True`/`index=True` 会让 `Base.metadata.create_all`
    # （开发/测试）与 Alembic（生产）产生同名索引的两种来源，漂移只在生产暴露。
    __table_args__ = (
        Index("ix_project_quotas_project_id", "project_id", unique=True),
    )

    project_id = Column(
        String(36),
        ForeignKey("projects.id"),
        nullable=False,
    )
    #: 同时在跑的 DCU 任务数上限（1 任务 1 卡口径）。
    max_concurrent_dcu = Column(
        Integer, nullable=False, default=2, server_default="2"
    )
    #: 同时在跑的 CPU 任务数上限（含 QUEUED，排队也算占用名额）。
    max_concurrent_cpu_tasks = Column(
        Integer, nullable=False, default=10, server_default="10"
    )
    #: 每个配额周期内的算力分钟上限；**0 = 不限**。单位是算力分钟而不是任务数、
    #: 也不是墙钟分钟（docs/03 §5.6.3③）。
    daily_quota_minutes = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: 单任务墙钟时长上限（分钟），0 = 不限。
    #: 执行点在准入（`check_submission_allowed`）：比较本次提交资源快照里声明的
    #: `timeout_sec` 与该上限，超了直接拒（429，`detail.dimension =
    #: "maxSingleTaskMinutes"`）。**不做运行期 kill** —— 那需要 executor 侧配合，
    #: 本期不实现，所以「置 TIMEOUT」这句只能指「超时不再下发」。
    max_single_task_minutes = Column(
        Integer, nullable=False, default=1440, server_default="1440"
    )
    quota_period = Column(
        String(16), nullable=False, default=QUOTA_PERIOD_DAILY,
        server_default=QUOTA_PERIOD_DAILY,
    )
    #: **只用来放宽拒绝线，不是告警阈值**：达到 `limit × ratio` 才拒绝新提交，
    #: 已在跑的一律不动。`1.00` = 用完即拒，`1.20` = 用到 120% 才拒。
    #: 超额本身不产生任何告警/指标（见模块 docstring）。
    overdraft_ratio = Column(
        Numeric(4, 2), nullable=False, default=DEFAULT_OVERDRAFT_RATIO,
        server_default="1.00",
    )
    #: 最后修改配额的人（审计用）。故意不建外键：用户被删后仍要能回答
    #: 「这份配额是谁在什么时候定的」。
    updated_by = Column(String(36), nullable=True)


__all__ = [
    "DEFAULT_DAILY_QUOTA_MINUTES",
    "DEFAULT_MAX_CONCURRENT_CPU_TASKS",
    "DEFAULT_MAX_CONCURRENT_DCU",
    "DEFAULT_MAX_SINGLE_TASK_MINUTES",
    "DEFAULT_OVERDRAFT_RATIO",
    "DEFAULT_QUOTA_PERIOD",
    "QUOTA_PERIODS",
    "QUOTA_PERIOD_DAILY",
    "QUOTA_PERIOD_MONTHLY",
    "QUOTA_PERIOD_NONE",
    "ProjectQuota",
]
