"""画布预设引用校验：预设中的每个工具 slug 都必须已在能力注册表登记。

这条断言防止前端画布回到历史 mock slug（如 ``molecular-docking`` /
``ligand-preparation`` / ``lead-optimizer``）而与库里真实工具脱节。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tools.capabilities import AIDD_TOOL_CAPABILITIES  # noqa: E402


PRESET_SOURCE = PROJECT_ROOT / "frontend" / "src" / "workflow" / "canvas-presets.ts"


def _preset_tool_slugs() -> set[str]:
    source = PRESET_SOURCE.read_text(encoding="utf-8")
    slugs: set[str] = set()
    for match in re.finditer(r"toolSlugs:\s*\[([^\]]*)\]", source):
        slugs.update(re.findall(r"'([^']+)'", match.group(1)))
    for match in re.finditer(r"recommendedToolSlug:\s*'([^']+)'", source):
        slugs.add(match.group(1))
    return slugs


def test_canvas_preset_tool_slugs_exist_in_capability_registry() -> None:
    slugs = _preset_tool_slugs()
    assert slugs, "未从 canvas-presets.ts 解析到任何工具 slug"

    missing = sorted(slug for slug in slugs if slug not in AIDD_TOOL_CAPABILITIES)
    assert not missing, f"画布预设引用了未登记的工具 slug: {missing}"


def test_canvas_presets_use_deployed_tools_where_available() -> None:
    slugs = _preset_tool_slugs()
    assert "pocket2mol-pocket-ligand-generation" in slugs
    assert "autodock-vina-docking" in slugs
    assert "molp-pc-property-prediction" in slugs
