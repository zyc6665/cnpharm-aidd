#!/usr/bin/env python3
"""AutoDock Vina docking entry for the SCIMINER Kubernetes model runtime.

Inputs (standard artifacts, resolved from params.json ``input_files``):
  * protein_structure@1 -> protein_pdb (PDB/CIF)
  * ligand_structure@1  -> ligand_sdf (SDF, one or more molecules) OR
    molecule_table@1    -> ligand_smiles (CSV with a SMILES column)
  * binding_pocket@1    -> binding_pocket (optional; PDB/MOL2/SDF defining the box centre)

Outputs (result.v2):
  * molecule_table@1  : docking_results (per-molecule stage flags / affinity / RMSD)
  * ligand_structure@1: docked_poses (best pose per kept ligand, multi-record SDF)
  * run_report@1      : run metadata

The funnel is real:
  1. input ligands
  2. pharmacophore features >= pharmacophore_min_features (RDKit feature factory)
  3. docking completed
  4. docking score <= docking_score_cutoff
  5. top_n kept (best scores first)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

FEATURE_FAMILIES = ("Donor", "Acceptor", "Aromatic", "Hydrophobe")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_ref(output_dir: Path, relative: str) -> dict[str, str]:
    path = output_dir / relative
    if not path.is_file():
        raise SystemExit(f"declared output file is missing: {relative}")
    return {"path": relative, "sha256": sha256_file(path)}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_input(input_dir: Path, value: str) -> Path:
    candidates = [
        Path(value),
        input_dir / value,
        input_dir / Path(value).name,
        input_dir.parent / value,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(f"input file not found: {value}")


def pick_input(
    files: dict[str, str],
    input_dir: Path,
    keywords: tuple[str, ...],
    suffixes: tuple[str, ...],
) -> Optional[Path]:
    for key, value in files.items():
        low = key.lower()
        if any(word in low for word in keywords):
            candidate = resolve_input(input_dir, value)
            if candidate.suffix.lower() in suffixes:
                return candidate
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in suffixes:
            return path
    return None


def prepare_receptor(pdb: Path, work: Path) -> Path:
    subprocess.run(
        [
            "mk_prepare_receptor.py",
            "--read_pdb",
            str(pdb),
            "-o",
            str(work / "receptor"),
            "-p",
            "--allow_bad_res",
            "--default_altloc",
            "A",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    pdbqt = work / "receptor.pdbqt"
    if not pdbqt.is_file():
        raise SystemExit("receptor.pdbqt not produced by mk_prepare_receptor.py")
    return pdbqt


def count_pharmacophore_features(mol) -> int:
    """Count RDKit base pharmacophore features used by the funnel."""
    from rdkit import RDConfig
    from rdkit.Chem import ChemicalFeatures

    factory = ChemicalFeatures.BuildFeatureFactory(
        os.path.join(RDConfig.RDDataDir, "BaseFeatures.fdef")
    )
    features = factory.GetFeaturesForMol(mol)
    return sum(1 for feature in features if feature.GetFamily() in FEATURE_FAMILIES)


def descriptor_values(mol) -> Dict[str, Any]:
    from rdkit.Chem import Descriptors, QED, rdMolDescriptors

    try:
        qed = float(QED.qed(mol))
    except Exception:
        qed = None
    return {
        "mol_weight": round(float(Descriptors.MolWt(mol)), 3),
        "logp": round(float(Descriptors.MolLogP(mol)), 3),
        "tpsa": round(float(rdMolDescriptors.CalcTPSA(mol)), 3),
        "qed": round(qed, 3) if qed is not None else "",
    }


def smiles_of(mol) -> str:
    from rdkit import Chem

    try:
        return Chem.MolToSmiles(Chem.RemoveHs(mol), canonical=True)
    except Exception:
        return ""


def read_smiles_rows(path: Path) -> List[Tuple[str, str]]:
    """Return (molecule_id, smiles) from a CSV with a SMILES-like column."""
    rows: List[Tuple[str, str]] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return rows
        smiles_key = next(
            (field for field in reader.fieldnames if field.strip().lower() == "smiles"),
            None,
        )
        if smiles_key is None:
            smiles_key = next(
                (field for field in reader.fieldnames if "smiles" in field.strip().lower()),
                None,
            )
        if smiles_key is None:
            raise SystemExit("ligand CSV must contain a SMILES column")
        id_key = next(
            (
                field
                for field in reader.fieldnames
                if field.strip().lower() in {"molecule_id", "ligand_id", "name", "id"}
            ),
            None,
        )
        for index, row in enumerate(reader, start=1):
            smiles = (row.get(smiles_key) or "").strip()
            if not smiles:
                continue
            molecule_id = (row.get(id_key) or "").strip() if id_key else ""
            rows.append((molecule_id or f"ligand_{index:03d}", smiles))
    return rows


def ensure_3d(mol, seed: int):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(mol, addCoords=True)
    if mol.GetNumConformers() == 0:
        params = AllChem.ETKDGv3()
        params.randomSeed = int(seed)
        if AllChem.EmbedMolecule(mol, params) != 0:
            return None
    return mol


def load_ligands(
    files: dict[str, str], input_dir: Path, seed: int, work: Path
) -> List[Tuple[str, Any]]:
    from rdkit import Chem

    sdf = pick_input(files, input_dir, ("ligand_sdf", "ligand", "sdf"), (".sdf",))
    if sdf is not None:
        supplier = Chem.SDMolSupplier(str(sdf), removeHs=False)
        molecules = []
        for index, mol in enumerate(supplier, start=1):
            if mol is None:
                continue
            name = mol.GetProp("_Name") if mol.HasProp("_Name") else ""
            molecules.append((name or f"ligand_{index:03d}", mol))
        if molecules:
            return molecules

    table = pick_input(files, input_dir, ("ligand_smiles", "smiles", "csv"), (".csv",))
    if table is not None:
        molecules = []
        for molecule_id, smiles in read_smiles_rows(table):
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue
            mol.SetProp("_Name", molecule_id)
            molecules.append((molecule_id, mol))
        if molecules:
            return molecules

    raise SystemExit("no readable ligand input found (expected ligand_sdf SDF or ligand_smiles CSV)")


def prepare_ligand(mol, work: Path, index: int, seed: int):
    from rdkit import Chem

    prepared = ensure_3d(mol, seed)
    if prepared is None:
        raise RuntimeError("RDKit failed to generate 3D coordinates")
    sdf = work / f"ligand_{index}.sdf"
    writer = Chem.SDWriter(str(sdf))
    writer.write(prepared)
    writer.close()
    pdbqt = work / f"ligand_{index}.pdbqt"
    subprocess.run(
        ["mk_prepare_ligand.py", "-i", str(sdf), "-o", str(pdbqt)],
        check=True,
        capture_output=True,
        text=True,
    )
    return prepared, pdbqt


def centroid_of_mol(mol) -> List[float]:
    conf = mol.GetConformer()
    xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
    ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
    zs = [conf.GetAtomPosition(i).z for i in range(mol.GetNumAtoms())]
    return [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)]


def box_for(mol, box_size: float, center: Optional[List[float]] = None):
    return center or centroid_of_mol(mol), [box_size, box_size, box_size]


def protein_center(pdb: Path) -> Optional[List[float]]:
    points: List[Tuple[float, float, float]] = []
    try:
        for line in pdb.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith(("ATOM  ", "HETATM")):
                points.append(
                    (float(line[30:38]), float(line[38:46]), float(line[46:54]))
                )
    except (ValueError, OSError):
        return None
    if not points:
        return None
    return [
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
        sum(point[2] for point in points) / len(points),
    ]


def pocket_center(path: Optional[Path]) -> Optional[List[float]]:
    if path is None:
        return None
    suffix = path.suffix.lower()
    if suffix == ".pdb":
        return protein_center(path)
    if suffix == ".sdf":
        from rdkit import Chem

        supplier = Chem.SDMolSupplier(str(path), removeHs=False)
        for mol in supplier:
            if mol is not None and mol.GetNumConformers() > 0:
                return centroid_of_mol(mol)
        return None
    if suffix == ".mol2":
        points: List[Tuple[float, float, float]] = []
        in_atoms = False
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("@<TRIPOS>ATOM"):
                in_atoms = True
                continue
            if line.startswith("@<TRIPOS>") and in_atoms:
                break
            if not in_atoms or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 5:
                try:
                    points.append((float(parts[2]), float(parts[3]), float(parts[4])))
                except ValueError:
                    continue
        if points:
            return [
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
                sum(point[2] for point in points) / len(points),
            ]
    return None


def read_pose_scores(pose_pdbqt: Path) -> list[tuple[float, float, float]]:
    scores: list[tuple[float, float, float]] = []
    for line in pose_pdbqt.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith("REMARK VINA RESULT:"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            scores.append((float(parts[3]), float(parts[4]), float(parts[5])))
        except ValueError:
            continue
    return scores


def poses_to_sdf(pose_pdbqt: Path, out_sdf: Path, name: str, affinity: float):
    from meeko import PDBQTMolecule, RDKitMolCreate
    from rdkit import Chem

    pdbqt_mol = PDBQTMolecule.from_file(str(pose_pdbqt), is_dlg=False, skip_typing=True)
    mols = RDKitMolCreate.from_pdbqt_mol(pdbqt_mol)
    mols = [m for m in mols if m is not None]
    if not mols:
        return None
    mol = mols[0]
    mol.SetProp("_Name", name)
    mol.SetProp("affinity_kcal_mol", f"{affinity:.3f}")
    writer = Chem.SDWriter(str(out_sdf))
    writer.write(mol)
    writer.close()
    return mol


def flag(value: bool) -> str:
    return "true" if value else "false"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default="unknown")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--params-json", required=True)
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    from vina import Vina

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    work = Path(args.work_dir or (output_dir / "work")).resolve()
    work.mkdir(parents=True, exist_ok=True)
    (output_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    params = json.loads(Path(args.params_json).read_text(encoding="utf-8"))
    files = params.get("input_files") or {}
    manifest_path = input_dir / "manifest.json"
    if manifest_path.is_file():
        staged = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = {
            entry["name"]: str((input_dir.parent / entry["path"]).resolve())
            for entry in staged
            if entry.get("name")
            and entry.get("path")
            and entry.get("role") != "metadata_json"
            and not str(entry.get("path", "")).endswith(".metadata_json.json")
        }

    run_params = params.get("params") or params.get("parameters") or {}

    def param(name: str, default):
        value = run_params.get(name)
        return default if value is None or value == "" else value

    box_size = float(param("box_size", 22.0))
    exhaustiveness = int(param("exhaustiveness", 8))
    n_poses = int(param("n_poses", 9))
    seed = int(param("seed", 42))
    min_features = int(param("pharmacophore_min_features", 3))
    score_cutoff = float(param("docking_score_cutoff", -8.0))
    top_n = max(0, int(param("top_n", 100)))

    protein = pick_input(files, input_dir, ("protein", "receptor", "pdb"), (".pdb", ".cif"))
    if protein is None:
        raise SystemExit("no protein input found")
    pocket_file = pick_input(files, input_dir, ("pocket",), (".pdb", ".mol2", ".sdf"))
    fixed_center = pocket_center(pocket_file)

    receptor_pdbqt = prepare_receptor(protein, work)
    ligands = load_ligands(files, input_dir, seed, work)
    protein_fixed_center = fixed_center or (protein_center(protein) if len(ligands) > 1 else None)

    rows: List[Dict[str, Any]] = []
    pose_files: Dict[str, Path] = {}

    for index, (molecule_id, molecule) in enumerate(ligands, start=1):
        descriptors = descriptor_values(molecule)
        features = count_pharmacophore_features(molecule)
        row: Dict[str, Any] = {
            "molecule_id": molecule_id,
            "smiles": smiles_of(molecule),
            "mol_weight": descriptors["mol_weight"],
            "logp": descriptors["logp"],
            "tpsa": descriptors["tpsa"],
            "qed": descriptors["qed"],
            "pharmacophore_features": features,
            "stage_pharmacophore": flag(features >= min_features),
            "stage_docking": "false",
            "docking_score": "",
            "rmsd_lb": "",
            "rmsd_ub": "",
            "num_poses": "",
            "stage_cutoff": "false",
            "rank": "",
            "passes": "false",
            "error": "",
        }
        if features < min_features:
            row["error"] = "pharmacophore_below_threshold"
            rows.append(row)
            continue

        try:
            prepared_mol, ligand_pdbqt = prepare_ligand(molecule, work, index, seed)
            center, size = box_for(prepared_mol, box_size, protein_fixed_center)
            vina = Vina(
                sf_name="vina",
                cpu=max(1, os.cpu_count() or 1),
                seed=seed,
                verbosity=0,
            )
            vina.set_receptor(str(receptor_pdbqt))
            vina.set_ligand_from_file(str(ligand_pdbqt))
            vina.compute_vina_maps(center=center, box_size=size)
            vina.dock(exhaustiveness=exhaustiveness, n_poses=n_poses)
            pose_file = work / f"poses_{index}.pdbqt"
            vina.write_poses(str(pose_file), n_poses=n_poses, overwrite=True)
            pose_scores = read_pose_scores(pose_file)
            if pose_scores:
                best, rmsd_lb, rmsd_ub = pose_scores[0]
            else:
                energies = vina.energies(n_poses=n_poses)
                best, rmsd_lb, rmsd_ub = float(energies[0][0]), None, None
            row.update(
                {
                    "stage_docking": "true",
                    "docking_score": f"{best:.3f}",
                    "rmsd_lb": f"{rmsd_lb:.3f}" if rmsd_lb is not None else "",
                    "rmsd_ub": f"{rmsd_ub:.3f}" if rmsd_ub is not None else "",
                    "num_poses": n_poses,
                }
            )
            pose_single = work / f"pose_{index}.sdf"
            poses_to_sdf(pose_file, pose_single, molecule_id, best)
            if pose_single.is_file():
                pose_files[molecule_id] = pose_single
        except Exception as exc:  # keep the batch alive; expose the failure per ligand
            row["error"] = str(exc)[:500]
        rows.append(row)

    docked_rows = [row for row in rows if row["stage_docking"] == "true"]
    docked_rows.sort(key=lambda row: float(row["docking_score"]))
    for rank, row in enumerate(docked_rows, start=1):
        row["rank"] = rank
        row["stage_cutoff"] = flag(float(row["docking_score"]) <= score_cutoff)

    cutoff_rows = [row for row in docked_rows if row["stage_cutoff"] == "true"]
    for index, row in enumerate(cutoff_rows, start=1):
        if index <= top_n:
            row["passes"] = "true"

    kept_rows = [row for row in cutoff_rows if row["passes"] == "true"]

    poses_path = output_dir / "artifacts" / "docked_poses.sdf"
    pose_writer = None
    try:
        from rdkit import Chem

        pose_writer = Chem.SDWriter(str(poses_path))
        for row in kept_rows:
            single = pose_files.get(row["molecule_id"])
            if single is None:
                continue
            supplier = Chem.SDMolSupplier(str(single), removeHs=False)
            for mol in supplier:
                if mol is not None:
                    pose_writer.write(mol)
    finally:
        if pose_writer is not None:
            pose_writer.close()
    if not poses_path.is_file():
        poses_path.write_text("", encoding="utf-8")

    table_path = output_dir / "artifacts" / "docking_results.csv"
    fieldnames = [
        "molecule_id",
        "smiles",
        "mol_weight",
        "logp",
        "tpsa",
        "qed",
        "pharmacophore_features",
        "stage_pharmacophore",
        "stage_docking",
        "docking_score",
        "rmsd_lb",
        "rmsd_ub",
        "num_poses",
        "stage_cutoff",
        "rank",
        "passes",
        "error",
    ]
    with table_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    input_count = len(rows)
    pharmacophore_pass_count = sum(1 for row in rows if row["stage_pharmacophore"] == "true")
    docked_count = len(docked_rows)
    score_pass_count = len(cutoff_rows)
    kept_count = len(kept_rows)
    best_affinities = [float(row["docking_score"]) for row in docked_rows]

    metadata_path = output_dir / "artifacts" / "metadata.json"
    write_json(
        metadata_path,
        {
            "molecule_id_field": "molecule_id",
            "source_task_id": args.task_id,
            "generated_by": "autodock-vina",
            "protein_file": protein.name,
            "pocket_file": pocket_file.name if pocket_file else None,
            "box_size": box_size,
            "exhaustiveness": exhaustiveness,
            "n_poses": n_poses,
            "seed": seed,
            "pharmacophore_min_features": min_features,
            "docking_score_cutoff": score_cutoff,
            "top_n": top_n,
        },
    )
    report_path = output_dir / "artifacts" / "report.json"
    write_json(
        report_path,
        {
            "source_task_id": args.task_id,
            "tool": "autodock-vina",
            "status": "succeeded",
            "num_ligands": input_count,
            "pharmacophore_pass_count": pharmacophore_pass_count,
            "docked_count": docked_count,
            "score_pass_count": score_pass_count,
            "kept_count": kept_count,
            "best_affinity_kcal_mol": min(best_affinities) if best_affinities else None,
            "box_size": box_size,
            "exhaustiveness": exhaustiveness,
            "n_poses": n_poses,
            "seed": seed,
            "pharmacophore_min_features": min_features,
            "docking_score_cutoff": score_cutoff,
            "top_n": top_n,
        },
    )

    metrics = {
        "num_ligands": input_count,
        "input_count": input_count,
        "pharmacophore_pass_count": pharmacophore_pass_count,
        "docked_count": docked_count,
        "score_pass_count": score_pass_count,
        "kept_count": kept_count,
        "best_affinity_kcal_mol": min(best_affinities) if best_affinities else None,
    }
    result = {
        "result_version": "aidd.sciminer/result",
        "artifacts": {
            "docking_results": {
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(output_dir, "artifacts/docking_results.csv"),
                    "metadata_json": file_ref(output_dir, "artifacts/metadata.json"),
                },
                "metadata": {"molecule_id_field": "molecule_id", "source_task_id": args.task_id},
            },
            "docked_poses": {
                "type": "ligand_structure@1",
                "files": {"structure_file": file_ref(output_dir, "artifacts/docked_poses.sdf")},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, "artifacts/report.json")},
                "metadata": {"source_task_id": args.task_id},
            },
        },
        "metrics": metrics,
    }
    write_json(output_dir / "result.json", result)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
