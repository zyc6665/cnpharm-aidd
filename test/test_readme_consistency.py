"""README 是交付仓库的门面，必须一直说真话。

这些断言锁的不是文案风格，而是几条会影响交付的事实：离线约束、分叉溯源、
可复制的命令、真实的目录结构、分支模型。README 改错任何一条，这里就失败。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

LINK_PATTERN = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_declares_delivery_constraints() -> None:
    """离线合规是甲方红线，README 必须显式声明，不能只写在 docs 里。"""
    text = _readme_text()

    assert "中国医药" in text
    assert "私有化离线部署" in text
    assert "K100-AI" in text
    assert "禁止出现任何公网域名" in text


def test_readme_documents_the_fork_point() -> None:
    """交付线从哪来必须可追溯，否则回产品线取补丁时无从下手。"""
    text = _readme_text()

    assert "cnpharm-base-ce9a521" in text
    assert "develop@ce9a521" in text


def test_readme_quickstart_commands_stay_runnable() -> None:
    """新成员按 README 敲命令必须能跑通，命令改动要同步。"""
    text = _readme_text()

    for command in (
        "pip install -r requirements-dev.txt",
        "python -m flake8 backend/app --select F401",
        "python -m pytest test/ -v",
        "docker compose -f deploy/compose/docker-compose.dev.yml up -d",
    ):
        assert command in text, f"README 缺少可直接复制的基础命令：{command}"


def test_readme_directory_tree_matches_repository_layout() -> None:
    """目录树不能写成想象的样子——提到的目录必须真实存在。"""
    text = _readme_text()

    for directory in ("backend", "frontend", "deploy", "docs", "test", "example"):
        assert f"{directory}/" in text, f"README 目录树缺少 {directory}/"
        assert (ROOT / directory).is_dir(), f"README 提到的 {directory}/ 在仓库中不存在"


def test_readme_documents_branch_model() -> None:
    """分支模型是协作前提，主干名与 tag 规则要在门面上出现。"""
    text = _readme_text()

    assert "`main`" in text
    assert "release/v1.x.y" in text
    assert "Refs:" in text


def test_readme_links_all_exist() -> None:
    """README 里的相对链接必须指向真实文件，避免新成员点开是 404。"""
    missing: list[str] = []

    for target in LINK_PATTERN.findall(_readme_text()):
        target = target.strip("<>")
        if target.startswith(("http://", "https://", "mailto:", "tel:", "#")):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        if not (ROOT / path_part).exists():
            missing.append(target)

    assert missing == []


def test_readme_does_not_regress_into_product_line_copy() -> None:
    """README 一旦被产品线版本覆盖，交付约束就会静默消失，这里拦住它。"""
    text = _readme_text()

    for forbidden in ("游客模式", "科学计算工具管理平台", "2026-07-29"):
        assert forbidden not in text, f"README 混入了产品线残留内容：{forbidden}"
