"""对象存储生命周期规则（docs/03 §4.5、docs/04 §5.8、docs/15 §3.2）。

为什么需要第二道保险
--------------------
平台自己已经有两处清理：``upload_sessions.expires_at`` 的三个业务入口校验、
以及 ``app.services.upload_maintenance`` 的定时巡检。但它们都跑在 **backend 进程**
里——进程停摆、任务被停用、或者运维把 ``UPLOAD_SWEEP_ENABLED`` 关掉，暂存分片就会
无声地长期占盘。``docs/15`` §3.2 把这条列为「运维最常漏的一条」（对应 ``14`` C-13）：
``drp-temp`` 若不清理，失败的上传会一直占着对象存储。

对象存储侧的生命周期规则由存储服务自己执行，与平台进程是否存活无关，所以它是最后
一道保险，而不是平台清理的替代品。两处都要有：平台侧清理能立刻回收（用户重试时
空间已经回来），存储侧规则兜住「平台没跑起来」的时间窗。

单桶 + 前缀 与文档里的多桶
--------------------------
``docs/03`` §4.5 与 ``docs/15`` §3.2 描述的是**目标态多桶**拓扑（``drp-assets`` /
``drp-results`` / ``drp-bulk`` / ``drp-logs`` / ``drp-temp`` / ``drp-models``）。
本仓库当前只有**一个桶**（``settings.MINIO_BUCKET``，默认 ``scitool-files``），
不同用途靠**对象键前缀**区分。两者的映射关系：

===========================  ==========================================  ==================================
文档里的桶                    本仓库实际前缀                                由谁写入
===========================  ==========================================  ==================================
``drp-temp``                 ``_uploads/``                                ``app.files.part_staging``
``drp-assets``（输入资产）    ``inputs/files/``                            ``app.files.writer``
``drp-results``（计算结果）   ``organizations/…/artifacts/``、``executions/``  ``app.services.artifacts``、K8s 产物回收
``drp-bulk``（MD 轨迹）       ``executions/`` 内的大文件                     同上（当前无独立前缀）
``drp-logs``                 尚未落对象存储（日志在本地文件 + ``audit_logs`` 表）
===========================  ==========================================  ==================================

因此本模块的规则按**前缀**表达。将来真的拆成多桶时，只要把 ``bucket`` 换掉、
前缀改短，规则语义不变——这也是把「桶」与「前缀」都做成参数的原因。

为什么默认不配「转低频」
------------------------
``docs/03`` §4.5 要求 ``drp-assets`` 30 天未引用转低频、``drp-results`` 90 天转低频、
``drp-bulk`` 180 天。但 **MinIO 是单层存储**：``Transition`` 指向的 storage class 必须
先用 ``mc ilm tier add`` 建出远程层，否则 ``set_bucket_lifecycle`` 会整体被拒——一条
配错的过渡规则会把「临时区 7 天清分片」这种关键规则一起带下水。

所以过渡规则默认**不生成**（``MINIO_LIFECYCLE_TRANSITION_STORAGE_CLASS`` 为空即跳过），
只生成两类真正安全且当前部署必然生效的规则：

* ``_uploads/`` 的 ``AbortIncompleteMultipartUpload(7)`` + ``Expiration(30)``；
* 各业务前缀的 ``NoncurrentVersionExpiration``（仅当桶开启了版本化才有意义）。

等甲方 MinIO 配好分层存储后，把 storage class 填进配置即可一并启用过渡规则。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.config import settings

logger = logging.getLogger(__name__)

#: 平台自己生成的对象键前缀（与 ``part_staging``/``writer``/``artifacts`` 保持一致）。
TEMP_PREFIX = "_uploads/"
INPUT_ASSET_PREFIX = "inputs/files/"
ARTIFACT_PREFIX = "organizations/"
EXECUTION_PREFIX = "executions/"

#: 规则 id 前缀。用固定前缀是为了**只接管自己的规则**：运维手工加的规则、
#: 备份策略加的规则，一律原样保留（见 ``merge_rules``）。
RULE_ID_PREFIX = "aidd-"

#: 规则 id。写死而不是拼接前缀，因为改前缀就等于换规则，审计时需要能对上号。
RULE_ID_TEMP = f"{RULE_ID_PREFIX}temp-scratch"
RULE_ID_INPUT_ASSETS = f"{RULE_ID_PREFIX}input-assets"
RULE_ID_ARTIFACTS = f"{RULE_ID_PREFIX}artifacts"
RULE_ID_EXECUTIONS = f"{RULE_ID_PREFIX}executions"

#: docs/04 §5.8 明文要求：未完成分片 7 天、对象 30 天。
DEFAULT_ABORT_INCOMPLETE_DAYS = 7
DEFAULT_TEMP_EXPIRATION_DAYS = 30

#: docs/15 §3.2 要求「版本 ≥ 90 天」。
DEFAULT_NONCURRENT_KEEP_DAYS = 90

#: docs/03 §4.5 的过渡天数。仅在显式配置 storage class 时生效。
DEFAULT_INPUT_TRANSITION_DAYS = 30
DEFAULT_ARTIFACT_TRANSITION_DAYS = 90
DEFAULT_EXECUTION_TRANSITION_DAYS = 180


@dataclass(frozen=True)
class LifecycleRuleSpec:
    """一条生命周期规则的后端无关描述。

    刻意不直接用 ``minio.lifecycleconfig.Rule``：规则表要能被单元测试、CLI 的
    ``--dry-run`` 与文档表格直接比对，绑到 SDK 对象上就得先构造 SDK 才能看一眼。
    """

    rule_id: str
    prefix: str
    expiration_days: Optional[int] = None
    abort_incomplete_multipart_days: Optional[int] = None
    noncurrent_expiration_days: Optional[int] = None
    transition_days: Optional[int] = None
    transition_storage_class: Optional[str] = None
    #: 版本化桶上，``Expiration`` 只会留下删除标记；要真正回收还得让它清标记。
    expired_object_delete_marker: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "prefix": self.prefix,
            "expirationDays": self.expiration_days,
            "abortIncompleteMultipartDays": self.abort_incomplete_multipart_days,
            "noncurrentExpirationDays": self.noncurrent_expiration_days,
            "transitionDays": self.transition_days,
            "transitionStorageClass": self.transition_storage_class,
            "expiredObjectDeleteMarker": self.expired_object_delete_marker,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class LifecyclePlan:
    """一次 ``apply`` 的计划与结果，供 CLI 打印与测试断言。"""

    bucket: str
    rules: list[LifecycleRuleSpec] = field(default_factory=list)
    #: 运维自己加的规则（id 不以 ``aidd-`` 开头），原样保留。
    preserved_rule_ids: list[str] = field(default_factory=list)
    #: 本次实际是否写入。规则完全一致时为 False——重复执行不该产生写操作。
    changed: bool = False
    applied: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "rules": [rule.to_dict() for rule in self.rules],
            "preservedRuleIds": list(self.preserved_rule_ids),
            "changed": self.changed,
            "applied": self.applied,
            "reason": self.reason,
        }


def _positive_or_none(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    number = int(value)
    return number if number > 0 else None


def default_lifecycle_rules(
    *,
    transition_storage_class: Optional[str] = None,
    temp_expiration_days: int = DEFAULT_TEMP_EXPIRATION_DAYS,
    abort_incomplete_days: int = DEFAULT_ABORT_INCOMPLETE_DAYS,
    noncurrent_keep_days: int = DEFAULT_NONCURRENT_KEEP_DAYS,
    input_transition_days: int = DEFAULT_INPUT_TRANSITION_DAYS,
    artifact_transition_days: int = DEFAULT_ARTIFACT_TRANSITION_DAYS,
    execution_transition_days: int = DEFAULT_EXECUTION_TRANSITION_DAYS,
) -> list[LifecycleRuleSpec]:
    """构造默认规则表。

    ``transition_storage_class`` 为空时**不生成任何过渡规则**（见模块 docstring
    里「为什么默认不配转低频」）。这样默认配置在单层 MinIO 上一定能写成功。
    """

    storage_class = (transition_storage_class or "").strip() or None
    expiration_days = _positive_or_none(temp_expiration_days)
    noncurrent_days = _positive_or_none(noncurrent_keep_days)
    # `abort_incomplete_days` 仍保留在签名里是为了不破坏既有调用方，
    # 但**不再生成 AbortIncompleteMultipartUpload**，原因见下面规则 1 的注释。
    _ = abort_incomplete_days

    rules: list[LifecycleRuleSpec] = []

    # 1. 分片暂存区：唯一一条会真正删数据的规则，只作用于平台自己的临时前缀。
    #
    # 这里**不配 AbortIncompleteMultipartUpload**，两条理由都有实测依据：
    #   a) 本仓库的分片上传是「对象级暂存」（`_uploads/<session>/00001.part`，见
    #      `backend/app/files/part_staging.py`），从头到尾没有用 S3 原生 Multipart
    #      Upload，因此压根不存在「未完成的分片上传」这种东西可中止。
    #   b) 本机实测的 MinIO（DEVELOPMENT.2025-05-24，`mc ilm rule add` 无对应选项）
    #      不接受该动作：只带 abort 的规则 PUT 400 `InvalidArgument`，与 Expiration
    #      一起提交时被**静默丢弃**——配置看上去生效了，实际什么也没做。
    # 所以「未完成的暂存分片」由 Expiration(30 天) 兜底清理，平台侧还有
    # `app.services.upload_maintenance` 的巡检做第一道处理。
    if expiration_days is not None or noncurrent_days is not None:
        rules.append(
            LifecycleRuleSpec(
                rule_id=RULE_ID_TEMP,
                prefix=TEMP_PREFIX,
                expiration_days=expiration_days,
                noncurrent_expiration_days=noncurrent_days,
                notes="分片上传暂存（docs/04 §5.8：暂存对象 30 天过期）",
            )
        )

    # 2. 输入资产：只允许过渡到低频，**绝不配 Expiration**——那是用户上传的原始数据。
    rules.append(
        LifecycleRuleSpec(
            rule_id=RULE_ID_INPUT_ASSETS,
            prefix=INPUT_ASSET_PREFIX,
            transition_days=(
                _positive_or_none(input_transition_days) if storage_class else None
            ),
            transition_storage_class=storage_class,
            noncurrent_expiration_days=noncurrent_days,
            notes="输入资产（docs/03 §4.5：30 天未引用转低频；不配过期）",
        )
    )

    # 3. 计算结果产物：同上，只过渡不删除。
    rules.append(
        LifecycleRuleSpec(
            rule_id=RULE_ID_ARTIFACTS,
            prefix=ARTIFACT_PREFIX,
            transition_days=(
                _positive_or_none(artifact_transition_days) if storage_class else None
            ),
            transition_storage_class=storage_class,
            noncurrent_expiration_days=noncurrent_days,
            notes="计算结果与报告（docs/03 §4.5：90 天转低频；不配过期）",
        )
    )

    # 4. 执行产物（含 MD 轨迹这类 GB 级大文件）：180 天转低频。
    rules.append(
        LifecycleRuleSpec(
            rule_id=RULE_ID_EXECUTIONS,
            prefix=EXECUTION_PREFIX,
            transition_days=(
                _positive_or_none(execution_transition_days) if storage_class else None
            ),
            transition_storage_class=storage_class,
            noncurrent_expiration_days=noncurrent_days,
            notes="执行产物与 MD 轨迹（docs/03 §4.5：180 天转低频）",
        )
    )

    return [rule for rule in rules if _has_action(rule)]


def _has_action(rule: LifecycleRuleSpec) -> bool:
    """至少有一个动作，否则 SDK 会在构造 ``Rule`` 时直接抛 ``ValueError``。"""

    return any(
        value is not None
        for value in (
            rule.expiration_days,
            rule.abort_incomplete_multipart_days,
            rule.noncurrent_expiration_days,
            rule.transition_days,
        )
    )


def is_platform_rule(rule_id: Optional[str]) -> bool:
    """判断某条规则是否由平台管理（决定要不要覆盖它）。"""

    return bool(rule_id) and str(rule_id).startswith(RULE_ID_PREFIX)


def build_lifecycle_config(rules: Iterable[LifecycleRuleSpec]):
    """把规则表转成 MinIO SDK 的 ``LifecycleConfig``。

    延迟导入 SDK：本地后端（``STORAGE_BACKEND=local``）不该因为没装 minio 就
    连模块都 import 不了。
    """

    from minio.commonconfig import ENABLED, Filter
    from minio.lifecycleconfig import (
        AbortIncompleteMultipartUpload,
        Expiration,
        LifecycleConfig,
        NoncurrentVersionExpiration,
        Rule,
        Transition,
    )

    sdk_rules = []
    for spec in rules:
        if not _has_action(spec):
            continue
        sdk_rules.append(
            Rule(
                ENABLED,
                Filter(prefix=spec.prefix) if spec.prefix else Filter(),
                rule_id=spec.rule_id,
                abort_incomplete_multipart_upload=(
                    AbortIncompleteMultipartUpload(spec.abort_incomplete_multipart_days)
                    if spec.abort_incomplete_multipart_days
                    else None
                ),
                expiration=(
                    Expiration(
                        days=spec.expiration_days,
                        # S3 规范：ExpiredObjectDeleteMarker 不能与 Days 同时出现
                        # （真 MinIO 报 `InvalidArgument: Delete marker cannot be
                        # specified with Days or Date in a Lifecycle Expiration
                        # Policy`）。二者同时配置时只保留 Days——过期对象本身已被
                        # 删除，残留的删除标记不影响占用，清理它是锦上添花。
                        expired_object_delete_marker=(
                            True
                            if spec.expired_object_delete_marker
                            and not spec.expiration_days
                            else None
                        ),
                    )
                    if spec.expiration_days or spec.expired_object_delete_marker
                    else None
                ),
                noncurrent_version_expiration=(
                    NoncurrentVersionExpiration(spec.noncurrent_expiration_days)
                    if spec.noncurrent_expiration_days
                    else None
                ),
                transition=(
                    Transition(
                        days=spec.transition_days,
                        storage_class=spec.transition_storage_class,
                    )
                    if spec.transition_days and spec.transition_storage_class
                    else None
                ),
            )
        )
    return LifecycleConfig(sdk_rules)


def rule_signature(rule: Any) -> tuple:
    """把 SDK ``Rule`` 压成可比较的元组，用于判断「是否需要重写」。

    不依赖 ``toxml()`` 的字符串输出：属性顺序或命名空间的变化会让字符串变、
    但语义没变，那样每次 apply 都会误判成「已变更」并多写一次。
    """

    rule_filter = getattr(rule, "rule_filter", None)
    prefix = getattr(rule_filter, "prefix", None) or ""
    expiration = getattr(rule, "expiration", None)
    abort = getattr(rule, "abort_incomplete_multipart_upload", None)
    noncurrent = getattr(rule, "noncurrent_version_expiration", None)
    transition = getattr(rule, "transition", None)
    return (
        str(getattr(rule, "rule_id", "") or ""),
        str(prefix),
        str(getattr(getattr(rule, "status", None), "value", getattr(rule, "status", ""))),
        getattr(expiration, "days", None) if expiration else None,
        bool(getattr(expiration, "expired_object_delete_marker", False)) if expiration else False,
        getattr(abort, "days_after_initiation", None) if abort else None,
        getattr(noncurrent, "noncurrent_days", None) if noncurrent else None,
        getattr(transition, "days", None) if transition else None,
        getattr(transition, "storage_class", None) if transition else None,
    )


def spec_signature(spec: LifecycleRuleSpec) -> tuple:
    """``LifecycleRuleSpec`` 侧的同一份签名，便于与 ``rule_signature`` 对照。"""

    return (
        spec.rule_id,
        spec.prefix or "",
        "Enabled",
        spec.expiration_days,
        bool(spec.expired_object_delete_marker) if spec.expiration_days else False,
        spec.abort_incomplete_multipart_days,
        spec.noncurrent_expiration_days,
        spec.transition_days if spec.transition_storage_class else None,
        spec.transition_storage_class if spec.transition_days else None,
    )


def merge_rules(
    desired: Iterable[LifecycleRuleSpec],
    existing: Optional[Any],
) -> tuple[list[Any], list[str], bool]:
    """把「想写的规则」与「桶上已有的规则」合并。

    返回 ``(待写入的 SDK Rule 列表, 保留的运维规则 id 列表, 是否有变化)``。

    合并规则：
    * id 以 ``aidd-`` 开头 → 平台接管，用新定义覆盖；
    * 其它 id（运维/备份策略加的）→ **原样保留**，绝不删除；
    * 平台规则若与现有定义完全一致 → 不重写（幂等，避免每次启动都写一次桶配置）。
    """

    desired_list = [spec for spec in desired if _has_action(spec)]
    desired_by_id = {spec.rule_id: spec for spec in desired_list}

    existing_rules = list(getattr(existing, "rules", None) or []) if existing else []
    existing_by_id: dict[str, Any] = {}
    preserved: list[Any] = []
    preserved_ids: list[str] = []
    for rule in existing_rules:
        rule_id = str(getattr(rule, "rule_id", "") or "")
        if is_platform_rule(rule_id):
            existing_by_id[rule_id] = rule
        else:
            preserved.append(rule)
            preserved_ids.append(rule_id)

    changed = False
    for spec in desired_list:
        current = existing_by_id.get(spec.rule_id)
        if current is None:
            changed = True
            break
        if rule_signature(current) != spec_signature(spec):
            changed = True
            break

    # 平台曾经写过、这次不再需要的规则（例如关掉了过渡）：也算变化。
    if not changed and set(existing_by_id) - set(desired_by_id):
        changed = True

    if changed:
        merged = list(preserved) + list(build_lifecycle_config(desired_list).rules)
    else:
        merged = list(existing_rules)
    return merged, preserved_ids, changed


def _backend_supports_lifecycle(backend: Any) -> bool:
    return callable(getattr(backend, "set_bucket_lifecycle", None)) and callable(
        getattr(backend, "get_bucket_lifecycle", None)
    )


async def _delete_lifecycle(backend: Any, bucket: str) -> None:
    """清空桶的生命周期配置。

    优先用 S3 的 DeleteBucketLifecycle（``delete_bucket_lifecycle``）；后端没有这个
    方法时退回「写一份空配置」，只为兼容测试替身——真 MinIO 会拒绝空配置（见
    ``MinIOStorageBackend.delete_bucket_lifecycle`` 的注释）。
    """

    delete = getattr(backend, "delete_bucket_lifecycle", None)
    if callable(delete):
        await delete(bucket)
        return
    from minio.lifecycleconfig import LifecycleConfig

    await backend.set_bucket_lifecycle(bucket, LifecycleConfig([]))


def resolve_rules(
    *,
    transition_storage_class: Optional[str] = None,
    **overrides: int,
) -> list[LifecycleRuleSpec]:
    """按配置构造规则表；显式入参优先于 ``settings``。"""

    storage_class = transition_storage_class
    if storage_class is None:
        storage_class = getattr(settings, "MINIO_LIFECYCLE_TRANSITION_STORAGE_CLASS", None)
    return default_lifecycle_rules(
        transition_storage_class=storage_class,
        temp_expiration_days=overrides.get(
            "temp_expiration_days",
            getattr(settings, "MINIO_LIFECYCLE_TEMP_EXPIRATION_DAYS", DEFAULT_TEMP_EXPIRATION_DAYS),
        ),
        abort_incomplete_days=overrides.get(
            "abort_incomplete_days",
            getattr(
                settings,
                "MINIO_LIFECYCLE_ABORT_INCOMPLETE_DAYS",
                DEFAULT_ABORT_INCOMPLETE_DAYS,
            ),
        ),
        noncurrent_keep_days=overrides.get(
            "noncurrent_keep_days",
            getattr(settings, "MINIO_LIFECYCLE_NONCURRENT_KEEP_DAYS", DEFAULT_NONCURRENT_KEEP_DAYS),
        ),
    )


async def plan_lifecycle(
    backend: Any = None,
    *,
    bucket: Optional[str] = None,
    rules: Optional[Iterable[LifecycleRuleSpec]] = None,
) -> LifecyclePlan:
    """只读：算出「如果要应用，会写什么、会保留什么」。"""

    target = bucket or settings.MINIO_BUCKET
    specs = list(rules) if rules is not None else resolve_rules()

    if backend is None:
        from app.storage.factory import get_storage_backend

        backend = get_storage_backend()

    if not _backend_supports_lifecycle(backend):
        return LifecyclePlan(
            bucket=target,
            rules=specs,
            reason="当前存储后端不支持生命周期规则（仅 minio 支持）",
        )

    existing = await backend.get_bucket_lifecycle(target)
    _, preserved_ids, changed = merge_rules(specs, existing)
    return LifecyclePlan(
        bucket=target,
        rules=specs,
        preserved_rule_ids=preserved_ids,
        changed=changed,
        reason="规则与桶上现有配置一致，无需写入" if not changed else "存在差异，需要写入",
    )


async def apply_lifecycle(
    backend: Any = None,
    *,
    bucket: Optional[str] = None,
    rules: Optional[Iterable[LifecycleRuleSpec]] = None,
    dry_run: bool = False,
) -> LifecyclePlan:
    """应用生命周期规则（幂等）。

    ``dry_run=True`` 时只返回计划，绝不写桶。
    """

    target = bucket or settings.MINIO_BUCKET
    specs = list(rules) if rules is not None else resolve_rules()

    if backend is None:
        from app.storage.factory import get_storage_backend

        backend = get_storage_backend()

    if not _backend_supports_lifecycle(backend):
        return LifecyclePlan(
            bucket=target,
            rules=specs,
            reason="当前存储后端不支持生命周期规则（仅 minio 支持）",
        )

    existing = await backend.get_bucket_lifecycle(target)
    merged, preserved_ids, changed = merge_rules(specs, existing)

    plan = LifecyclePlan(
        bucket=target,
        rules=specs,
        preserved_rule_ids=preserved_ids,
        changed=changed,
        reason="规则与桶上现有配置一致，无需写入" if not changed else "存在差异，需要写入",
    )
    if dry_run or not changed:
        return plan

    if not merged:
        # 一条规则都不需要（例如所有时间窗都被配成 0）：S3 语义里这对应「删除配置」，
        # 而不是写一份空配置——真 MinIO 会以
        # `InvalidArgument: Lifecycle configuration should have at least one rule` 拒绝。
        await _delete_lifecycle(backend, target)
        logger.info("已删除对象存储生命周期规则: bucket=%s", target)
        return LifecyclePlan(
            bucket=plan.bucket,
            rules=plan.rules,
            preserved_rule_ids=plan.preserved_rule_ids,
            changed=True,
            applied=True,
            reason="已删除配置",
        )

    from minio.lifecycleconfig import LifecycleConfig

    await backend.set_bucket_lifecycle(target, LifecycleConfig(merged))
    logger.info(
        "已写入对象存储生命周期规则: bucket=%s rules=%s preserved=%s",
        target,
        [spec.rule_id for spec in specs if _has_action(spec)],
        preserved_ids,
    )
    return LifecyclePlan(
        bucket=plan.bucket,
        rules=plan.rules,
        preserved_rule_ids=plan.preserved_rule_ids,
        changed=True,
        applied=True,
        reason="已写入",
    )


async def ensure_lifecycle_on_startup() -> Optional[LifecyclePlan]:
    """启动时按配置应用一次（默认关闭）。

    失败只告警不阻断启动：生命周期规则缺失会多占存储，但不该让整个平台起不来。
    """

    if not getattr(settings, "MINIO_LIFECYCLE_APPLY_ON_STARTUP", False):
        return None
    if settings.STORAGE_BACKEND != "minio":
        return None
    try:
        plan = await apply_lifecycle()
    except Exception:  # noqa: BLE001 - 生命周期配置失败不阻断启动
        logger.warning("启动时应用对象存储生命周期规则失败（不影响启动）", exc_info=True)
        return None
    if plan.changed:
        logger.info("启动时已同步对象存储生命周期规则: bucket=%s", plan.bucket)
    return plan


__all__ = [
    "ARTIFACT_PREFIX",
    "DEFAULT_ABORT_INCOMPLETE_DAYS",
    "DEFAULT_TEMP_EXPIRATION_DAYS",
    "EXECUTION_PREFIX",
    "INPUT_ASSET_PREFIX",
    "LifecyclePlan",
    "LifecycleRuleSpec",
    "RULE_ID_ARTIFACTS",
    "RULE_ID_EXECUTIONS",
    "RULE_ID_INPUT_ASSETS",
    "RULE_ID_PREFIX",
    "RULE_ID_TEMP",
    "TEMP_PREFIX",
    "apply_lifecycle",
    "build_lifecycle_config",
    "default_lifecycle_rules",
    "ensure_lifecycle_on_startup",
    "is_platform_rule",
    "merge_rules",
    "plan_lifecycle",
    "resolve_rules",
    "rule_signature",
    "spec_signature",
]
