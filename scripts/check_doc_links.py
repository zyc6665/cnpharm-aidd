#!/usr/bin/env python3
"""检查 Markdown 文档内的相对链接是否指向真实存在的文件。

交付期文档是验收材料的一部分，断链会让甲方质询「文档是否真实维护」。
CI 每次 PR 都跑，不要求文档写得好，但要求链接不烂。

检查范围:
    docs/**/*.md
    README.md
    CONTRIBUTING.md

忽略:
    外链（http/https/mailto）、页内锚点（#xxx）、代码块内的示例

用法:
    python scripts/check_doc_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "CONTRIBUTING.md",
]
DOCS_DIR = REPO_ROOT / "docs"

# [text](target)  或  [text](<target>)
LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


# 归档目录是产品线历史文档的只读快照，内含大量指向原开发机绝对路径的
# 代码引用（如 /data/zhouyc/...），不参与断链检查。
EXCLUDED_DIRS = {"archive-upstream"}


def _iter_markdown() -> "list[Path]":
    files: list[Path] = []
    for path in TARGETS:
        if path.exists():
            files.append(path)
    if DOCS_DIR.exists():
        for path in sorted(DOCS_DIR.rglob("*.md")):
            if any(part in EXCLUDED_DIRS for part in path.relative_to(DOCS_DIR).parts):
                continue
            files.append(path)
    return files


def _strip_code_fences(text: str) -> "list[tuple[int, str]]":
    """返回 (行号, 行内容)，跳过 fenced code block 内的行。"""
    result: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        result.append((lineno, line))
    return result


def _is_external(target: str) -> bool:
    lowered = target.lower()
    return (
        lowered.startswith(("http://", "https://", "mailto:", "tel:", "ftp://"))
        or lowered.startswith("#")
        or lowered.startswith("data:")
    )


def check() -> list[tuple[str, int, str]]:
    broken: list[tuple[str, int, str]] = []
    for path in _iter_markdown():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in _strip_code_fences(text):
            for match in LINK_RE.finditer(line):
                raw = match.group(1).strip()
                if raw.startswith("<") and raw.endswith(">"):
                    raw = raw[1:-1].strip()
                if not raw or _is_external(raw):
                    continue
                # 去掉锚点与查询串
                target = raw.split("#", 1)[0].split("?", 1)[0]
                if not target:
                    continue
                # 绝对路径是代码位置引用，不是仓库内文档链接
                if target.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", target):
                    continue
                target = unquote(target)
                resolved = (path.parent / target).resolve()
                # Windows 下路径比较需归一化大小写以外的分隔符
                if not resolved.exists():
                    broken.append((rel, lineno, raw))
    return broken


def main() -> int:
    broken = check()
    print("=" * 72)
    print("文档相对链接检查")
    print("=" * 72)
    if not broken:
        print("结果: PASSED（无断链）")
        return 0

    print(f"发现 {len(broken)} 处断链:")
    for rel, lineno, target in broken:
        print(f"  {rel}:{lineno}  ->  {target}")
    print()
    print("修法: 改链接或补文件。若目标文件已归档到 docs/archive-upstream/，请更新路径。")
    print("结果: FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
