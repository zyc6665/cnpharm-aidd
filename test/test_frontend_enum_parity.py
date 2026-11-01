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


def test_task_status_is_single_source_and_covers_all_states() -> None:
    """TaskStatus 必须在单一枚举源里，前端类型从生成值派生。

    这条是第 10 项的根因守护：``TaskStatus`` 扩成八态时，前端手写的三态/七态
    数组没人拦。把它纳入 codegen 后，这里同时锁住三件事：
    1. ``app.models.tasks.TaskStatus`` 就是 ``app.common.enums.TASK_STATUS``（迁移后
       对外导入路径不变）；
    2. 生成文件确实包含全部八个取值；
    3. ``models.d.ts`` 的 ``TaskStatus`` 是 ``Lowercase<TaskStatusGenerated>`` 派生，
       而不是又手抄一份清单。
    """
    from app.common.enums import TASK_STATUS
    from app.models.tasks import TaskStatus

    assert TaskStatus is TASK_STATUS
    assert set(TASK_STATUS.values()) == {
        "PENDING",
        "REJECTED",
        "QUEUED",
        "RUNNING",
        "SUCCESS",
        "FAILURE",
        "TIMEOUT",
        "CANCELED",
    }

    rendered = GENERATED.read_text(encoding="utf-8")
    assert "export const TASK_STATUS = [" in rendered
    assert "export type TaskStatusGenerated = (typeof TASK_STATUS)[number]" in rendered

    models_dts = (REPO_ROOT / "frontend" / "src" / "types" / "models.d.ts").read_text(
        encoding="utf-8"
    )
    assert "export type TaskStatus = Lowercase<TaskStatusGenerated>" in models_dts
