#!/usr/bin/env python3
"""为 main 分支配置保护规则。

为什么用脚本而不是手点：分支保护是交付纪律的一部分，必须和代码一样可复核、
可重放。新仓库初始化、误删后重建、或收紧规则时直接重跑本脚本即可。

用法：
    python scripts/setup_branch_protection.py            # 查看当前设置
    python scripts/setup_branch_protection.py --apply    # 应用设置（管理员也不可绕过）
    python scripts/setup_branch_protection.py --apply --approvals 1

前置：gh 已登录且对仓库有 admin 权限。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

REPO = "zyc6665/cnpharm-aidd"
BRANCH = "main"

# 与 .github/workflows/ci.yml 中的 job name 严格一致——名字写错会导致
# 保护规则等一个永远不会出现的检查，PR 永远不会变成绿色。
REQUIRED_CHECKS = [
    "后端规范检查",
    "后端测试",
    "迁移链（PostgreSQL）",
    "前端构建",
    "前端单元测试",
    "离线合规扫描",
    "部署配置校验",
    "文档链接检查",
]

# 只在 push / base 为 main 时运行，不能作为合入门槛
CONDITIONAL_CHECKS = ["前端 E2E"]


def _gh(args: list[str], *, payload: dict | None = None) -> subprocess.CompletedProcess:
    cmd = ["gh", *args]
    if payload is not None:
        cmd.extend(["--input", "-"])
    return subprocess.run(
        cmd,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def show_current() -> int:
    result = _gh(["api", f"repos/{REPO}/branches/{BRANCH}/protection"])
    if result.returncode != 0:
        print("当前未配置分支保护：")
        print((result.stderr or result.stdout).strip())
        return 0
    data = json.loads(result.stdout)
    print("当前分支保护：")
    print(f"  必需状态检查：{data.get('required_status_checks')}")
    print(f"  必需评审数：{data.get('required_pull_request_reviews')}")
    print(f"  禁止强推：{data.get('allow_force_pushes')}")
    print(f"  线性历史：{data.get('required_linear_history')}")
    return 0


def apply(approvals: int, enforce_admins: bool) -> int:
    payload = {
        "required_status_checks": {
            "strict": True,
            "contexts": REQUIRED_CHECKS,
        },
        "enforce_admins": enforce_admins,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": approvals > 0,
            "required_approving_review_count": approvals,
        },
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_conversation_resolution": True,
    }
    result = _gh(
        ["api", "-X", "PUT", f"repos/{REPO}/branches/{BRANCH}/protection"],
        payload=payload,
    )
    if result.returncode != 0:
        print("应用失败：")
        print((result.stderr or result.stdout).strip())
        return 1
    print(f"已应用到 {REPO}@{BRANCH}")
    print(f"  必需检查（{len(REQUIRED_CHECKS)}）：{'、'.join(REQUIRED_CHECKS)}")
    print(f"  必需评审数：{approvals}")
    print(f"  enforce_admins：{enforce_admins}")
    print(f"  说明：{('、'.join(CONDITIONAL_CHECKS))} 条件运行，未纳入门槛。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="配置 main 分支保护")
    parser.add_argument("--apply", action="store_true", help="实际写入（默认只查看）")
    parser.add_argument(
        "--approvals",
        type=int,
        default=0,
        help="必需评审数。单人期用 0；团队到位后改 1",
    )
    parser.add_argument(
        "--allow-admin-bypass",
        action="store_true",
        help="允许管理员绕过规则。默认禁止——能绕过就等于没有保护",
    )
    args = parser.parse_args()

    if not args.apply:
        return show_current()
    return apply(args.approvals, enforce_admins=not args.allow_admin_bypass)


if __name__ == "__main__":
    sys.exit(main())
