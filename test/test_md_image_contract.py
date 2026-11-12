"""MD 结果页两张图的字段契约（`docs/26` H-3）。

症状：`analysis.csv` 里从来没有 `rmsf_nm` / `rg_nm`，页面「RMSF」与「Rg」两张图
恒为空白；而分析脚本只跑了 `gmx energy` 与 `gmx rms`。这里的测试锁定三件事：

1. 镜像确实实现了回转半径（逐帧量，进 `analysis.csv` 的 `rg_nm` 列）；
2. RMSF 走**逐残基**表 `rmsf.csv`（RMSF 是时间平均量，塞进逐帧时间序列是错的）；
3. `md_trajectory@1` 标准承认 `rmsf_csv` 这个 role——否则产物会被标准校验拒绝。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = REPO_ROOT / "deploy" / "model-images" / "k8s" / "gromacs"
STANDARD_YAML = REPO_ROOT / "backend" / "app" / "artifact_standards" / "schemas" / "md_trajectory.v1.yaml"

if str(IMAGE_DIR) not in sys.path:
    sys.path.insert(0, str(IMAGE_DIR))

_spec = importlib.util.spec_from_file_location("gromacs_platform_under_test", IMAGE_DIR / "gromacs_platform.py")
gromacs = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gromacs)

PDB = """\
ATOM      1  N   MET A   1      11.000  10.000  10.000  1.00 20.00           N
ATOM      2  CA  MET A   1      10.000  10.000  10.000  1.00 20.00           C
ATOM      3  C   MET A   1       9.000  10.000  10.000  1.00 20.00           C
ATOM      4  CA  LYS A 745      10.000  11.000  10.000  1.00 20.00           C
ATOM      5  CA  LYS A 745      10.500  11.500  10.000  1.00 20.00           C
ATOM      6  CA  GLY B   2      12.000  12.000  12.000  1.00 20.00           C
HETATM    7  O   HOH A 900      13.000  13.000  13.000  1.00 20.00           O
"""


def test_standard_declares_rmsf_csv_role():
    text = STANDARD_YAML.read_text(encoding="utf-8")
    assert "role: rmsf_csv" in text
    assert "recommended_name: rmsf.csv" in text


def test_backbone_residues_uses_ca_atoms_in_order(tmp_path: Path):
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(PDB, encoding="utf-8")
    assert gromacs.backbone_residues(pdb) == [
        ("A", "1", "MET"),
        ("A", "745", "LYS"),
        ("B", "2", "GLY"),
    ]


def test_backbone_residues_tolerates_missing_file(tmp_path: Path):
    assert gromacs.backbone_residues(tmp_path / "absent.pdb") == []


def test_analysis_and_rmsf_columns_are_declared():
    source = (IMAGE_DIR / "gromacs_platform.py").read_text(encoding="utf-8")
    # 回转半径进逐帧时间序列
    assert 'writer.writerow(columns + ["rmsd_nm", "rg_nm"])' in source
    assert '"gyrate"' in source
    # RMSF 单独一张逐残基表
    assert 'writer.writerow(["residue_seq", "residue_name", "rmsf_nm"])' in source
    assert '"rmsf_csv": file_ref(output_dir, "artifacts/rmsf.csv")' in source
