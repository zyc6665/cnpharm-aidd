#!/usr/bin/env python3
"""离线合规扫描：禁止代码与配置中出现公网域名、外部 API、遥测上报。

依据 docs/03-系统架构设计说明书.md §10（约束 C-1）：
  红线——代码与配置禁止出现任何公网域名、外部 API、遥测上报。

扫描分两级：
  BLOCKER  运行时会被真正发起请求的外部地址 —— 直接判失败
  NOTICE   文档/元数据性质（项目主页、JSON Schema 声明、参考链接）—— 只提示

允许的例外形态：localhost、127.0.0.1、集群内地址（*.svc.cluster.local）、
XML 命名空间（w3.org / purl.org）、example.invalid 等占位域名。

命中但确需保留的，登记到 .github/offline-allowlist.txt 并写明理由与移除计划。

用法:
    python scripts/check_offline_compliance.py
    python scripts/check_offline_compliance.py --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 扫描范围
# ---------------------------------------------------------------------------
SCAN_DIRS = [
    "backend/app",
    "backend/alembic",
    "frontend/src",
    "deploy",
    "scripts",
    "example",
]
SCAN_SUFFIXES = {
    ".py", ".ts", ".tsx", ".vue", ".js", ".yaml", ".yml", ".json",
    ".toml", ".ini", ".cfg", ".env", ".sh", ".dockerfile", "",
}
SKIP_DIR_NAMES = {
    "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".git", ".pytest_cache", ".mypy_cache", "coverage", "htmlcov",
}

# ---------------------------------------------------------------------------
# 外部域名识别
# ---------------------------------------------------------------------------
URL_RE = re.compile(r"https?://([A-Za-z0-9.\-_]+\.[A-Za-z]{2,})", re.IGNORECASE)

# 允许的域名/后缀：本机、集群内、命名空间、占位
ALLOWED_HOST_SUFFIXES = (
    "localhost",
    ".local",
    ".svc.cluster.local",
    ".cluster.local",
    ".invalid",
    ".test",
    ".example",
    "example.com",
    "example.org",
    ".example.com",
    ".example.org",
    ".example.invalid",
    ".internal",
    ".svc",
    ".cluster.local",
    "w3.org",
    "purl.org",
    "json-schema.org",
    "schemas.xmlsoap.org",
    "xmlns.com",
    "127.0.0.1",
    "0.0.0.0",
)

# 文档/元数据性质的字段名，命中这些行的 URL 降级为 NOTICE
DOC_CONTEXT_KEYS = (
    "project_url",
    "homepage",
    "documentation",
    "reference_url",
    "source_url",
    "license_url",
    "$schema",
    "@context",
    "url\":",  # golden metadata 里的出典链接
)

# 强特征：这些域名一旦出现在代码里，基本可以确定是真实外部调用
HIGH_RISK_HOSTS = (
    "pubchem.ncbi.nlm.nih.gov",
    "rcsb.org",
    "ebi.ac.uk",
    "uniprot.org",
    "pdbbind.org.cn",
    "chembl",
    "drugbank",
    "api.openai.com",
    "api.deepseek.com",
    "dashscope.aliyuncs.com",
    "anthropic.com",
    "googleapis.com",
    "segment.io",
    "sentry.io",
    "mixpanel.com",
    "amplitude.com",
)


@dataclass(frozen=True)
class Finding:
    level: str  # BLOCKER / NOTICE
    path: str
    lineno: int
    host: str
    line: str


def _is_allowed_host(host: str) -> bool:
    host = host.lower().strip(".")
    if host in ALLOWED_HOST_SUFFIXES:
        return True
    return any(
        host == suffix.lstrip(".") or host.endswith(suffix)
        for suffix in ALLOWED_HOST_SUFFIXES
        if suffix.startswith(".")
    )


def _load_allowlist() -> dict[str, str]:
    """读取 .github/offline-allowlist.txt -> {相对路径: 理由}"""
    allow_file = REPO_ROOT / ".github" / "offline-allowlist.txt"
    entries: dict[str, str] = {}
    if not allow_file.exists():
        return entries
    for raw in allow_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        entries[parts[0]] = parts[1] if len(parts) > 1 else ""
    return entries


TEST_FILE_PATTERNS = (
    ".spec.ts", ".spec.tsx", ".spec.js", ".test.ts", ".test.tsx", ".test.js",
    "_test.py", "test_", "conftest.py",
)


def _is_test_file(path: Path) -> bool:
    """测试文件里的域名是 fixture，不会真实发起请求，不参与合规判定。"""
    name = path.name
    if any(pattern in name for pattern in TEST_FILE_PATTERNS):
        return True
    parts = set(path.parts)
    return bool(parts & {"test", "tests", "__tests__", "e2e"})


def _iter_files() -> "list[Path]":
    files: list[Path] = []
    for rel_dir in SCAN_DIRS:
        base = REPO_ROOT / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() not in SCAN_SUFFIXES:
                continue
            if _is_test_file(path):
                continue
            files.append(path)
    return files


def _classify(path: Path, line: str, host: str) -> str:
    lowered = line.lower()
    if any(key.lower() in lowered for key in DOC_CONTEXT_KEYS):
        return "NOTICE"
    if any(risk in host.lower() for risk in HIGH_RISK_HOSTS):
        return "BLOCKER"
    # 其余外部域名：源文件里出现也算阻断，配置文件里的允许作为提示
    if path.suffix.lower() in {".py", ".ts", ".tsx", ".vue", ".js"}:
        return "BLOCKER"
    return "NOTICE"


def scan() -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in URL_RE.finditer(line):
                host = match.group(1)
                if _is_allowed_host(host):
                    continue
                findings.append(
                    Finding(
                        level=_classify(path, line, host),
                        path=rel,
                        lineno=lineno,
                        host=host,
                        line=line.strip()[:160],
                    )
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="离线合规扫描")
    parser.add_argument("--verbose", action="store_true", help="同时列出 NOTICE 级命中")
    args = parser.parse_args()

    allowlist = _load_allowlist()
    findings = scan()

    blockers: list[Finding] = []
    notices: list[Finding] = []
    suppressed: list[Finding] = []

    for finding in findings:
        if finding.path in allowlist:
            suppressed.append(finding)
        elif finding.level == "BLOCKER":
            blockers.append(finding)
        else:
            notices.append(finding)

    print("=" * 72)
    print("离线合规扫描（docs/03 §10 约束 C-1）")
    print("=" * 72)
    print(f"扫描目录: {', '.join(SCAN_DIRS)}")
    print(f"阻断级命中: {len(blockers)}    提示级命中: {len(notices)}    已登记豁免: {len(suppressed)}")
    print()

    if blockers:
        print("[BLOCKER] 阻断级违规（运行时真实外部调用）:")
        for item in blockers:
            print(f"  {item.path}:{item.lineno}  [{item.host}]")
            print(f"      {item.line}")
        print()
        print("处理方式二选一:")
        print("  1. 移除该调用（交付线不允许公网访问）")
        print("  2. 确需保留则登记到 .github/offline-allowlist.txt，写明理由与移除计划")
        print()

    if args.verbose and notices:
        print("[NOTICE] 提示级命中（文档/元数据性质，不阻断）:")
        for item in notices:
            print(f"  {item.path}:{item.lineno}  [{item.host}]")
        print()

    if suppressed:
        print("[ALLOWLIST] 已登记豁免:")
        for path, reason in sorted(allowlist.items()):
            count = sum(1 for item in suppressed if item.path == path)
            if count:
                print(f"  {path}  ({count} 处) — {reason or '未填写理由'}")
        print()

    if blockers:
        print("结果: FAILED")
        return 1

    print("结果: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
