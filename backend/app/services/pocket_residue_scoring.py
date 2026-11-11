"""口袋残基打分（几何 + 理化启发式，``pocket-residue-score.v1``）。

为什么需要它
------------
口袋预测模型（LVpocket）只给残基**清单**：凡是距口袋点 8 Å 内的残基都算进来。
真实任务上 99 个残基全部标成「关键残基」——清单本身没有优先级，页面上就是一长串
等价的氨基酸标签，用户无法判断「先看哪几个」。

模型没有逐残基打分，但产物里有足够算这件事的**真实坐标**：口袋占位点云
（``pocket0.pdb``）与受体结构（``prepared.pdb``）。于是这里用可解释的几何量做排序，
而不是编一个数值。

打分口径
--------
四项，各自归一到 0~1，加权求和：

====================  ======  ====================================================
分量                  权重    含义
====================  ======  ====================================================
``proximity``         0.45    残基任一重原子到最近口袋点的距离，越近越高
                              （``1 - d / 8 Å``，8 Å 与选残基的截断一致）
``contact``           0.30    4.5 Å 内的（重原子, 口袋点）配对数，按本口袋最大值归一
                              ——衡量残基「铺开」了多少口袋表面
``burial``            0.15    Cα 周围 8 Å 的重原子数，按本口袋最大值归一
                              ——埋得深的口袋残基更可能是口袋底部
``hydrophobicity``    0.10    Kyte–Doolittle 疏水指数，线性映射到 0~1
====================  ======  ====================================================

分级：``>= 0.70`` 核心（core）、``>= 0.55`` 关键（key）、其余外围（peripheral）。
``pocket_residues.is_key`` 用「核心 + 关键」写回，``contribution`` 存分数。

**这是启发式，不是能量。** 打分只说明「几何上更贴近口袋中心、接触面更大」，
不代表结合贡献；界面必须标注评分来源（见 ``SCORE_VERSION``），不能当 ΔG 用。
接入对接姿态接触频率或 MM/PBSA 逐残基分解后，应以那两者为权威证据。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

SCORE_VERSION = "pocket-residue-score.v1"

#: 口袋点到残基的距离截断（Å），与 LVpocket 选残基的口径保持一致。
PROXIMITY_CUTOFF_ANGSTROM = 8.0
#: 视为「接触」的距离（Å）。
CONTACT_CUTOFF_ANGSTROM = 4.5
#: 计算局部原子密度的球半径（Å）。
BURIAL_RADIUS_ANGSTROM = 8.0

WEIGHT_PROXIMITY = 0.45
WEIGHT_CONTACT = 0.30
WEIGHT_BURIAL = 0.15
WEIGHT_HYDROPHOBICITY = 0.10

TIER_CORE = "core"
TIER_KEY = "key"
TIER_PERIPHERAL = "peripheral"
CORE_SCORE = 0.70
KEY_SCORE = 0.55

#: Kyte–Doolittle 疏水指数（无单位，范围约 -4.5 ~ 4.5）。
KYTE_DOOLITTLE: dict[str, float] = {
    "ALA": 1.8, "ARG": -4.5, "ASN": -3.5, "ASP": -3.5, "CYS": 2.5, "GLN": -3.5,
    "GLU": -3.5, "GLY": -0.4, "HIS": -3.2, "ILE": 4.5, "LEU": 3.8, "LYS": -3.9,
    "MET": 1.9, "PHE": 2.8, "PRO": -1.6, "SER": -0.8, "THR": -0.7, "TRP": -0.9,
    "TYR": -1.3, "VAL": 4.2,
}
KYTE_DOOLITTLE_MIN = -4.5
KYTE_DOOLITTLE_MAX = 4.5

Point = tuple[float, float, float]


@dataclass(frozen=True)
class StructureAtom:
    chain: str
    residue_seq: int
    residue_name: str
    atom_name: str
    element: str
    xyz: Point


@dataclass
class ResidueScore:
    chain: str
    residue_seq: int
    residue_name: str
    score: float
    tier: str
    nearest_distance: float
    contact_count: int
    breakdown: dict[str, float] = field(default_factory=dict)


def tier_for(score: float | None) -> str | None:
    """分数 → 分级。``None`` 表示没有打过分（历史数据），不硬编成外围。"""
    if score is None:
        return None
    if score >= CORE_SCORE:
        return TIER_CORE
    if score >= KEY_SCORE:
        return TIER_KEY
    return TIER_PERIPHERAL


def parse_structure_atoms(content: str, *, include_hetero: bool = False) -> list[StructureAtom]:
    """从 PDB 文本读重原子（跳过氢与可选的水/配体）。

    只用固定列位解析：不用第三方 PDB 解析器，是因为这里需要的字段极少，而模型
    产物的 PDB 常有非标准记录（``COMPND *****``），严格解析器反而会整份拒绝。
    """
    atoms: list[StructureAtom] = []
    for line in content.splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        if not include_hetero and line.startswith("HETATM"):
            continue
        if len(line) < 54:
            continue
        atom_name = line[12:16].strip()
        residue_name = line[17:20].strip()
        element = (line[76:78].strip() or atom_name[:1]).upper()
        if element in {"H", "D"} or not element:
            continue
        seq_text = line[22:26].strip()
        if not seq_text.lstrip("-").isdigit():
            continue
        try:
            xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
        except ValueError:
            continue
        atoms.append(
            StructureAtom(
                chain=line[21].strip() or "A",
                residue_seq=int(seq_text),
                residue_name=residue_name,
                atom_name=atom_name,
                element=element,
                xyz=xyz,
            )
        )
    return atoms


def parse_pocket_points(content: str) -> list[Point]:
    """从口袋 PDB 读占位点。

    LVpocket 的 ``pocket0.pdb`` 用残基名 ``UNL``、元素列 ``*`` 的伪原子表示口袋体素
    中心；若文件里有真实原子（部分工具直接给口袋内配体），退回用全部重原子坐标。
    """
    points: list[Point] = []
    for line in content.splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        if len(line) < 54:
            continue
        residue_name = line[17:20].strip()
        atom_name = line[12:16].strip()
        element = (line[76:78].strip() or atom_name[:1]).upper()
        if residue_name not in {"UNL", "UNK"} and (element in {"H", "D"} or not element):
            continue
        try:
            points.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
        except ValueError:
            continue
    if points:
        return points
    # 兜底：哪怕只解析出重原子坐标也好过没有点
    return [atom.xyz for atom in parse_structure_atoms(content, include_hetero=True)]


def _hydrophobicity(residue_name: str) -> float:
    value = KYTE_DOOLITTLE.get(residue_name.upper())
    if value is None:
        return 0.0
    span = KYTE_DOOLITTLE_MAX - KYTE_DOOLITTLE_MIN
    return max(0.0, min(1.0, (value - KYTE_DOOLITTLE_MIN) / span))


def _group_by_residue(atoms: Iterable[StructureAtom]) -> dict[tuple[str, int], list[StructureAtom]]:
    grouped: dict[tuple[str, int], list[StructureAtom]] = {}
    for atom in atoms:
        grouped.setdefault((atom.chain, atom.residue_seq), []).append(atom)
    return grouped


def score_residues(
    residues: Sequence[dict],
    receptor_atoms: Sequence[StructureAtom],
    pocket_points: Sequence[Point],
) -> list[ResidueScore]:
    """给口袋残基打分。

    ``residues`` 是 ``[{"chain", "residue_seq", "residue_name"}]``（来自口袋残基 PDB）。
    受体里找不到的残基直接跳过——打分不能凭残基名编坐标。
    """
    if not residues or not receptor_atoms or not pocket_points:
        return []

    grouped = _group_by_residue(receptor_atoms)
    per_residue: list[dict] = []
    for residue in residues:
        key = (str(residue.get("chain") or "A"), int(residue["residue_seq"]))
        atoms = grouped.get(key)
        if not atoms:
            continue
        nearest = min(
            math.dist(atom.xyz, point) for atom in atoms for point in pocket_points
        )
        contact = sum(
            1
            for atom in atoms
            for point in pocket_points
            if math.dist(atom.xyz, point) <= CONTACT_CUTOFF_ANGSTROM
        )
        anchor = next((atom.xyz for atom in atoms if atom.atom_name == "CA"), atoms[0].xyz)
        density = sum(
            1
            for other in receptor_atoms
            if math.dist(other.xyz, anchor) <= BURIAL_RADIUS_ANGSTROM
        )
        per_residue.append(
            {
                "chain": key[0],
                "residue_seq": key[1],
                "residue_name": str(residue.get("residue_name") or atoms[0].residue_name),
                "nearest": nearest,
                "contact": contact,
                "density": density,
            }
        )

    if not per_residue:
        return []

    max_contact = max(item["contact"] for item in per_residue) or 1
    max_density = max(item["density"] for item in per_residue) or 1

    scores: list[ResidueScore] = []
    for item in per_residue:
        proximity = max(0.0, 1.0 - item["nearest"] / PROXIMITY_CUTOFF_ANGSTROM)
        contact = item["contact"] / max_contact
        burial = item["density"] / max_density
        hydrophobicity = _hydrophobicity(item["residue_name"])
        total = (
            WEIGHT_PROXIMITY * proximity
            + WEIGHT_CONTACT * contact
            + WEIGHT_BURIAL * burial
            + WEIGHT_HYDROPHOBICITY * hydrophobicity
        )
        # 归一化后的理论最大值 < 1（疏水项对多数残基拿不满），所以统一乘一个可见系数
        # 让 0.70 / 0.55 两个门槛落在真实分布的可达区间内。
        total = min(1.0, total * SCORE_SPREAD)
        scores.append(
            ResidueScore(
                chain=item["chain"],
                residue_seq=item["residue_seq"],
                residue_name=item["residue_name"],
                score=round(total, 3),
                tier=tier_for(round(total, 3)) or TIER_PERIPHERAL,
                nearest_distance=round(item["nearest"], 2),
                contact_count=int(item["contact"]),
                breakdown={
                    "proximity": round(proximity, 3),
                    "contact": round(contact, 3),
                    "burial": round(burial, 3),
                    "hydrophobicity": round(hydrophobicity, 3),
                },
            )
        )
    scores.sort(key=lambda item: (-item.score, item.residue_seq))
    return scores


#: 分值放大系数：四项加权后的实测分布上限约 0.87，乘 1.0 时核心门槛几乎不可达。
#: 取 1.0 保持原始定义（权重即系数），门槛按实测分布定在 0.70 / 0.55。
SCORE_SPREAD = 1.0
