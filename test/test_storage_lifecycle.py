"""对象存储生命周期规则测试（G-12，docs/04 §5.8、docs/03 §4.5、docs/15 §3.2）。

关键回归点
----------
1. **``_uploads/`` 必须有一条真的删除规则**（7 天 abort 未完成分片 + 30 天过期对象）——
   这是 docs/04 §5.8 的明文要求，也是 ``docs/15`` 说的「运维最常漏的一条」。
2. **业务前缀绝不能配 Expiration**：``inputs/files/``（用户上传的原始资产）与
   ``organizations/``（计算结果）一旦被配成过期删除，就是数据丢失。
3. **运维自己加的规则必须保留**：平台只接管 id 以 ``aidd-`` 开头的规则。
4. **幂等**：桶上已是目标配置时不产生写操作（否则每次部署都动一次生产存储）。
5. **过渡规则默认不生成**：MinIO 单层存储下过渡目标不存在会让整份
   lifecycle 被拒，把「清分片」这条关键规则一起带下水。
"""

from __future__ import annotations

import asyncio

import pytest

from app.storage.lifecycle import (
    INPUT_ASSET_PREFIX,
    RULE_ID_ARTIFACTS,
    RULE_ID_EXECUTIONS,
    RULE_ID_INPUT_ASSETS,
    RULE_ID_TEMP,
    TEMP_PREFIX,
    LifecycleRuleSpec,
    apply_lifecycle,
    build_lifecycle_config,
    default_lifecycle_rules,
    is_platform_rule,
    merge_rules,
    plan_lifecycle,
    resolve_rules,
    rule_signature,
    spec_signature,
)


class _FakeBackend:
    """最小可用的存储后端替身：只实现生命周期两个方法。"""

    def __init__(self, existing=None, supports_delete=False):
        self.existing = existing
        self.written = []
        self.deleted = []
        if supports_delete:
            self.delete_bucket_lifecycle = self._delete

    async def _delete(self, bucket):
        self.deleted.append(bucket)
        self.existing = None

    async def get_bucket_lifecycle(self, bucket):
        return self.existing

    async def set_bucket_lifecycle(self, bucket, config):
        self.written.append((bucket, config))
        self.existing = config


class _NoLifecycleBackend:
    """模拟本地后端：没有桶概念。"""


def _rules_by_id(rules):
    return {rule.rule_id: rule for rule in rules}


# --------------------------------------------------------------------------- #
# 规则表本身
# --------------------------------------------------------------------------- #


def test_temp_prefix_expires_without_multipart_abort():
    """暂存区要有过期规则，且**不得**再带 AbortIncompleteMultipartUpload。

    两条实测依据（本机 MinIO DEVELOPMENT.2025-05-24）：
    * 本仓库分片是对象级暂存（``_uploads/<session>/00001.part``），不存在 S3
      原生 Multipart Upload，没有「未完成分片上传」可中止；
    * 该版本 MinIO 不接受这个动作：只带 abort 的规则 PUT 400，与 Expiration 一起
      提交时被静默丢弃（写进去读不回来，配置看着生效其实没做）。
    """

    rules = _rules_by_id(default_lifecycle_rules())
    temp = rules[RULE_ID_TEMP]
    assert temp.prefix == TEMP_PREFIX == "_uploads/"
    assert temp.expiration_days == 30
    assert temp.abort_incomplete_multipart_days is None
    assert temp.notes  # 规则要能在 CLI 里被解释


def test_business_prefixes_never_expire():
    """输入资产与计算结果只允许转低频，绝不允许过期删除。"""

    rules = _rules_by_id(default_lifecycle_rules())
    for rule_id in (RULE_ID_INPUT_ASSETS, RULE_ID_ARTIFACTS, RULE_ID_EXECUTIONS):
        rule = rules[rule_id]
        assert rule.expiration_days is None, f"{rule_id} 不得配置过期删除"
        assert rule.abort_incomplete_multipart_days is None

    assert rules[RULE_ID_INPUT_ASSETS].prefix == INPUT_ASSET_PREFIX


