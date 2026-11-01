"""drp-runner 接口契约的静态守护（docs/07 §3.6）。

`platform_run_v2.sh` 是全部模型镜像的平台适配入口。shell 脚本不易做行为单测，
这里用静态断言锁住三件容易在重构中悄悄丢失的契约：

- 收到 SIGTERM 必须注册 `trap` 并尽力上传已产出物后以退出码 13 结束（超时语义）；
- 过渡期必须同时识别 7 个 `DRP_*` 环境变量（与既有 SCIMINER_* 并存）；
- 退出码必须覆盖 10/11/12/13 四类失败语义。

并用 `bash -n` 保证脚本语法始终可解析（Windows 无 bash 时跳过）。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (
    ROOT
    / "deploy"
    / "kubernetes"
    / "model-image-template"
    / "platform_adaptor"
    / "platform_run_v2.sh"
)

DRP_VARIABLES = (
    "DRP_TASK_FILE",
    "DRP_RESULT_FILE",
    "DRP_OUT_DIR",
    "DRP_MODEL_ENTRY",
    "DRP_DEVICE",
    "DRP_HEARTBEAT_SEC",
    "DRP_MAX_MINUTES",
)


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_installs_sigterm_trap_and_exits_13() -> None:
    source = _source()
    assert "trap 'on_term' TERM" in source
    # 超时分支必须先尽力上传再以 13 退出
    assert "object_storage.py" in source
    assert "exit 13" in source


def test_recognises_all_drp_variables() -> None:
    source = _source()
    for name in DRP_VARIABLES:
        assert name in source, f"platform_run_v2.sh 缺少 {name}"


def test_maps_failure_exit_codes() -> None:
    source = _source()
    for code in ("exit 10", "exit 11", "exit 12", "exit 13"):
        assert code in source, f"platform_run_v2.sh 缺少退出码映射 {code}"


def test_script_parses_with_bash() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash 不可用，跳过语法校验")
    completed = subprocess.run(
        [bash, "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
