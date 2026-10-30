#!/usr/bin/env python3
# scripts/gen_frontend_enums.py
"""从后端单一枚举源生成前端 TypeScript 枚举常量（计划 §3.2）。

数据来源是 ``backend/app/common/enums.py`` 里的枚举类 —— 这里用 ``import`` 读取
``values()``，**不做正则解析**，因此后端一旦新增/删除取值，本脚本与守护测试
``test/test_frontend_enum_parity.py`` 会一起发现。

生成物固定为每组的 ``as const`` 数组 + ``typeof arr[number]`` 联合类型：

    export const PROJECT_STATUS = ["draft", ...] as const
    export type ProjectStatus = (typeof PROJECT_STATUS)[number]

用法::

    python scripts/gen_frontend_enums.py                 # 写入默认位置
    python scripts/gen_frontend_enums.py --output /tmp/x # 写到别处（守护测试用）
    python scripts/gen_frontend_enums.py --check         # 只校验，不写盘
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common import enums as backend_enums  # noqa: E402  (path bootstrap)

#: (后端枚举类名, 前端 TypeScript 类型名)
ENUM_GROUPS = [
    ("PROJECT_STATUS", "ProjectStatus"),
    ("PROJECT_ROLE", "ProjectRole"),
    ("TASK_PRIORITY", "TaskPriority"),
    # 后端 TaskStatus 取值是大写（PENDING/QUEUED/...），前端 API 契约是小写。
    # 这里生成 ``TaskStatusGenerated``，由 ``types/models.d.ts`` 用
    # ``Lowercase<TaskStatusGenerated>`` 派生小写联合，避免手抄八态清单。
    ("TASK_STATUS", "TaskStatusGenerated"),
    ("ASSET_ARTIFACT_TYPE", "AssetArtifactType"),
    ("AUDIT_ACTION", "AuditAction"),
    ("AUDIT_RESULT", "AuditResult"),
    ("RESOURCE_TYPE", "ResourceType"),
]

DEFAULT_OUTPUT = REPO_ROOT / "frontend" / "src" / "types" / "enums.generated.ts"

_HEADER = """\
// AUTO-GENERATED FILE — DO NOT EDIT BY HAND.
// Source: backend/app/common/enums.py
// Regenerate: python scripts/gen_frontend_enums.py
/* eslint-disable */
"""


def render() -> str:
    """Return the full TypeScript source for every enum group."""
    chunks = [_HEADER]
    for const_name, type_name in ENUM_GROUPS:
        enum_cls = getattr(backend_enums, const_name)
        values = list(enum_cls.values())
        array_literal = ", ".join(json.dumps(value) for value in values)
        chunks.append(
            f"export const {const_name} = [{array_literal}] as const\n"
            f"export type {type_name} = (typeof {const_name})[number]\n"
        )
    return "\n".join(chunks).rstrip("\n") + "\n"


def write_output(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="生成文件路径（默认 frontend/src/types/enums.generated.ts）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只比对不写入；与磁盘内容不一致时退出码为 1",
    )
    args = parser.parse_args(argv)

    rendered = render()
    if args.check:
        current = (
            args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        )
        if current != rendered:
            print(f"枚举生成文件已过期：{args.output}", file=sys.stderr)
            return 1
        print(f"枚举生成文件已是最新：{args.output}")
        return 0

    write_output(args.output)
    print(f"已生成 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
