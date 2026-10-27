"""对象存储生命周期规则的运维入口（docs/04 §5.8、docs/15 §3.2）。

用法::

    # 只打印计划，不写桶
    python -m app.cli.storage_lifecycle --dry-run

    # 写入（幂等：规则未变则不产生写操作）
    python -m app.cli.storage_lifecycle --apply

为什么是 CLI 而不是启动时自动写
--------------------------------
改桶的 lifecycle 是**运维动作**：它会真的删除 ``_uploads/`` 下 30 天前的对象。
放在启动流程里意味着「重启一次就动一次生产存储配置」，且没人知道是谁在什么时候
改的。做成显式命令，部署脚本里调用、日志里留痕，出问题能对上时间点。

``MINIO_LIFECYCLE_APPLY_ON_STARTUP`` 保留为可选开关，但默认关闭。
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.config import settings
from app.storage.factory import get_storage_backend
from app.storage.lifecycle import LifecyclePlan, apply_lifecycle, resolve_rules


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="对象存储生命周期规则")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="只计算并打印计划，不写桶")
    mode.add_argument("--apply", action="store_true", help="写入生命周期规则（幂等）")
    parser.add_argument(
        "--bucket",
        default=None,
        help=f"目标桶，默认取 MINIO_BUCKET（当前 {settings.MINIO_BUCKET}）",
    )
    parser.add_argument(
        "--storage-class",
        default=None,
        help="转低频的目标 storage class；留空读配置，仍为空则不生成过渡规则",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    return parser


def _describe_actions(rule) -> str:
    actions = []
    if rule.expiration_days:
        actions.append(f"expire={rule.expiration_days}d")
    if rule.abort_incomplete_multipart_days:
        actions.append(f"abort-multipart={rule.abort_incomplete_multipart_days}d")
    if rule.noncurrent_expiration_days:
        actions.append(f"noncurrent={rule.noncurrent_expiration_days}d")
    if rule.transition_days and rule.transition_storage_class:
        actions.append(
            f"transition={rule.transition_days}d->{rule.transition_storage_class}"
        )
    return " ".join(actions) or "(no action)"


def _print_plan(plan: LifecyclePlan, *, dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"[{mode}] bucket={plan.bucket}", flush=True)
    for rule in plan.rules:
        print(
            f"  {rule.rule_id:<28} prefix={rule.prefix or '(all)':<24} "
            f"{_describe_actions(rule)}",
            flush=True,
        )
    if plan.preserved_rule_ids:
        print(f"  保留运维规则: {', '.join(plan.preserved_rule_ids)}", flush=True)
    print(f"  结论: {plan.reason}", flush=True)


async def _run(
    *,
    dry_run: bool,
    bucket: str | None,
    storage_class: str | None,
    as_json: bool,
) -> int:
    rules = resolve_rules(transition_storage_class=storage_class)
    backend = get_storage_backend()
    plan = await apply_lifecycle(backend, bucket=bucket, rules=rules, dry_run=dry_run)

    if as_json:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), flush=True)
    else:
        _print_plan(plan, dry_run=dry_run)

    # 写入模式下后端不支持生命周期 → 退出码 2，便于部署脚本 fail-fast。
    if not dry_run and not plan.applied and "不支持" in plan.reason:
        return 2
    return 0


def main() -> None:
    args = _parser().parse_args()
    raise SystemExit(
        asyncio.run(
            _run(
                dry_run=args.dry_run,
                bucket=args.bucket,
                storage_class=args.storage_class,
                as_json=bool(args.json),
            )
        )
    )


if __name__ == "__main__":
    main()
