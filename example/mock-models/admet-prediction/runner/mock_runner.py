"""Mock runner for the admet-prediction Tool Package.

演示用 mock 执行器：能用 RDKit 真算的理化性质真算（MW / logP / TPSA / HBD /
HBA / RotB / QED / SA / InChIKey）；不能真算的（generation_score /
docking_score / 结合自由能 / MD 轨迹）使用「seed + 输入哈希」的确定性合成值。
所有产物都带 mock_disclaimer，数值不可用于科研决策。

平台通过环境变量调用：
  DRP_TASK_FILE    task.json / request.v1 路径
  DRP_OUT_DIR      产物输出目录
  DRP_RESULT_FILE  result.v2 路径（缺省为 <DRP_OUT_DIR>/result.json）

也可以直接导入 `run(task, out_dir)` 做离线测试（tests/ 就是这么用的）。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SLUG = "admet-prediction"
MODE = "admet"
DISCLAIMER = (
    "本产物由 mock 模型包 admet-prediction 生成，仅用于平台演示与前端联调；"
    "数值为 RDKit 理化性质或基于 seed + 输入哈希的确定性合成值，"
    "不可用于科研、临床或生产决策。"
)

try:  # RDKit is expected to be installed in the python_script environment
    from rdkit import Chem
    from rdkit.Chem import Crippen, Descriptors, Lipinski, QED
    from rdkit.Chem import rdDepictor, rdMolDescriptors

    _RDKIT_OK = True
except Exception:  # pragma: no cover - only when RDKit is missing
    _RDKIT_OK = False


# --------------------------------------------------------------------------- #
# deterministic synthetic helpers
# --------------------------------------------------------------------------- #
def _stable_unit(*parts: Any) -> float:
    text = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _stable_float(seed: Any, low: float, high: float, *parts: Any) -> float:
    return round(low + (high - low) * _stable_unit(seed, *parts), 4)


# --------------------------------------------------------------------------- #
# task / input helpers
# --------------------------------------------------------------------------- #
def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    return task.get("parameters") or task.get("params") or {}


def _inputs(task: dict[str, Any]) -> dict[str, Any]:
    return task.get("inputs") or {}


def _task_id(task: dict[str, Any]) -> str:
    inner = task.get("task") or {}
    return str(task.get("task_id") or inner.get("id") or "mock-task")


def _base_dir(task: dict[str, Any]) -> Path:
    execution = task.get("execution") or {}
    work = task.get("work_dir") or execution.get("work_dir") or "."
    return Path(work)


def _resolve(task: dict[str, Any], raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = _base_dir(task) / path
    return path


def _file_path(task: dict[str, Any], slot: str, role: str | None = None) -> Path | None:
    artifact = _inputs(task).get(slot) or {}
    files = artifact.get("files") or {}
    if role and role in files:
        raw = files[role].get("path")
    else:
        raw = next((item.get("path") for item in files.values() if item.get("path")), None)
    if not raw:
        return None
    return _resolve(task, str(raw))


def _read_bytes(path: Path | None) -> bytes:
    if path is None:
        return b""
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _input_hash(task: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps(_parameters(task), sort_keys=True, default=str).encode("utf-8"))
    for artifact in _inputs(task).values():
        for ref in (artifact.get("files") or {}).values():
            raw = ref.get("path")
            if raw:
                digest.update(_read_bytes(_resolve(task, str(raw))))
    return digest.hexdigest()


def _read_smiles(path: Path | None) -> list[str]:
    if path is None or not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        lookup = {str(item).strip().lower(): item for item in headers}
        column = None
        for candidate in ("smiles", "canonical_smiles", "isomeric_smiles", "smile"):
            if candidate in lookup:
                column = lookup[candidate]
                break
        if column is None and headers:
            column = headers[0]
        rows: list[str] = []
        for row in reader:
            value = (row.get(column) or "").strip()
            if value:
                rows.append(value)
        return rows


# --------------------------------------------------------------------------- #
# RDKit property helpers
# --------------------------------------------------------------------------- #
def _mol_from_smiles(smiles: str):
    if not _RDKIT_OK:
        return None
    return Chem.MolFromSmiles(smiles)


def _sa_score(mol) -> float | None:
    # Interpretable heuristic substitute for the original sascorer (which is not
    # shipped in the RDKit wheel). Rewards simplicity, penalises size / rings /
    # stereocentres. Documented in model-card.md as a mock heuristic.
    if mol is None:
        return None
    mw = Descriptors.MolWt(mol)
    rings = rdMolDescriptors.CalcNumRings(mol)
    stereo = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
    rotb = Lipinski.NumRotatableBonds(mol)
    score = 1.0 + 0.012 * max(mw - 150.0, 0.0) + 0.45 * rings + 0.30 * stereo - 0.05 * rotb
    return round(min(10.0, max(1.0, score)), 3)


def _inchi_key(smiles: str) -> str:
    mol = _mol_from_smiles(smiles)
    if mol is None:
        return "MOCK-" + hashlib.sha1(smiles.encode("utf-8")).hexdigest()[:14].upper()
    try:
        return Chem.MolToInchiKey(mol)
    except Exception:
        return "MOCK-" + hashlib.sha1(smiles.encode("utf-8")).hexdigest()[:14].upper()


def _compute_props(smiles: str) -> dict[str, Any] | None:
    mol = _mol_from_smiles(smiles)
    if mol is None:
        return None
    return {
        "smiles": smiles,
        "inchi_key": _inchi_key(smiles),
        "mol_weight": round(Descriptors.MolWt(mol), 3),
        "logp": round(Crippen.MolLogP(mol), 3),
        "tpsa": round(rdMolDescriptors.CalcTPSA(mol), 3),
        "hbd": int(Lipinski.NumHDonors(mol)),
        "hba": int(Lipinski.NumHAcceptors(mol)),
        "rotb": int(Lipinski.NumRotatableBonds(mol)),
        "qed": round(float(QED.qed(mol)), 4),
        "sa_score": _sa_score(mol),
    }


# --------------------------------------------------------------------------- #
# output helpers
# --------------------------------------------------------------------------- #
_CONTENT_TYPES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".sdf": "chemical/x-mdl-sdfile",
    ".pdb": "chemical/x-pdb",
    ".dcd": "application/octet-stream",
    ".md": "text/markdown",
}


def _content_type(filename: str) -> str:
    return _CONTENT_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text(out_dir: Path, subdir: str, filename: str, text: str) -> dict[str, Any]:
    target = out_dir / subdir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {"path": f"{subdir}/{filename}", "sha256": _sha256(target), "content_type": _content_type(filename)}


def _write_bytes(out_dir: Path, subdir: str, filename: str, data: bytes) -> dict[str, Any]:
    target = out_dir / subdir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": f"{subdir}/{filename}", "sha256": _sha256(target), "content_type": _content_type(filename)}


def _write_csv(out_dir: Path, subdir: str, filename: str, fieldnames: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    target = out_dir / subdir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return {"path": f"{subdir}/{filename}", "sha256": _sha256(target), "content_type": _content_type(filename)}


def _artifact(name: str, type_: str, files: dict[str, Any], metadata: dict[str, Any], summary=None, metrics=None):
    return {
        "name": name,
        "type": type_,
        "files": files,
        "metadata": metadata,
        "summary": summary or {},
        "metrics": metrics or {},
    }


def _report(out_dir: Path, task_id: str, extra: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "source_task_id": task_id,
        "package": SLUG,
        "mock": True,
        "mock_disclaimer": DISCLAIMER,
    }
    payload.update(extra)
    ref = _write_text(out_dir, "report", "report.json", json.dumps(payload, ensure_ascii=False, indent=2))
    return _artifact("report", "run_report@1", {"report_json": ref}, {"source_task_id": task_id})


def _table_metadata(task_id: str, id_field: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = {"molecule_id_field": id_field, "source_task_id": task_id}
    if extra:
        meta.update(extra)
    return meta


# --------------------------------------------------------------------------- #
# mode: generation
# --------------------------------------------------------------------------- #
_TEMPLATES = [
    "c1ccc({s})cc1",
    "O=C(O)c1ccc({s})cc1",
    "CC(=O)Nc1ccc({s})cc1",
    "COc1ccc({s})cc1",
    "CC(C)Cc1ccc({s})cc1",
    "c1ccc2c(c1)ccc({s})c2",
    "O=C(O)c1ccc(cc1){s}",
    "CC(=O)Oc1ccc({s})cc1",
]
_SUBSTITUENTS = [
    "C", "CC", "CCC", "OC", "OCC", "N", "N(C)C", "Cl", "F", "Br",
    "C(=O)O", "C(=O)N", "C(=O)OC", "S(=O)(=O)N", "C#N", "C(F)(F)F",
    "CO", "CC(C)C", "c1ccccc1", "n1ccccc1", "Oc1ccccc1",
    "C(=O)c1ccccc1", "NC(=O)C", "S(=O)(=O)C", "CCN", "CCO", "CN(C)C",
]
_FALLBACK_SMILES = [
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "CC(=O)CC(c1ccccc1)c1c(O)c2ccccc2oc1=O",
    "CC(C)(C)NCC(O)c1ccc(O)c(CO)c1",
    "CCN(CC)CCNC(=O)c1cc(Cl)c(N)cc1OC",
    "CC(C)NCC(O)COc1cccc2ccccc12",
    "Clc1ccc(cc1)C(c1ccccc1)N1CCN(CC1)CCOC(c1ccccc1)c1ccccc1",
    "COc1cc2c(cc1OC)C(=O)C(CC1CCN(Cc3ccccc3)CC1)C2",
]


def _generate_candidates(seed: Any) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for template in _TEMPLATES:
        for sub in _SUBSTITUENTS:
            smiles = template.format(s=sub)
            mol = _mol_from_smiles(smiles)
            if mol is None:
                continue
            canonical = Chem.MolToSmiles(mol)
            if canonical in seen:
                continue
            seen.add(canonical)
            candidates.append(smiles)
    candidates.extend(smiles for smiles in _FALLBACK_SMILES if smiles not in seen)
    # deterministic shuffle
    candidates.sort(key=lambda item: _stable_unit(seed, "order", item))
    return candidates


def build_generation(task: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    params = _parameters(task)
    task_id = _task_id(task)
    seed = int(params.get("seed", 42))
    num = int(params.get("num_molecules", 100))
    mw_min = float(params.get("mw_min", 200))
    mw_max = float(params.get("mw_max", 600))
    logp_min = float(params.get("logp_min", -1))
    logp_max = float(params.get("logp_max", 5))

    selected: list[dict[str, Any]] = []
    relax: list[dict[str, Any]] = []
    for smiles in _generate_candidates(seed):
        props = _compute_props(smiles)
        if props is None:
            continue
        in_range = (
            mw_min <= props["mol_weight"] <= mw_max
            and logp_min <= props["logp"] <= logp_max
        )
        record = dict(props)
        record["generation_score"] = _stable_float(seed, 0.30, 0.99, smiles, "gen")
        if in_range:
            selected.append(record)
        else:
            relax.append(record)
        if len(selected) >= num:
            break
    if len(selected) < num:
        for record in relax:
            if len(selected) >= num:
                break
            selected.append(record)

    selected.sort(key=lambda item: item["generation_score"], reverse=True)
    rows = []
    for index, record in enumerate(selected, start=1):
        row = dict(record)
        row["rank"] = index
        rows.append(row)

    fields = [
        "smiles", "inchi_key", "mol_weight", "logp", "tpsa", "hbd", "hba",
        "rotb", "qed", "sa_score", "generation_score", "rank",
    ]
    table = _write_csv(out_dir, "molecules", "molecules.csv", fields, rows)
    meta = _write_text(
        out_dir, "molecules", "metadata.json",
        json.dumps(_table_metadata(task_id, "smiles", {"mock": True}), ensure_ascii=False, indent=2),
    )
    molecules = _artifact(
        "molecules", "molecule_table@1",
        {"table_file": table, "metadata_json": meta},
        _table_metadata(task_id, "smiles", {"mock": True}),
        summary={"num_molecules": len(rows), "mock": True},
        metrics={"num_molecules": len(rows)},
    )
    report = _report(out_dir, task_id, {"kind": "molecule_generation", "seed": seed, "num_molecules": len(rows)})
    return {
        "result_version": "aidd.sciminer/result",
        "artifacts": {"molecules": molecules, "report": report},
        "relations": [{"from": "report", "to": "molecules", "type": "describes"}],
        "summary": {"package": SLUG, "mock": True, "num_molecules": len(rows)},
        "metrics": {"num_molecules": len(rows)},
    }


# --------------------------------------------------------------------------- #
# mode: peptide
# --------------------------------------------------------------------------- #
_AA_MASS = {
    "A": 89.09, "C": 121.16, "D": 133.10, "E": 147.13, "F": 165.19,
    "G": 75.07, "H": 155.16, "I": 131.17, "K": 146.19, "L": 131.17,
    "M": 149.21, "N": 132.12, "P": 115.13, "Q": 146.15, "R": 174.20,
    "S": 105.09, "T": 119.12, "V": 117.15, "W": 204.23, "Y": 181.19,
}
_RESIDUES = "ACDEFGHIKLMNPQRSTVWY"


def build_peptide(task: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    params = _parameters(task)
    task_id = _task_id(task)
    seed = int(params.get("seed", 42))
    num = int(params.get("num_peptides", 50))
    length_min = max(2, int(params.get("length_min", 8)))
    length_max = max(length_min, int(params.get("length_max", 15)))

    rows = []
    for index in range(num):
        span = length_max - length_min + 1
        length = length_min + int(_stable_unit(seed, index, "len") * span)
        length = max(length_min, min(length_max, length))
        sequence = "".join(
            _RESIDUES[int(_stable_unit(seed, index, position, "aa") * len(_RESIDUES)) % len(_RESIDUES)]
            for position in range(length)
        )
        mass = sum(_AA_MASS[aa] for aa in sequence) - 18.015 * (length - 1)
        positive = sum(1 for aa in sequence if aa in "KR") + 0.1 * sum(1 for aa in sequence if aa == "H")
        negative = sum(1 for aa in sequence if aa in "DE")
        net_charge = round(positive - negative, 3)
        isoelectric = round(max(3.0, min(12.0, 7.0 - 0.35 * (positive - negative))), 2)
        hydrophobic = round(sum(1 for aa in sequence if aa in "AVILMFWC") / length, 4)
        design_score = _stable_float(seed, 0.30, 0.99, sequence, "design")
        rows.append(
            {
                "peptide_sequence": sequence,
                "length": length,
                "mol_weight": round(mass, 2),
                "net_charge": net_charge,
                "isoelectric_point": isoelectric,
                "hydrophobic_ratio": hydrophobic,
                "design_score": design_score,
            }
        )
    rows.sort(key=lambda row: row["design_score"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    fields = [
        "peptide_sequence", "length", "mol_weight", "net_charge",
        "isoelectric_point", "hydrophobic_ratio", "design_score", "rank",
    ]
    table = _write_csv(out_dir, "peptides", "peptides.csv", fields, rows)
    meta = _write_text(
        out_dir, "peptides", "metadata.json",
        json.dumps(_table_metadata(task_id, "peptide_sequence", {"mock": True}), ensure_ascii=False, indent=2),
    )
    peptides = _artifact(
        "peptides", "molecule_table@1",
        {"table_file": table, "metadata_json": meta},
        _table_metadata(task_id, "peptide_sequence", {"mock": True}),
        summary={"num_peptides": len(rows), "mock": True},
        metrics={"num_peptides": len(rows)},
    )
    report = _report(out_dir, task_id, {"kind": "peptide_design", "seed": seed, "num_peptides": len(rows)})
    return {
        "result_version": "aidd.sciminer/result",
        "artifacts": {"peptides": peptides, "report": report},
        "relations": [{"from": "report", "to": "peptides", "type": "describes"}],
        "summary": {"package": SLUG, "mock": True, "num_peptides": len(rows)},
        "metrics": {"num_peptides": len(rows)},
    }


# --------------------------------------------------------------------------- #
# mode: admet
# --------------------------------------------------------------------------- #
_TASK_GROUPS = [
    ("Absorption", "admet_absorption"),
    ("Distribution", "admet_distribution"),
    ("Excretion", "admet_excretion"),
    ("Metabolism", "admet_metabolism"),
    ("Toxicology", "admet_toxicity"),
    ("Tox21", "admet_tox21"),
    ("Ecotoxicity", "admet_ecotoxicity"),
    ("LD50", "admet_ld50"),
]


def build_admet(task: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    params = _parameters(task)
    task_id = _task_id(task)
    seed = int(params.get("seed", 42))
    smiles_list = _read_smiles(_file_path(task, "molecules", "table_file"))
    if not smiles_list:
        smiles_list = ["CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O"]

    rows = []
    for smiles in smiles_list:
        props = _compute_props(smiles)
        if props is None:
            continue
        row = dict(props)
        for _group, field in _TASK_GROUPS:
            row[field] = _stable_float(seed, 0.0, 1.0, smiles, field)
        rows.append(row)

    fields = [
        "smiles", "inchi_key", "mol_weight", "logp", "tpsa", "hbd", "hba",
        "rotb", "qed", "sa_score",
    ] + [field for _group, field in _TASK_GROUPS]
    table = _write_csv(out_dir, "properties", "properties.csv", fields, rows)
    meta = _write_text(
        out_dir, "properties", "metadata.json",
        json.dumps(_table_metadata(task_id, "smiles", {"mock": True}), ensure_ascii=False, indent=2),
    )
    properties = _artifact(
        "properties", "molecule_table@1",
        {"table_file": table, "metadata_json": meta},
        _table_metadata(task_id, "smiles", {"mock": True}),
        summary={"num_molecules": len(rows), "mock": True},
        metrics={"num_molecules": len(rows)},
    )
    report = _report(out_dir, task_id, {"kind": "admet_prediction", "num_molecules": len(rows)})
    return {
        "result_version": "aidd.sciminer/result",
        "artifacts": {"properties": properties, "report": report},
        "relations": [{"from": "report", "to": "properties", "type": "describes"}],
        "summary": {"package": SLUG, "mock": True, "num_molecules": len(rows)},
        "metrics": {"num_molecules": len(rows)},
    }


# --------------------------------------------------------------------------- #
# mode: vina
# --------------------------------------------------------------------------- #
def _write_sdf_multimol(out_dir: Path, subdir: str, filename: str, records: list[tuple[str, str]]) -> dict[str, Any]:
    """records = [(mol_name, smiles), ...]; written as a multi-molecule SDF."""
    target = out_dir / subdir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    for name, smiles in records:
        mol = _mol_from_smiles(smiles)
        if mol is None:
            continue
        try:
            rdDepictor.Compute2DCoords(mol)
        except Exception:
            pass
        mol.SetProp("_Name", name)
        blocks.append(Chem.MolToMolBlock(mol))
    if not blocks:
        blocks = ["\n  mock\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n$$$$\n"]
    target.write_text("$$$$\n".join(block.rstrip("\n") for block in blocks) + "\n$$$$\n", encoding="utf-8")
    return {"path": f"{subdir}/{filename}", "sha256": _sha256(target), "content_type": _content_type(filename)}


def build_vina(task: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    params = _parameters(task)
    task_id = _task_id(task)
    seed = int(params.get("seed", 42))
    min_features = int(params.get("pharmacophore_min_features", 3))
    cutoff = float(params.get("docking_score_cutoff", -8.0))
    top_n = int(params.get("top_n", 100))
    smiles_list = _read_smiles(_file_path(task, "ligands", "table_file"))
    if not smiles_list:
        smiles_list = ["CC(=O)Oc1ccccc1C(=O)O", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"]

    ranked_rows = []
    for smiles in smiles_list:
        props = _compute_props(smiles)
        if props is None:
            continue
        features = 2 + int(_stable_unit(seed, smiles, "features") * 6)
        docking_score = _stable_float(seed, -11.5, -4.5, smiles, "dock")
        stage_pharmacophore = features >= min_features
        stage_docking = stage_pharmacophore and docking_score <= cutoff
        stage_rescore = stage_docking
        passes = stage_rescore
        ranked_rows.append(
            {
                "smiles": smiles,
                "inchi_key": props["inchi_key"],
                "mol_weight": props["mol_weight"],
                "logp": props["logp"],
                "qed": props["qed"],
                "stage_pharmacophore": stage_pharmacophore,
                "stage_docking": stage_docking,
                "stage_rescore": stage_rescore,
                "docking_score": docking_score,
                "passes": passes,
            }
        )
    ranked_rows.sort(key=lambda row: row["docking_score"])
    for rank, row in enumerate(ranked_rows[:top_n], start=1):
        row["rank"] = rank
    shown = ranked_rows[:top_n]

    fields = [
        "smiles", "inchi_key", "mol_weight", "logp", "qed",
        "stage_pharmacophore", "stage_docking", "stage_rescore",
        "docking_score", "rank", "passes",
    ]
    table = _write_csv(out_dir, "ranked", "ranked.csv", fields, shown)
    meta = _write_text(
        out_dir, "ranked", "metadata.json",
        json.dumps(_table_metadata(task_id, "smiles", {"mock": True}), ensure_ascii=False, indent=2),
    )
    ranked = _artifact(
        "ranked", "molecule_table@1",
        {"table_file": table, "metadata_json": meta},
        _table_metadata(task_id, "smiles", {"mock": True}),
        summary={"num_ligands": len(shown), "mock": True},
        metrics={"num_ligands": len(shown)},
    )

    top = shown[:10]
    pose_records = [(f"pose-{row['rank']}", row["smiles"]) for row in top]
    structure_file = _write_sdf_multimol(out_dir, "poses", "poses.sdf", pose_records[:1])
    structure_3d = _write_sdf_multimol(out_dir, "poses", "poses.3d.sdf", pose_records)
    poses_meta_payload = {
        "ligand_id": f"pose-{top[0]['rank']}" if top else "pose-1",
        "mock": True,
        "poses": [
            {
                "pose_id": f"pose-{row['rank']}",
                "ligand_smiles": row["smiles"],
                "rank": row["rank"],
                "docking_score": row["docking_score"],
                "rmsd_lb": 0.0,
                "rmsd_ub": 0.0,
                "interactions": [
                    {
                        "residue": "MET769",
                        "chain": "A",
                        "type": "hydrogen_bond",
                        "distance": round(2.6 + 0.4 * _stable_unit(seed, row["smiles"], "hb"), 1),
                    }
                ],
            }
            for row in top
        ],
    }
    poses_meta = _write_text(out_dir, "poses", "metadata.json", json.dumps(poses_meta_payload, ensure_ascii=False, indent=2))
    poses = _artifact(
        "poses", "ligand_structure@1",
        {"structure_file": structure_file, "structure_3d_sdf": structure_3d, "metadata_json": poses_meta},
        {"ligand_id": poses_meta_payload["ligand_id"], "mock": True, "poses": poses_meta_payload["poses"]},
        summary={"num_poses": len(top), "mock": True},
        metrics={"num_poses": len(top)},
    )
    report = _report(out_dir, task_id, {"kind": "virtual_screening", "num_ligands": len(shown), "top_n": top_n})
    return {
        "result_version": "aidd.sciminer/result",
        "artifacts": {"ranked": ranked, "poses": poses, "report": report},
        "relations": [
            {"from": "poses", "to": "ranked", "type": "derived_from"},
            {"from": "report", "to": "ranked", "type": "describes"},
        ],
        "summary": {"package": SLUG, "mock": True, "num_ligands": len(shown)},
        "metrics": {"num_ligands": len(shown)},
    }


# --------------------------------------------------------------------------- #
# mode: md
# --------------------------------------------------------------------------- #
def build_md(task: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    params = _parameters(task)
    task_id = _task_id(task)
    seed = int(params.get("seed", 42))
    force_field = str(params.get("force_field", "amber99sb-ildn"))
    duration_ns = float(params.get("duration_ns", 100))
    temperature_k = float(params.get("temperature_k", 300))
    frames = max(2, min(1000, int(duration_ns * 10)))

    structure = _file_path(task, "complex", "structure_file") or _file_path(task, "complex", "prepared_pdb")
    pdb_bytes = _read_bytes(structure)
    if not pdb_bytes:
        pdb_bytes = b"REMARK mock topology generated without input structure\nEND\n"
    topology = _write_bytes(out_dir, "trajectory", "topology.pdb", pdb_bytes)

    analysis_rows = []
    for frame in range(frames):
        time_ps = round((frame + 1) * (duration_ns * 1000.0 / frames), 3)
        progress = (frame + 1) / frames
        rmsd = round(0.15 + 0.35 * progress + 0.05 * _stable_unit(seed, frame, "rmsd"), 4)
        rmsf = round(0.05 + 0.10 * _stable_unit(seed, "rmsf") + 0.02 * progress, 4)
        rg = round(1.8 + 0.3 * _stable_unit(seed, "rg") + 0.1 * progress, 4)
        temperature = round(temperature_k + 4.0 * (_stable_unit(seed, frame, "temp") - 0.5), 2)
        potential = round(-120000.0 + 8000.0 * progress + 1500.0 * _stable_unit(seed, frame, "pot"), 2)
        analysis_rows.append(
            {
                "time_ps": time_ps,
                "rmsd_nm": rmsd,
                "rmsf_nm": rmsf,
                "rg_nm": rg,
                "temperature_k": temperature,
                "potential_kj_mol": potential,
            }
        )
    analysis = _write_csv(
        out_dir, "trajectory", "analysis.csv",
        ["time_ps", "rmsd_nm", "rmsf_nm", "rg_nm", "temperature_k", "potential_kj_mol"],
        analysis_rows,
    )

    # deterministic pseudo-DCD payload (mock, not a valid binary DCD)
    digest = hashlib.sha256(f"{seed}|{force_field}|{duration_ns}".encode("utf-8")).digest()
    payload = b"MOCKDCD\x00" + b"".join(digest for _ in range(64))
    dcd = _write_bytes(out_dir, "trajectory", "trajectory.dcd", payload)

    md_meta = {
        "source_task_id": task_id,
        "mock": True,
        "force_field": force_field,
        "duration_ns": duration_ns,
        "frames": frames,
        "temperature_k": temperature_k,
        "note": "trajectory.dcd is a deterministic placeholder, not a real MD trajectory",
    }
    meta = _write_text(out_dir, "trajectory", "metadata.json", json.dumps(md_meta, ensure_ascii=False, indent=2))
    trajectory = _artifact(
        "trajectory", "md_trajectory@1",
        {"topology_pdb": topology, "trajectory_dcd": dcd, "analysis_csv": analysis, "metadata_json": meta},
        md_meta,
        summary={"frames": frames, "mock": True},
        metrics={"frames": frames, "duration_ns": duration_ns},
    )
    report = _report(out_dir, task_id, {"kind": "md_simulation", "force_field": force_field, "duration_ns": duration_ns})
    return {
        "result_version": "aidd.sciminer/result",
        "artifacts": {"trajectory": trajectory, "report": report},
        "relations": [{"from": "report", "to": "trajectory", "type": "describes"}],
        "summary": {"package": SLUG, "mock": True, "frames": frames},
        "metrics": {"frames": frames},
    }


# --------------------------------------------------------------------------- #
# mode: mmpbsa
# --------------------------------------------------------------------------- #
def build_mmpbsa(task: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    params = _parameters(task)
    task_id = _task_id(task)
    seed = int(params.get("seed", 42))
    method = str(params.get("method", "mmgbsa"))
    frames = max(1, min(5000, int(params.get("frames", 100))))

    rows = []
    for frame in range(1, frames + 1):
        progress = frame / frames
        total = round(-42.0 + 3.0 * _stable_unit(seed, frame, "total") - 2.0 * progress, 3)
        vdw = round(-45.0 + 2.0 * _stable_unit(seed, frame, "vdw"), 3)
        electrostatic = round(-28.0 + 4.0 * _stable_unit(seed, frame, "elec"), 3)
        polar = round(38.0 + 3.0 * _stable_unit(seed, frame, "polar") + 2.0 * progress, 3)
        nonpolar = round(-3.5 + 0.5 * _stable_unit(seed, frame, "nonpolar"), 3)
        sasa = round(0.55 + 0.1 * _stable_unit(seed, frame, "sasa"), 3)
        rows.append(
            {
                "frame": frame,
                "delta_g_total": total,
                "delta_g_vdw": vdw,
                "delta_g_electrostatic": electrostatic,
                "delta_g_polar_solvation": polar,
                "delta_g_nonpolar_solvation": nonpolar,
                "delta_g_sasa": sasa,
            }
        )
    fields = [
        "frame", "delta_g_total", "delta_g_vdw", "delta_g_electrostatic",
        "delta_g_polar_solvation", "delta_g_nonpolar_solvation", "delta_g_sasa",
    ]
    table = _write_csv(out_dir, "energies", "energies.csv", fields, rows)
    meta = _write_text(
        out_dir, "energies", "metadata.json",
        json.dumps(_table_metadata(task_id, "frame", {"mock": True, "method": method}), ensure_ascii=False, indent=2),
    )
    energies = _artifact(
        "energies", "molecule_table@1",
        {"table_file": table, "metadata_json": meta},
        _table_metadata(task_id, "frame", {"mock": True, "method": method}),
        summary={"frames": len(rows), "method": method, "mock": True},
        metrics={"frames": len(rows)},
    )
    report = _report(out_dir, task_id, {"kind": "mmpbsa_free_energy", "method": method, "frames": len(rows)})
    return {
        "result_version": "aidd.sciminer/result",
        "artifacts": {"energies": energies, "report": report},
        "relations": [{"from": "report", "to": "energies", "type": "describes"}],
        "summary": {"package": SLUG, "mock": True, "frames": len(rows)},
        "metrics": {"frames": len(rows)},
    }


_BUILDERS = {
    "generation": build_generation,
    "peptide": build_peptide,
    "admet": build_admet,
    "vina": build_vina,
    "md": build_md,
    "mmpbsa": build_mmpbsa,
}


def run(task: dict[str, Any], out_dir: str | os.PathLike[str]) -> dict[str, Any]:
    """Execute the mock model and return the result.v2 envelope dict."""
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    return _BUILDERS[MODE](task, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=SLUG)
    parser.add_argument("--params-file")
    parser.add_argument("--output-dir")
    parser.add_argument("--result-file")
    args, _unknown = parser.parse_known_args(argv)

    task_file = os.environ.get("DRP_TASK_FILE")
    out_dir = args.output_dir or os.environ.get("DRP_OUT_DIR", ".")
    result_file = (
        args.result_file
        or os.environ.get("DRP_RESULT_FILE")
        or str(Path(out_dir) / "result.json")
    )
    if task_file:
        task = json.loads(Path(task_file).read_text(encoding="utf-8"))
    elif args.params_file:
        raw = json.loads(Path(args.params_file).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and ("inputs" in raw or "parameters" in raw or "params" in raw):
            task = raw
        else:
            task = {"params": raw if isinstance(raw, dict) else {}}
    else:
        print("provide DRP_TASK_FILE or --params-file", file=sys.stderr)
        return 2
    result = run(task, out_dir)
    Path(result_file).parent.mkdir(parents=True, exist_ok=True)
    Path(result_file).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{SLUG}: wrote {len(result['artifacts'])} artifacts to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
