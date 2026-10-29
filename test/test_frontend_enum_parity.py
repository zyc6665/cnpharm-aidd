"""守护：前端枚举 codegen 与后端单一枚举源保持一致（计划 §3.2）。

做法是把 ``scripts/gen_frontend_enums.py`` 跑到临时目录，再与入库的
``frontend/src/types/enums.generated.ts`` 逐字节 diff —— 不修改仓库文件，因此
可以安全地在 CI / 本地反复运行。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "scripts" / "gen_frontend_enums.py"
GENERATED = REPO_ROOT / "frontend" / "src" / "types" / "enums.generated.ts"


def test_frontend_enums_match_backend(tmp_path: Path) -> None:
    output = tmp_path / "enums.generated.ts"
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--output", str(output)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    assert GENERATED.exists(), "frontend/src/types/enums.generated.ts 未入库"
    assert output.read_text(encoding="utf-8") == GENERATED.read_text(
        encoding="utf-8"
    ), (
        "frontend/src/types/enums.generated.ts 已过期：请运行 "
        "`python scripts/gen_frontend_enums.py` 重新生成后提交。"
    )
