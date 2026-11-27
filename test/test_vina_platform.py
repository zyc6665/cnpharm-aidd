"""Vina 镜像的科学性回归（``deploy/model-images/k8s/vina/vina_platform.py``）。

锁三件事：

1. 盒子中心只能来自显式 ``center_x/y/z`` 或口袋文件；两者都没有必须明确失败，
   不能再回退到「配体自身质心 / 全蛋白几何中心」的盲对接；
2. 受体进 ``mk_prepare_receptor.py`` 前要清掉结晶水与非金属有机共晶配体，
   同时保留金属离子和修饰残基；
3. ETKDG 嵌入之后必须做力场优化（MMFF，缺参数回退 UFF）。
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VINA_DIR = REPO_ROOT / "deploy" / "model-images" / "k8s" / "vina"

_spec = importlib.util.spec_from_file_location("vina_platform_under_test", VINA_DIR / "vina_platform.py")
vina = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(vina)


def _pdb_line(
    record: str,
    serial: int,
    atom: str,
    resname: str,
    chain: str,
    resseq: int,
    x: float,
    y: float,
    z: float,
) -> str:
    """按 PDB 固定列宽拼一行，保证 17:20=resName / 21=chain 的切片正确。"""
    return (
        f"{record:<6}{serial:>5} {atom:<4} {resname:>3} {chain}{resseq:>4}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           C"
    )


def _receptor_pdb(path: Path) -> Path:
    lines = [
        _pdb_line("ATOM", 1, "N", "MET", "A", 1, 11.0, 10.0, 10.0),
        _pdb_line("ATOM", 2, "CA", "MET", "A", 1, 10.0, 10.0, 10.0),
        _pdb_line("HETATM", 3, "O", "HOH", "A", 101, 13.0, 13.0, 13.0),
        _pdb_line("HETATM", 4, "ZN", "ZN", "A", 201, 14.0, 14.0, 14.0),
        _pdb_line("HETATM", 5, "C1", "LIG", "A", 301, 15.0, 15.0, 15.0),
        # 修饰残基（硒代甲硫氨酸）以 HETATM 出现，但属于聚合物链，必须保留。
        _pdb_line("HETATM", 6, "CA", "MSE", "A", 2, 16.0, 16.0, 16.0),
        _pdb_line("HETATM", 7, "N", "MSE", "A", 2, 16.5, 16.0, 16.0),
        "TER",
        "END",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- 盒子中心


def test_center_prefers_explicit_params():
    center = vina.resolve_docking_center(
        {"center_x": 1.5, "center_y": "2.5", "center_z": 3}, None
    )
    assert center == [1.5, 2.5, 3.0]


def test_center_ignores_non_finite_and_incomplete_params(tmp_path: Path):
    """NaN / inf / 缺轴都算「没提供」，必须继续找口袋文件而不是拼半个中心。"""
    pocket = _receptor_pdb(tmp_path / "pocket.pdb")
    pocket_center = vina.resolve_docking_center({}, pocket)

    for params in (
        {"center_x": float("nan"), "center_y": 0.0, "center_z": 0.0},
        {"center_x": float("inf"), "center_y": 0.0, "center_z": 0.0},
        {"center_x": 1.0, "center_y": 2.0},
        {"center_x": "", "center_y": "", "center_z": ""},
    ):
        assert vina.resolve_docking_center(params, pocket) == pocket_center

    with pytest.raises(SystemExit):
        vina.resolve_docking_center({"center_x": float("inf"), "center_y": 0.0}, None)


def test_center_falls_back_to_pocket_file(tmp_path: Path):
    pocket = _receptor_pdb(tmp_path / "pocket.pdb")
    center = vina.resolve_docking_center({}, pocket)
    # 口袋 PDB 的几何中心（含全部 ATOM/HETATM 坐标）
    assert center is not None
    assert len(center) == 3
    assert all(math.isfinite(value) for value in center)


def test_center_without_any_source_fails_loudly():
    """没有显式中心也没有口袋文件时，宁可直接失败也不盲对接。"""
    with pytest.raises(SystemExit) as excinfo:
        vina.resolve_docking_center({}, None)
    assert "center" in str(excinfo.value).lower()


def test_blind_docking_fallback_is_gone():
    """盒子不再按每个配体单独算（那正是「配体质心」回退的入口）。"""
    source = (VINA_DIR / "vina_platform.py").read_text(encoding="utf-8")
    assert "def box_for" not in source
    assert "box_for(" not in source
    assert "center = docking_center" in source


# ---------------------------------------------------------------- 受体清理


def test_strip_receptor_heterogens_removes_water_and_cocrystal_ligand(tmp_path: Path):
    source = _receptor_pdb(tmp_path / "protein.pdb")
    cleaned_path = vina.strip_receptor_heterogens(source, tmp_path / "clean.pdb")
    cleaned = cleaned_path.read_text(encoding="utf-8")

    assert "ATOM  " in cleaned
    assert "HOH" not in cleaned
    assert "LIG" not in cleaned
    # 金属离子与聚合物型修饰残基保留
    assert " ZN " in cleaned
    assert "MSE" in cleaned
    # 坐标列没被破坏：CA 仍在原位置
    assert "10.000" in cleaned


def test_strip_receptor_heterogens_passes_through_non_pdb(tmp_path: Path):
    cif = tmp_path / "protein.cif"
    cif.write_text("data_test\n", encoding="utf-8")
    assert vina.strip_receptor_heterogens(cif, tmp_path / "clean.pdb") == cif


# ---------------------------------------------------------------- 构象优化


rdkit = pytest.importorskip("rdkit")


def _embedded_ethanol():
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    return mol


def _mmff_energy(mol) -> float:
    from rdkit.Chem import AllChem

    properties = AllChem.MMFFGetMoleculeProperties(mol)
    force_field = AllChem.MMFFGetMoleculeForceField(mol, properties)
    return float(force_field.CalcEnergy())


def test_optimize_geometry_lowers_mmff_energy():
    mol = _embedded_ethanol()
    before = _mmff_energy(mol)

    assert vina.optimize_geometry(mol, max_iters=200) is True

    assert _mmff_energy(mol) <= before + 1e-6


def test_optimize_geometry_falls_back_to_uff(monkeypatch: pytest.MonkeyPatch):
    from rdkit.Chem import AllChem

    mol = _embedded_ethanol()
    calls: dict[str, int] = {}

    monkeypatch.setattr(AllChem, "MMFFHasAllMoleculeParams", lambda _mol: False)
    monkeypatch.setattr(
        AllChem,
        "UFFOptimizeMolecule",
        lambda _mol, maxIters=200: calls.setdefault("max_iters", maxIters),
    )

    assert vina.optimize_geometry(mol) is True
    assert calls["max_iters"] == 200


def test_ensure_3d_returns_optimized_conformer():
    from rdkit import Chem

    mol = Chem.MolFromSmiles("c1ccccc1O")
    prepared = vina.ensure_3d(mol, seed=42)

    assert prepared is not None
    assert prepared.GetNumConformers() == 1
    # 优化过的构象能量应低于「新鲜嵌入但未优化」的同一分子
    fresh = Chem.AddHs(Chem.MolFromSmiles("c1ccccc1O"))
    from rdkit.Chem import AllChem

    assert AllChem.EmbedMolecule(fresh, randomSeed=42) == 0
    assert _mmff_energy(prepared) <= _mmff_energy(fresh) + 1e-3