def test_transition_rules_skipped_without_storage_class():
    rules = default_lifecycle_rules(transition_storage_class=None)
    assert all(rule.transition_days is None for rule in rules)
    assert all(rule.transition_storage_class is None for rule in rules)


def test_transition_rules_enabled_when_storage_class_given():
    rules = _rules_by_id(
        default_lifecycle_rules(transition_storage_class="COLDTIER")
    )
    assert rules[RULE_ID_INPUT_ASSETS].transition_days == 30
    assert rules[RULE_ID_ARTIFACTS].transition_days == 90
    assert rules[RULE_ID_EXECUTIONS].transition_days == 180
    assert rules[RULE_ID_INPUT_ASSETS].transition_storage_class == "COLDTIER"


def test_zero_or_negative_windows_are_dropped():
    """0/负数在 S3 语义里不是「永不」，而是非法值；必须被过滤掉。"""

    rules = default_lifecycle_rules(
        temp_expiration_days=0, abort_incomplete_days=-1, noncurrent_keep_days=0
    )
    # 三个时间窗全被归一成 None → 这条规则没有任何动作 → SDK 构造 Rule 会抛
    # ValueError（「at least one of action ... must be specified」），所以整条必须消失。
    assert RULE_ID_TEMP not in _rules_by_id(rules)


def test_resolve_rules_reads_settings(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.MINIO_LIFECYCLE_TEMP_EXPIRATION_DAYS", 45, raising=False
    )
    monkeypatch.setattr(
        "app.config.settings.MINIO_LIFECYCLE_ABORT_INCOMPLETE_DAYS", 3, raising=False
    )
    monkeypatch.setattr(
        "app.config.settings.MINIO_LIFECYCLE_TRANSITION_STORAGE_CLASS",
        None,
        raising=False,
    )
    temp = _rules_by_id(resolve_rules())[RULE_ID_TEMP]
    assert temp.expiration_days == 45
    # abort 配置项仍被读取（保留签名兼容），但不再落到规则上。
    assert temp.abort_incomplete_multipart_days is None


def test_is_platform_rule_only_claims_own_prefix():
    assert is_platform_rule("aidd-temp-scratch") is True
    assert is_platform_rule("ops-manual-backup") is False
    assert is_platform_rule(None) is False
    assert is_platform_rule("") is False


# --------------------------------------------------------------------------- #
# SDK 转换与签名
# --------------------------------------------------------------------------- #


def test_build_lifecycle_config_produces_sdk_rules():
    config = build_lifecycle_config(default_lifecycle_rules())
    assert len(config.rules) == 4
    temp = next(r for r in config.rules if r.rule_id == RULE_ID_TEMP)
    assert temp.abort_incomplete_multipart_upload is None
    assert temp.expiration.days == 30
    assert temp.expiration.expired_object_delete_marker is None
    assert temp.rule_filter.prefix == TEMP_PREFIX


def test_signature_matches_between_spec_and_sdk():
    """``merge_rules`` 的幂等判断靠这两份签名一致，不一致会导致每次都重写。"""

    specs = default_lifecycle_rules()
    config = build_lifecycle_config(specs)
    sdk_by_id = {rule.rule_id: rule for rule in config.rules}
    for spec in specs:
        assert rule_signature(sdk_by_id[spec.rule_id]) == spec_signature(spec)


def test_signature_detects_changed_days():
    specs = _rules_by_id(default_lifecycle_rules())
    changed = default_lifecycle_rules(temp_expiration_days=90)
    assert rule_signature(
        build_lifecycle_config([specs[RULE_ID_TEMP]]).rules[0]
    ) != spec_signature(_rules_by_id(changed)[RULE_ID_TEMP])


# --------------------------------------------------------------------------- #
# 合并语义
# --------------------------------------------------------------------------- #


