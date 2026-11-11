"""口袋残基打分（``pocket-residue-score.v1``）的纯函数测试。

不连数据库：打分的输入只有坐标与残基三元组，用构造的小 PDB 就能把口径钉住。
真值链路由 ``test_domain_results.py`` 覆盖。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.targets import PocketResidue  # noqa: E402
from app.services.domain_targets import serialize_residue  # noqa: E402
from app.services.pocket_residue_scoring import (  # noqa: E402
    CORE_SCORE,
    KEY_SCORE,
    TIER_CORE,
    TIER_KEY,
    TIER_PERIPHERAL,
    parse_pocket_points,
    parse_structure_atoms,
    score_residues,
    tier_for,
)


def _atom(
    serial: int,
    name: str,
    resname: str,
    chain: str,
    seq: int,
    xyz: tuple[float, float, float],
    element: str,
    record: str = "ATOM",
) -> str:
    x, y, z = xyz
    return (
        f"{record:<6s}{serial:5d} {name:<4s} {resname:>3s} {chain}{seq:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {element:>2s}"
    )


def _point(serial: int, xyz: tuple[float, float, float]) -> str:
    return _atom(serial, "C", "UNL", "A", 1, xyz, "*", record="HETATM")


def test_parse_structure_atoms_keeps_heavy_atoms_and_skips_hydrogens():
    content = "\n".join(
        [
            "COMPND    *****",
            _atom(1, "N", "ALA", "A", 1, (0.0, 0.0, 0.0), "N"),
            _atom(2, "H", "ALA", "A", 1, (0.4, 0.0, 0.0), "H"),
            _atom(3, "CA", "ALA", "A", 1, (1.0, 0.0, 0.0), "C"),
            _atom(4, "C1", "LIG", "A", 900, (5.0, 5.0, 5.0), "C", record="HETATM"),
        ]
    )
    atoms = parse_structure_atoms(content)
    assert [(atom.atom_name, atom.residue_name) for atom in atoms] == [("N", "ALA"), ("CA", "ALA")]
    assert atoms[1].xyz == (1.0, 0.0, 0.0)
    assert atoms[1].chain == "A" and atoms[1].residue_seq == 1


def test_parse_pocket_points_reads_unl_placeholders():
    content = "\n".join([_point(1, (0.0, 0.0, 0.0)), _point(2, (1.0, 1.0, 1.0))])
    assert parse_pocket_points(content) == [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)]


def test_parse_pocket_points_falls_back_to_real_atoms():
    content = _atom(1, "C1", "LIG", "A", 900, (2.0, 0.0, 0.0), "C", record="HETATM")
    assert parse_pocket_points(content) == [(2.0, 0.0, 0.0)]


def test_tier_thresholds_are_the_documented_ones():
    assert tier_for(CORE_SCORE) == TIER_CORE
    assert tier_for(CORE_SCORE - 0.001) == TIER_KEY
    assert tier_for(KEY_SCORE) == TIER_KEY
    assert tier_for(KEY_SCORE - 0.001) == TIER_PERIPHERAL
    assert tier_for(None) is None


def _scored_residues():
    """三个残基：A1 贴住口袋中心、A3 在边缘、A2 远离口袋。"""
    receptor = "\n".join(
        [
            _atom(1, "N", "ALA", "A", 1, (1.0, 0.0, 0.0), "N"),
            _atom(2, "CA", "ALA", "A", 1, (1.5, 0.0, 0.0), "C"),
            _atom(3, "C", "ALA", "A", 1, (2.0, 0.0, 0.0), "C"),
            _atom(4, "O", "ALA", "A", 1, (2.5, 0.5, 0.0), "O"),
            _atom(5, "N", "LEU", "A", 3, (6.0, 0.0, 0.0), "N"),
            _atom(6, "CA", "LEU", "A", 3, (6.5, 0.0, 0.0), "C"),
            _atom(7, "N", "LYS", "A", 2, (20.0, 0.0, 0.0), "N"),
            _atom(8, "CA", "LYS", "A", 2, (20.5, 0.0, 0.0), "C"),
        ]
    )
    pocket = "\n".join(
        [
            _point(1, (0.0, 0.0, 0.0)),
            _point(2, (1.0, 0.0, 0.0)),
            _point(3, (2.0, 0.0, 0.0)),
        ]
    )
    residues = [
        {"chain": "A", "residue_seq": 1, "residue_name": "ALA"},
        {"chain": "A", "residue_seq": 2, "residue_name": "LYS"},
        {"chain": "A", "residue_seq": 3, "residue_name": "LEU"},
    ]
    return score_residues(
        residues, parse_structure_atoms(receptor), parse_pocket_points(pocket)
    )


def test_residues_closest_to_the_pocket_rank_first():
    scored = _scored_residues()
    assert [item.residue_seq for item in scored] == [1, 3, 2]
    assert scored[0].score > scored[1].score > scored[2].score
    # A1 的 N 原子正落在口袋点上（距离 0），A3 最近 4 Å，A2 在 18 Å 外
    assert [item.nearest_distance for item in scored] == [0.0, 4.0, 18.0]


def test_tiers_follow_the_score_bands():
    scored = {item.residue_seq: item for item in _scored_residues()}
    assert scored[1].tier == TIER_CORE
    assert scored[2].tier == TIER_PERIPHERAL
    assert scored[3].tier in {TIER_KEY, TIER_PERIPHERAL}
    assert set(scored[1].breakdown) == {"proximity", "contact", "burial", "hydrophobicity"}


def test_residues_missing_from_the_receptor_are_skipped():
    """受体里没有的残基不能凭残基名编一个坐标。"""
    receptor = parse_structure_atoms(_atom(1, "CA", "ALA", "A", 1, (1.0, 0.0, 0.0), "C"))
    points = parse_pocket_points(_point(1, (0.0, 0.0, 0.0)))
    scored = score_residues(
        [{"chain": "A", "residue_seq": 99, "residue_name": "GLY"}], receptor, points
    )
    assert scored == []


def test_scoring_returns_empty_without_geometry():
    assert score_residues([], [], []) == []


def test_serialize_residue_exposes_derived_tier():
    """分级由分数派生：列里只有分数，接口补 tier，避免「0.72 却标外围」的自相矛盾。"""
    residue = PocketResidue(
        id="r1",
        pocket_id="p1",
        chain="A",
        residue_seq=15,
        residue_name="LEU",
        is_key=True,
        contribution=0.72,
    )
    payload = serialize_residue(residue)
    assert payload["contribution"] == 0.72
    assert payload["score_tier"] == TIER_CORE

    unknown = PocketResidue(
        id="r2",
        pocket_id="p1",
        chain="A",
        residue_seq=16,
        residue_name="GLY",
        is_key=True,
        contribution=None,
    )
    assert serialize_residue(unknown)["score_tier"] is None
