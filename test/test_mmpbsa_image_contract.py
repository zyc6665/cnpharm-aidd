"""自由能表的字段契约：镜像产物列名必须与前端解析列名逐字一致。

这条契约此前是断的（`docs/26` H-1）：镜像 `mmpbsa_platform.py` 只写一行汇总
（`molecule_id, delta_g_bind_kcal_mol, delta_g_std_kcal_mol, frames`），而前端
`frontend/src/views/md/analysis.ts` 的 `buildFreeEnergyRows()` 按
`frame / delta_g_*` 逐帧解析——任务成功、页面却是「暂无可用的自由能数据」。
mock 包 `example/mock-models/gmx-mmpbsa-free-energy` 一直是按逐帧契约写的，
所以这类不一致在 mock 演示里看不出来，只有真镜像跑完才露。

测试直接加载真镜像的模块（它只 import 标准库 + 同目录的 `gromacs_platform`），
并把前端源文件里的列名解析出来比对——任一侧改名都会红。
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = REPO_ROOT / "deploy" / "model-images" / "k8s" / "gromacs"
FRONTEND_ANALYSIS = REPO_ROOT / "frontend" / "src" / "views" / "md" / "analysis.ts"

if str(IMAGE_DIR) not in sys.path:
    sys.path.insert(0, str(IMAGE_DIR))

_spec = importlib.util.spec_from_file_location("mmpbsa_platform_under_test", IMAGE_DIR / "mmpbsa_platform.py")
mmpbsa = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mmpbsa)

EXPECTED_COLUMNS = [
    "frame",
    "delta_g_total",
    "delta_g_vdw",
    "delta_g_electrostatic",
    "delta_g_polar_solvation",
    "delta_g_nonpolar_solvation",
    "delta_g_sasa",
]


def _frontend_row_keys() -> set[str]:
    """从 `buildFreeEnergyRows` 的对象字面量里取出前端实际读取的列名。"""
    text = FRONTEND_ANALYSIS.read_text(encoding="utf-8")
    start = text.index("export function buildFreeEnergyRows")
    end = text.index("export function downsampleSeries")
    body = text[start:end]
    return set(re.findall(r"^\s{4,}([a-z][a-z0-9_]*):", body, flags=re.MULTILINE))


def test_image_columns_match_frontend():
    assert mmpbsa.FREE_ENERGY_COLUMNS == EXPECTED_COLUMNS
    frontend_keys = _frontend_row_keys()
    assert frontend_keys == set(EXPECTED_COLUMNS), (
        "镜像列名与前端解析列名不一致："
        f"仅前端有 {sorted(frontend_keys - set(EXPECTED_COLUMNS))}，"
        f"仅镜像有 {sorted(set(EXPECTED_COLUMNS) - frontend_keys)}"
    )


def test_build_frame_rows_maps_gmx_mmpbsa_headers():
    header = ["Frame", "ΔTOTAL", "ΔVDWAALS", "ΔEEL", "ΔEGB", "ΔESURF"]
    data = [
        ["1", "-42.5", "-45.1", "-28.4", "37.6", "-3.4"],
        ["2", "-41.0", "-44.8", "-27.9", "38.1", "-3.2"],
    ]
    rows = mmpbsa.build_frame_rows(header, data)
    assert [row["frame"] for row in rows] == [1, 2]
    assert rows[0]["delta_g_total"] == "-42.5000"
    assert rows[0]["delta_g_vdw"] == "-45.1000"
    assert rows[0]["delta_g_electrostatic"] == "-28.4000"
    assert rows[0]["delta_g_polar_solvation"] == "37.6000"
    assert rows[0]["delta_g_nonpolar_solvation"] == "-3.4000"
    # gmx_MMPBSA 的 GB 输出没有 SASA 列：留空而不是补 0
    assert rows[0]["delta_g_sasa"] == ""


def test_build_frame_rows_supports_pb_headers():
    header = ["Frame", "TOTAL", "VDWAALS", "EEL", "EPB", "ENPOLAR"]
    rows = mmpbsa.build_frame_rows(header, [["7", "-30.2", "-20.0", "-15.5", "9.9", "-4.6"]])
    assert rows[0]["frame"] == 7
    assert rows[0]["delta_g_polar_solvation"] == "9.9000"
    assert rows[0]["delta_g_nonpolar_solvation"] == "-4.6000"


def test_build_frame_rows_without_total_returns_empty():
    assert mmpbsa.build_frame_rows(["Frame", "VDWAALS"], [["1", "-45.1"]]) == []


def test_build_frame_rows_falls_back_to_row_position():
    header = ["TOTAL", "VDWAALS"]
    rows = mmpbsa.build_frame_rows(header, [["-42.5", "-45.1"], ["-41.0", "-44.8"]])
    assert [row["frame"] for row in rows] == [1, 2]


def test_build_frame_rows_skips_unparsable_rows():
    header = ["Frame", "ΔTOTAL"]
    data = [["1", "-42.5"], ["2", "N/A"], ["3", "-40.0"]]
    rows = mmpbsa.build_frame_rows(header, data)
    assert [row["frame"] for row in rows] == [1, 3]