def test_merge_preserves_operator_rules():
    existing = build_lifecycle_config(
        [
            LifecycleRuleSpec(
                rule_id="ops-manual-archive", prefix="archive/", expiration_days=365
            )
        ]
    )
    merged, preserved_ids, changed = merge_rules(default_lifecycle_rules(), existing)
    assert preserved_ids == ["ops-manual-archive"]
    assert changed is True
    ids = [rule.rule_id for rule in merged]
    assert "ops-manual-archive" in ids
    assert RULE_ID_TEMP in ids


def test_merge_is_idempotent_when_already_applied():
    specs = default_lifecycle_rules()
    existing = build_lifecycle_config(specs)
    merged, preserved_ids, changed = merge_rules(specs, existing)
    assert changed is False
    assert preserved_ids == []
    assert len(merged) == len(specs)


def test_merge_from_empty_bucket_is_changed():
    _, _, changed = merge_rules(default_lifecycle_rules(), None)
    assert changed is True


def test_merge_drops_platform_rules_that_are_no_longer_wanted():
    """曾配过过渡规则、后来把 storage class 清空 → 必须能删掉那条旧规则。"""

    with_transition = default_lifecycle_rules(transition_storage_class="COLDTIER")
    existing = build_lifecycle_config(with_transition)
    without_transition = default_lifecycle_rules(transition_storage_class=None)

    _, _, changed = merge_rules(without_transition, existing)
    assert changed is True

    merged, _, _ = merge_rules(without_transition, existing)
    for rule in merged:
        assert getattr(rule, "transition", None) is None


# --------------------------------------------------------------------------- #
# 应用与幂等（走 fake 后端）
# --------------------------------------------------------------------------- #


def test_apply_writes_once_then_is_noop():
    backend = _FakeBackend(existing=None)

    first = asyncio.run(
        apply_lifecycle(backend, bucket="b1", rules=default_lifecycle_rules())
    )
    assert first.applied is True
    assert len(backend.written) == 1

    second = asyncio.run(
        apply_lifecycle(backend, bucket="b1", rules=default_lifecycle_rules())
    )
    assert second.applied is False
    assert second.changed is False
    assert len(backend.written) == 1, "规则未变时不得再写一次桶配置"


def test_apply_dry_run_never_writes():
    backend = _FakeBackend(existing=None)
    plan = asyncio.run(
        apply_lifecycle(
            backend, bucket="b1", rules=default_lifecycle_rules(), dry_run=True
        )
    )
    assert plan.applied is False
    assert plan.changed is True
    assert backend.written == []


def test_plan_reports_preserved_operator_rules():
    existing = build_lifecycle_config(
        [LifecycleRuleSpec(rule_id="ops-x", prefix="x/", expiration_days=10)]
    )
    backend = _FakeBackend(existing=existing)
    plan = asyncio.run(plan_lifecycle(backend, bucket="b1"))
    assert plan.preserved_rule_ids == ["ops-x"]


def test_empty_rule_set_deletes_config_instead_of_writing_empty():
    """一条规则都不需要时，S3 语义是「删除配置」。

    真 MinIO 上实测：写空配置会被拒并报
    ``InvalidArgument: Lifecycle configuration should have at least one rule``。
    """

    existing = build_lifecycle_config(default_lifecycle_rules())
    backend = _FakeBackend(existing=existing, supports_delete=True)

    plan = asyncio.run(
        apply_lifecycle(backend, bucket="b1", rules=[])
    )
    assert plan.applied is True
    assert plan.reason == "已删除配置"
    assert backend.deleted == ["b1"]
    assert backend.written == [], "空规则集不得走 set_bucket_lifecycle"


def test_empty_rule_set_falls_back_for_backends_without_delete():
    """测试替身/旧后端没有 delete 方法时退回写空配置，不能抛。

    桶上本来就有平台规则才能构成「需要删除」，否则是纯粹的 no-op（什么都没配，
    也就没有要清的东西）。
    """

    existing = build_lifecycle_config(default_lifecycle_rules())
    backend = _FakeBackend(existing=existing, supports_delete=False)
    plan = asyncio.run(apply_lifecycle(backend, bucket="b1", rules=[]))
    assert plan.applied is True
    assert len(backend.written) == 1


