#!/usr/bin/env python3
"""Convert a SMILES table (CSV) into a multi-record 3D SDF for affinity models.

Affinity models such as MSIGN need 3D ligand conformers.  Enterprise users often
have only SMILES, so this helper generates one ETKDG conformer per row and
writes a multi-record SDF that the model consumes in batch mode.

Rows that cannot be parsed or embedded are skipped and reported in a JSON
sidecar so the result post-processor can surface them as per-molecule errors
instead of failing the whole task.

Usage:
    python smiles_to_sdf.py --smiles-csv ligands.csv --output-sdf ligands.sdf \
        --errors-json artifacts/smiles_conversion_errors.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D


SMILES_COLUMNS = ("smiles", "canonical_smiles", "isomeric_smiles", "smile")
ID_COLUMNS = ("molecule_id", "ligand_id", "id", "name", "compound_id")


def _pick_column(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:
    by_lower = {name.strip().lower(): name for name in fieldnames if name}
    for candidate in candidates:
        if candidate in by_lower:
            return by_lower[candidate]
    return None


def _clean_id(value: str, fallback: str) -> str:
    text = (value or "").strip()
    if not text:
        return fallback
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text)[:80] or fallback


def _protein_centroid(protein_pdb: Path) -> tuple[float, float, float]:
    """Coordinate of the protein heavy atom closest to the geometric centroid.

    A raw centroid can sit in a hollow interior far from every atom, which makes
    MSIGN report "no protein pocket atoms within 5 Angstrom". Anchoring on the
    medoid atom guarantees the conformer lands inside the protein. This is only a
    coarse placement for SMILES-only input; a real binding pose still requires a
    docked SDF (ligand_sdf).
    """
    coords: list[tuple[float, float, float]] = []
    for line in protein_pdb.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        element = line[76:78].strip().upper()
        if element == "H":
            continue
        try:
            coords.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
        except ValueError:
            continue
    if not coords:
        raise SystemExit(f"no atoms found in protein PDB: {protein_pdb}")
    center = [sum(c[axis] for c in coords) / len(coords) for axis in range(3)]
    return min(
        coords,
        key=lambda c: sum((c[axis] - center[axis]) ** 2 for axis in range(3)),
    )


def convert(
    smiles_csv: Path,
    output_sdf: Path,
    errors_json: Path,
    *,
    smiles_column: str | None,
    id_column: str | None,
    max_molecules: int | None,
    random_seed: int,
    center_from_protein: Path | None = None,
) -> dict[str, Any]:
    with smiles_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        smiles_field = smiles_column or _pick_column(fieldnames, SMILES_COLUMNS)
        if not smiles_field or smiles_field not in fieldnames:
            raise SystemExit(
                "SMILES column not found; expected one of "
                + ", ".join(SMILES_COLUMNS)
                + f"; got {fieldnames}"
            )
        id_field = id_column or _pick_column(fieldnames, ID_COLUMNS)
        rows = list(reader)

    if max_molecules is not None:
        rows = rows[:max_molecules]

    output_sdf.parent.mkdir(parents=True, exist_ok=True)
    errors_json.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(output_sdf))
    errors: list[dict[str, str]] = []
    written = 0
    target_center = _protein_centroid(center_from_protein) if center_from_protein else None
    try:
        for index, row in enumerate(rows, start=1):
            smiles = (row.get(smiles_field) or "").strip()
            molecule_id = _clean_id(row.get(id_field, "") if id_field else "", f"ligand_{index:03d}")
            if not smiles:
                errors.append({"molecule_id": molecule_id, "smiles": smiles, "error": "empty SMILES"})
                continue
            molecule = Chem.MolFromSmiles(smiles)
            if molecule is None:
                errors.append({"molecule_id": molecule_id, "smiles": smiles, "error": "RDKit could not parse SMILES"})
                continue
            molecule = Chem.AddHs(molecule)
            params = AllChem.ETKDGv3()
            params.randomSeed = random_seed
            if AllChem.EmbedMolecule(molecule, params) != 0:
                errors.append({"molecule_id": molecule_id, "smiles": smiles, "error": "3D conformer generation failed"})
                continue
            try:
                AllChem.MMFFOptimizeMolecule(molecule, maxIters=200)
            except Exception:  # optimisation is best-effort
                pass
            if target_center is not None:
                conformer = molecule.GetConformer()
                count = molecule.GetNumAtoms()
                ligand_center = [
                    sum(conformer.GetAtomPosition(i)[axis] for i in range(count)) / count
                    for axis in range(3)
                ]
                shift = [target_center[axis] - ligand_center[axis] for axis in range(3)]
                for atom_index in range(count):
                    pos = conformer.GetAtomPosition(atom_index)
                    conformer.SetAtomPosition(
                        atom_index,
                        Point3D(pos.x + shift[0], pos.y + shift[1], pos.z + shift[2]),
                    )
            molecule.SetProp("_Name", molecule_id)
            molecule.SetProp("smiles", smiles)
            writer.write(molecule)
            written += 1
    finally:
        writer.close()

    payload = {
        "requested_count": len(rows),
        "written_count": written,
        "failed_count": len(errors),
        "errors": errors,
    }
    errors_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smiles-csv", required=True)
    parser.add_argument("--output-sdf", required=True)
    parser.add_argument("--errors-json", required=True)
    parser.add_argument("--smiles-column", default=None)
    parser.add_argument("--id-column", default=None)
    parser.add_argument("--max-molecules", type=int, default=None)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument(
        "--center-from-protein",
        default=None,
        help="平移每个配体使其质心落在该蛋白 PDB 的重原子质心（粗略口袋落点）",
    )
    args = parser.parse_args()
    payload = convert(
        Path(args.smiles_csv),
        Path(args.output_sdf),
        Path(args.errors_json),
        smiles_column=args.smiles_column,
        id_column=args.id_column,
        max_molecules=args.max_molecules,
        random_seed=args.random_seed,
        center_from_protein=Path(args.center_from_protein) if args.center_from_protein else None,
    )
    print(json.dumps(payload, ensure_ascii=False))
    if payload["written_count"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
