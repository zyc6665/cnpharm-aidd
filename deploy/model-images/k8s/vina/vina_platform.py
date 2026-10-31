#!/usr/bin/env python3
"""AutoDock Vina docking entry for the SCIMINER Kubernetes model runtime.

Inputs (standard artifacts, resolved from params.json ``input_files``):
  * protein_structure@1 -> structure_file (PDB)
  * ligand_structure@1  -> structure_file (SDF, one or more molecules)

Outputs (result.v2):
  * molecule_table@1  : docking_results (per-molecule affinity / RMSD)
  * ligand_structure@1: docked_poses (best pose per ligand, multi-record SDF)
  * run_report@1      : run metadata

Box: centred on each ligand's 3D centroid; size from ``params.box_size`` (default 22 Å).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


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
    candidates = [Path(value), input_dir / value, input_dir / Path(value).name, input_dir.parent / value]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(f"input file not found: {value}")


def pick_input(files: dict[str, str], input_dir: Path, keywords: tuple[str, ...], suffixes: tuple[str, ...]) -> Path:
    for key, value in files.items():
        low = key.lower()
        if any(word in low for word in keywords):
            candidate = resolve_input(input_dir, value)
            if candidate.suffix.lower() in suffixes:
                return candidate
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in suffixes:
            return path
    raise SystemExit(f"cannot find input matching {keywords} / {suffixes}")


def prepare_receptor(pdb: Path, work: Path) -> Path:
    subprocess.run(
        ["mk_prepare_receptor.py", "--read_pdb", str(pdb), "-o", str(work / "receptor"), "-p"],
        check=True,
        capture_output=True,
        text=True,
    )
    pdbqt = work / "receptor.pdbqt"
    if not pdbqt.is_file():
        raise SystemExit("receptor.pdbqt not produced by mk_prepare_receptor.py")
    return pdbqt


def prepare_ligand(mol, work: Path, index: int):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(mol, addCoords=True)
    if mol.GetNumConformers() == 0:
        AllChem.EmbedMolecule(mol, randomSeed=42)
    sdf = work / f"ligand_{index}.sdf"
    writer = Chem.SDWriter(str(sdf))
    writer.write(mol)
    writer.close()
    pdbqt = work / f"ligand_{index}.pdbqt"
    subprocess.run(
        ["mk_prepare_ligand.py", "-i", str(sdf), "-o", str(pdbqt)],
        check=True,
        capture_output=True,
        text=True,
    )
    return mol, pdbqt


def box_for(mol, box_size: float) -> tuple[list[float], list[float]]:
    conf = mol.GetConformer()
    xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
    ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
    zs = [conf.GetAtomPosition(i).z for i in range(mol.GetNumAtoms())]
    center = [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)]
    return center, [box_size, box_size, box_size]


def read_pose_scores(pose_pdbqt: Path) -> list[tuple[float, float, float]]:
    """Parse ``REMARK VINA RESULT`` rows: affinity, rmsd_lb, rmsd_ub.

    ``Vina.energies()`` returns energy terms (affinity + inter/intra components),
    not RMSD columns, so RMSD must come from the written pose PDBQT remark.
    """
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default="unknown")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--params-json", required=True)
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    from rdkit import Chem
    from vina import Vina

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    work = Path(args.work_dir or (output_dir / "work")).resolve()
    work.mkdir(parents=True, exist_ok=True)
    (output_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    params = json.loads(Path(args.params_json).read_text(encoding="utf-8"))
    files = params.get("input_files") or {}
    # 平台适配层会把对象存储输入落到 input/<name>/<filename>，并写 manifest.json；
    # 优先用 manifest 的本地路径，避免依赖 params 里的对象存储 URI。
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
    run_params = params.get("params") or {}
    box_size = float(run_params.get("box_size") or 22.0)
    exhaustiveness = int(run_params.get("exhaustiveness") or 8)
    n_poses = int(run_params.get("n_poses") or 9)

    protein = pick_input(files, input_dir, ("protein", "receptor", "pdb"), (".pdb", ".cif"))
    ligand = pick_input(files, input_dir, ("ligand", "sdf"), (".sdf",))

    receptor_pdbqt = prepare_receptor(protein, work)
    supplier = Chem.SDMolSupplier(str(ligand), removeHs=False)
    molecules = [m for m in supplier if m is not None]
    if not molecules:
        raise SystemExit("ligand SDF contains no readable molecule")

    rows: list[dict[str, Any]] = []
    poses_path = output_dir / "artifacts" / "docked_poses.sdf"
    pose_writer = Chem.SDWriter(str(poses_path))
    best_affinities: list[float] = []

    for index, molecule in enumerate(molecules, start=1):
        molecule_id = molecule.GetProp("_Name") if molecule.HasProp("_Name") and molecule.GetProp("_Name") else f"ligand_{index:03d}"
        prepared_mol, ligand_pdbqt = prepare_ligand(molecule, work, index)
        center, size = box_for(prepared_mol, box_size)

        vina = Vina(sf_name="vina", cpu=max(1, os.cpu_count() or 1), seed=42, verbosity=0)
        vina.set_receptor(str(receptor_pdbqt))
        vina.set_ligand_from_file(str(ligand_pdbqt))
        vina.compute_vina_maps(center=center, box_size=size)
        vina.dock(exhaustiveness=exhaustiveness, n_poses=n_poses)
        pose_file = work / f"poses_{index}.pdbqt"
        vina.write_poses(str(pose_file), n_poses=n_poses, overwrite=True)
        pose_scores = read_pose_scores(pose_file)
        print(
            f"[vina] {molecule_id} score={vina.score()[:3].tolist()} "
            f"pose_scores={pose_scores[:2]}",
            flush=True,
        )
        if pose_scores:
            best, rmsd_lb, rmsd_ub = pose_scores[0]
        else:
            # 兜底：PDBQT 无 REMARK 时仅取能量项首列，RMSD 留空。
            energies = vina.energies(n_poses=n_poses)
            best, rmsd_lb, rmsd_ub = float(energies[0][0]), None, None
        best_affinities.append(best)

        mol = poses_to_sdf(pose_file, work / f"pose_{index}.sdf", molecule_id, best)
        if mol is not None:
            pose_writer.write(mol)
        rows.append(
            {
                "molecule_id": molecule_id,
                "affinity_kcal_mol": f"{best:.3f}",
                "rmsd_lb": f"{rmsd_lb:.3f}" if rmsd_lb is not None else "",
                "rmsd_ub": f"{rmsd_ub:.3f}" if rmsd_ub is not None else "",
                "num_poses": n_poses,
            }
        )
    pose_writer.close()

    table_path = output_dir / "artifacts" / "docking_results.csv"
    with table_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    metadata_path = output_dir / "artifacts" / "metadata.json"
    write_json(
        metadata_path,
        {
            "molecule_id_field": "molecule_id",
            "source_task_id": args.task_id,
            "generated_by": "autodock-vina",
            "protein_file": protein.name,
            "ligand_file": ligand.name,
            "box_size": box_size,
            "exhaustiveness": exhaustiveness,
        },
    )
    report_path = output_dir / "artifacts" / "report.json"
    write_json(
        report_path,
        {
            "source_task_id": args.task_id,
            "tool": "autodock-vina",
            "status": "succeeded",
            "num_ligands": len(rows),
            "best_affinity_kcal_mol": min(best_affinities) if best_affinities else None,
            "box_size": box_size,
            "exhaustiveness": exhaustiveness,
        },
    )

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
        "metrics": {
            "num_ligands": len(rows),
            "best_affinity_kcal_mol": min(best_affinities) if best_affinities else None,
        },
    }
    write_json(output_dir / "result.json", result)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