def test_empty_rule_set_on_clean_bucket_is_noop():
    backend = _FakeBackend(existing=None, supports_delete=True)
    plan = asyncio.run(apply_lifecycle(backend, bucket="b1", rules=[]))
    assert plan.applied is False
    assert plan.changed is False
    assert backend.deleted == [] and backend.written == []


def test_empty_rule_set_never_constructs_sdk_lifecycle_config():
    """空规则集绝不能构造 ``minio.LifecycleConfig([])``——两个受支持版本行为相反。

    这条守的是一次真实的 CI 全红：本机 minio 7.2.20 允许空配置，``requirements.txt``
    锁定的 7.2.3 直接 ``raise ValueError("rules must be provided")``，于是 13 条用例在
    本机全绿、在 CI 全挂。空规则集只应产出本地 ``_EmptyLifecycleConfig``。
    """

    from app.storage import lifecycle as lifecycle_module

    empty = lifecycle_module.build_lifecycle_config([])
    assert isinstance(empty, lifecycle_module._EmptyLifecycleConfig)
    assert empty.rules == []

    # 非空仍必须是真正的 SDK 对象（否则「与版本无关」就变成了「压根没用 SDK」）。
    from minio.lifecycleconfig import LifecycleConfig

    full = lifecycle_module.build_lifecycle_config(default_lifecycle_rules())
    assert isinstance(full, LifecycleConfig)
    assert len(full.rules) >= 1


def test_backend_without_lifecycle_support_is_reported_not_raised():
    """本地后端没有桶：要给出可读结论，不是抛 NotImplementedError。"""

    backend = _NoLifecycleBackend()
    plan = asyncio.run(plan_lifecycle(backend, bucket="b1"))
    assert plan.applied is False
    assert "不支持" in plan.reason

    applied = asyncio.run(apply_lifecycle(backend, bucket="b1"))
    assert applied.applied is False
    assert "不支持" in applied.reason


def test_plan_dict_is_serializable():
    backend = _FakeBackend(existing=None)
    plan = asyncio.run(plan_lifecycle(backend, bucket="b1"))
    payload = plan.to_dict()
    assert payload["bucket"] == "b1"
    assert {rule["ruleId"] for rule in payload["rules"]} == {
        RULE_ID_TEMP,
        RULE_ID_INPUT_ASSETS,
        RULE_ID_ARTIFACTS,
        RULE_ID_EXECUTIONS,
    }
    assert payload["rules"][0]["prefix"]


@pytest.mark.asyncio
async def test_startup_hook_is_noop_by_default(monkeypatch):
    """默认不启用：改桶配置是运维动作，不该每次重启都动一次生产存储。"""

    from app.storage import lifecycle as lifecycle_module

    monkeypatch.setattr(
        "app.config.settings.MINIO_LIFECYCLE_APPLY_ON_STARTUP", False, raising=False
    )
    called = []

    async def _boom(*args, **kwargs):  # pragma: no cover - 不该被调用
        called.append(True)
        raise AssertionError("默认配置下不应调用 apply_lifecycle")

    monkeypatch.setattr(lifecycle_module, "apply_lifecycle", _boom)
    assert await lifecycle_module.ensure_lifecycle_on_startup() is None
    assert called == []


@pytest.mark.asyncio
async def test_startup_hook_swallows_failures(monkeypatch):
    """生命周期配置失败不该让平台起不来。"""

    from app.storage import lifecycle as lifecycle_module

    monkeypatch.setattr(
        "app.config.settings.MINIO_LIFECYCLE_APPLY_ON_STARTUP", True, raising=False
    )
    monkeypatch.setattr(
        "app.config.settings.STORAGE_BACKEND", "minio", raising=False
    )

    async def _fail(*args, **kwargs):
        raise RuntimeError("minio 不可达")

    monkeypatch.setattr(lifecycle_module, "apply_lifecycle", _fail)
    assert await lifecycle_module.ensure_lifecycle_on_startup() is None
