#!/usr/bin/env python3
"""Platform adapter for LPDI-EPFL/lddm inside the Kubernetes runtime container.

LDDM's ``scripts/sample.py`` requires ``--protein <pdb>`` and ``--ref_ligand <sdf>``
(where ``--ref_ligand`` is used only to select interacting pocket residues and is
never part of generated outputs). When platform callers pass a pocket PDB and/or
pocket center ``(center_x, center_y, center_z)`` instead of an explicit SDF ligand,
this adapter synthesizes a multi-atom 3D carbon probe SDF at those coordinates so
LDDM plugs seamlessly into the platform pocket-to-molecule pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import time
from pathlib import Path
from typing import Any


MODEL_ROOT = Path(__file__).resolve().parent
DEFAULT_CHECKPOINT = MODEL_ROOT / "checkpoints" / "lddm.ckpt"
ATOM_RECORDS = {"ATOM", "HETATM"}
SOLVENT_RESNAMES = {"HOH", "WAT", "DOD", "SO4", "PO4", "CL", "NA", "MG", "ZN", "K"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LDDM platform adapter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--task-id", required=True)
    prepare.add_argument("--input-dir", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--params-json", required=True)
    prepare.add_argument("--work-dir", required=True)
    prepare.add_argument("--device", default="auto")
    prepare.add_argument("--env-out", required=True)
    prepare.add_argument("--metadata-out", required=True)
    prepare.add_argument("--sdf-out", required=True)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--task-id", required=True)
    finalize.add_argument("--output-dir", required=True)
    finalize.add_argument("--sdf-path", required=True)
    finalize.add_argument("--metadata-json", required=True)
    finalize.add_argument("--start-ts", required=True)

    fail = subparsers.add_parser("fail")
    fail.add_argument("--output-dir", required=True)
    fail.add_argument("--message", required=True)
    fail.add_argument("--code", default="MODEL_EXECUTION_FAILED")
    fail.add_argument("--details", default="")
    fail.add_argument("--start-ts", default="")

    return parser.parse_args()


def load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("params.json must contain a JSON object")
    return payload


def get_params(payload: dict[str, Any]) -> dict[str, Any]:
    params = dict(payload.get("params") if isinstance(payload.get("params"), dict) else {})
    for key, value in payload.items():
        if key in {
            "task_id",
            "task_name",
            "params",
            "parameters",
            "inputs",
            "input_files",
            "uploaded_files",
            "files",
        }:
            continue
        params.setdefault(key, value)
    return params


def get_input_files(payload: dict[str, Any]) -> dict[str, Any]:
    input_files = dict(
        payload.get("input_files") if isinstance(payload.get("input_files"), dict) else {}
    )
    for key in (
        "protein_pdb",
        "receptor_pdb",
        "pdb_path",
        "structure_file",
        "pocket_pdb",
        "ref_ligand",
        "reference_ligand",
        "ligand_sdf",
        "fragment_sdf",
        "ligand",
    ):
        if key not in input_files and key in payload:
            input_files[key] = payload[key]
    return input_files


def raw_path(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("path", "file", "filename", "local_path", "name"):
            if value.get(key):
                return str(value[key])
        return ""
    if isinstance(value, list):
        return raw_path(value[0]) if value else ""
    if value is None:
        return ""
    return str(value)


def resolve_input_file(raw: str, input_dir: Path) -> Path | None:
    text = raw.strip()
    if not text:
        return None
    candidate = Path(text)
    search_list = (
        [candidate, input_dir / candidate.name]
        if candidate.is_absolute()
        else [input_dir / candidate, input_dir / candidate.name, MODEL_ROOT / candidate]
    )
    for item in search_list:
        if item.is_file():
            return item.resolve()
    return None


def resolve_named_file(
    input_files: dict[str, Any],
    keys: tuple[str, ...],
    input_dir: Path,
) -> Path | None:
    for key in keys:
        found = resolve_input_file(raw_path(input_files.get(key)), input_dir)
        if found is not None:
            return found
    return None


def int_param(
    params: dict[str, Any],
    key: str,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = params.get(key)
    result = default if value in (None, "") else int(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{key} must be >= {minimum}, got {result}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{key} must be <= {maximum}, got {result}")
    return result


def float_param(
    params: dict[str, Any],
    key: str,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = params.get(key)
    result = default if value in (None, "") else float(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{key} must be >= {minimum}, got {result}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{key} must be <= {maximum}, got {result}")
    return result


def parse_center(raw: Any) -> list[float]:
    if isinstance(raw, (list, tuple)):
        pieces = [float(item) for item in raw]
    elif isinstance(raw, str):
        pieces = [float(item) for item in re.split(r"[,\s]+", raw.strip()) if item]
    else:
        raise ValueError("center must be a comma-separated string or 3-element list")
    if len(pieces) != 3:
        raise ValueError("center must contain exactly 3 coordinates")
    return pieces


def parse_pdb_coords(
    pdb_path: Path,
    *,
    hetatm_only: bool = False,
) -> list[tuple[float, float, float]]:
    coords: list[tuple[float, float, float]] = []
    for line in pdb_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        record = line[:6].strip()
        if hetatm_only and record != "HETATM":
            continue
        if not hetatm_only and record not in ATOM_RECORDS:
            continue
        resname = line[17:20].strip().upper()
        if hetatm_only and resname in SOLVENT_RESNAMES:
            continue
        element = line[76:78].strip().upper()
        atom_name = line[12:16].strip().upper()
        if element == "H" or atom_name.startswith("H"):
            continue
        try:
            coords.append(
                (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            )
        except ValueError:
            continue
    return coords


def probe_coords_around_center(
    center: tuple[float, float, float],
    radius: float = 3.0,
) -> list[tuple[float, float, float]]:
    cx, cy, cz = center
    return [
        (cx, cy, cz),
        (cx + radius, cy, cz),
        (cx - radius, cy, cz),
        (cx, cy + radius, cz),
        (cx, cy - radius, cz),
        (cx, cy, cz + radius),
        (cx, cy, cz - radius),
    ]


def write_probe_sdf(coords: list[tuple[float, float, float]], dest: Path) -> Path:
    from rdkit import Chem

    if len(coords) == 1:
        coords = probe_coords_around_center(coords[0], radius=2.5)
    elif len(coords) > 48:
        step = max(1, len(coords) // 48)
        coords = coords[::step][:48]

    mol = Chem.RWMol()
    conf = Chem.Conformer(len(coords))
    for idx, (x, y, z) in enumerate(coords):
        atom = Chem.Atom(6)
        atom_idx = mol.AddAtom(atom)
        conf.SetAtomPosition(atom_idx, (float(x), float(y), float(z)))
    rdmol = mol.GetMol()
    rdmol.AddConformer(conf, assignId=True)
    Chem.SanitizeMol(rdmol)

    dest.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(dest))
    writer.write(rdmol)
    writer.close()
    return dest


def resolve_ref_ligand(
    *,
    input_files: dict[str, Any],
    input_dir: Path,
    params: dict[str, Any],
    protein_pdb: Path,
    pocket_pdb: Path | None,
    work_dir: Path,
) -> tuple[Path, str]:
    explicit = resolve_named_file(
        input_files, ("ref_ligand", "reference_ligand", "ligand_sdf"), input_dir
    )
    if explicit is not None:
        return explicit, "input_files.ref_ligand"

    # Prefer HETATM pocket points (e.g. LVPocket atom_pocket / pocket0) if available.
    if pocket_pdb is not None:
        het_coords = parse_pdb_coords(pocket_pdb, hetatm_only=True)
        if len(het_coords) >= 2:
            probe = write_probe_sdf(het_coords, work_dir / "synthetic_ref_ligand.sdf")
            return probe, "pocket_pdb.hetatm_probe"

    if params.get("center") not in (None, ""):
        cx, cy, cz = parse_center(params["center"])
        probe = write_probe_sdf(
            probe_coords_around_center((cx, cy, cz)),
            work_dir / "synthetic_ref_ligand.sdf",
        )
        return probe, "params.center"

    if all(params.get(k) not in (None, "") for k in ("center_x", "center_y", "center_z")):
        cx = float(params["center_x"])
        cy = float(params["center_y"])
        cz = float(params["center_z"])
        probe = write_probe_sdf(
            probe_coords_around_center((cx, cy, cz)),
            work_dir / "synthetic_ref_ligand.sdf",
        )
        return probe, "params.center_xyz"

    if pocket_pdb is not None:
        all_coords = parse_pdb_coords(pocket_pdb, hetatm_only=False)
        if all_coords:
            n = float(len(all_coords))
            centroid = (
                sum(c[0] for c in all_coords) / n,
                sum(c[1] for c in all_coords) / n,
                sum(c[2] for c in all_coords) / n,
            )
            probe = write_probe_sdf(
                probe_coords_around_center(centroid),
                work_dir / "synthetic_ref_ligand.sdf",
            )
            return probe, "pocket_pdb.centroid_probe"

    # Last fallback: protein HETATM ligand or protein heavy-atom centroid
    prot_het = parse_pdb_coords(protein_pdb, hetatm_only=True)
    if len(prot_het) >= 2:
        probe = write_probe_sdf(prot_het, work_dir / "synthetic_ref_ligand.sdf")
        return probe, "protein_pdb.hetatm_probe"

    prot_all = parse_pdb_coords(protein_pdb, hetatm_only=False)
    if not prot_all:
        raise ValueError(f"No heavy atoms found in protein PDB: {protein_pdb}")
    n = float(len(prot_all))
    centroid = (
        sum(c[0] for c in prot_all) / n,
        sum(c[1] for c in prot_all) / n,
        sum(c[2] for c in prot_all) / n,
    )
    probe = write_probe_sdf(
        probe_coords_around_center(centroid),
        work_dir / "synthetic_ref_ligand.sdf",
    )
    return probe, "protein_pdb.centroid_probe"


def resolve_device(requested: str) -> str:
    value = str(requested or "auto").strip().lower()
    if value == "cpu":
        return "cpu"
    if value in {"", "auto"}:
        try:
            import torch

            return "cuda:0" if torch.cuda.is_available() else "cpu"
        except Exception:  # noqa: BLE001
            return "cpu"
    if value in {"gpu", "cuda", "cuda:0"}:
        return "cuda:0"
    if value.startswith("cuda:") and value.split(":", 1)[1].isdigit():
        return value
    raise ValueError(f"unsupported device: {requested!r}")


def validate_molecule_size(raw: Any) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text or text.lower() in {"auto", "histogram", "default"}:
        return ""
    if text.isdigit():
        count = int(text)
        if not (1 <= count <= 200):
            raise ValueError("molecule_size integer must be in 1..200")
        return str(count)
    match = re.fullmatch(r"uniform_(\d+)_(\d+)", text)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        if not (1 <= low <= high <= 200):
            raise ValueError("molecule_size uniform_<low>_<high> must satisfy 1 <= low <= high <= 200")
        return text
    raise ValueError("molecule_size must be empty/auto, an integer (1..200), or uniform_<low>_<high>")


def resolve_fragment_file(raw: Path | None, work_dir: Path) -> Path | None:
    if raw is None:
        return None
    if raw.suffix.lower() == ".sdf":
        return raw
    if raw.suffix.lower() in {".pdb", ".ent", ".mol", ".mol2"}:
        from rdkit import Chem

        mol = (
            Chem.MolFromPDBFile(str(raw), sanitize=False, removeHs=False)
            if raw.suffix.lower() in {".pdb", ".ent"}
            else Chem.MolFromMol2File(str(raw), sanitize=False, removeHs=False)
            if raw.suffix.lower() == ".mol2"
            else Chem.MolFromMolFile(str(raw), sanitize=False, removeHs=False)
        )
        if mol is None:
            raise ValueError(f"Unable to parse fragment/ligand file with RDKit: {raw}")
        dest = work_dir / f"{raw.stem}.converted.sdf"
        writer = Chem.SDWriter(str(dest))
        writer.write(mol)
        writer.close()
        return dest
    return raw


def parse_atoms_to_dock(raw: Any) -> list[int]:
    if raw in (None, "", []):
        return []
    if isinstance(raw, (list, tuple)):
        items = [int(item) for item in raw if str(item).strip() != ""]
    elif isinstance(raw, str):
        items = [int(token) for token in re.split(r"[,\s]+", raw.strip()) if token]
    else:
        raise ValueError("atoms_to_dock must be a list or comma/space-separated string of atom indices")
    if any(idx < 0 for idx in items):
        raise ValueError("atoms_to_dock indices must be >= 0")
    return items


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_shell_env(path: Path, mapping: dict[str, Any]) -> None:
    lines = [f"export {k}={shlex.quote(str(v))}" for k, v in mapping.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_prepare(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    payload = load_payload(Path(args.params_json).resolve())
    params = get_params(payload)
    input_files = get_input_files(payload)

    protein_pdb = resolve_named_file(
        input_files, ("protein_pdb", "receptor_pdb", "pdb_path", "structure_file"), input_dir
    )
    if protein_pdb is None:
        pdbs = sorted(
            p for p in input_dir.rglob("*.pdb")
            if "pocket" not in p.name.lower() and "ligand" not in p.name.lower()
        )
        protein_pdb = pdbs[0].resolve() if pdbs else None
    if protein_pdb is None:
        raise FileNotFoundError(f"protein_pdb not found in input_dir: {input_dir}")

    pocket_pdb = resolve_named_file(input_files, ("pocket_pdb",), input_dir)
    if pocket_pdb is None:
        pockets = sorted(p for p in input_dir.rglob("*.pdb") if "pocket" in p.name.lower())
        pocket_pdb = pockets[0].resolve() if pockets else None

    ref_ligand, ref_source = resolve_ref_ligand(
        input_files=input_files,
        input_dir=input_dir,
        params=params,
        protein_pdb=protein_pdb,
        pocket_pdb=pocket_pdb,
        work_dir=work_dir,
    )
    frag_ligand_raw = resolve_named_file(input_files, ("fragment_sdf", "ligand_sdf", "ligand"), input_dir)
    frag_ligand = resolve_fragment_file(frag_ligand_raw, work_dir)

    checkpoint = Path(
        str(params.get("checkpoint") or os.environ.get("LDDM_CHECKPOINT") or DEFAULT_CHECKPOINT)
    ).resolve()
    if not checkpoint.is_file():
        raise FileNotFoundError(f"LDDM checkpoint not found: {checkpoint}")

    generation_mode = str(params.get("generation_mode") or params.get("mode") or "denovo").strip().lower()
    if generation_mode in {"de_novo", "de-novo", "denovo", "design"}:
        generation_mode = "denovo"
    elif generation_mode in {"fragment", "frag", "grow", "growing", "linking"}:
        generation_mode = "fragment"
    elif generation_mode in {"dock", "docking", "partial_dock"}:
        generation_mode = "dock"
    else:
        raise ValueError(f"unsupported generation_mode: {generation_mode!r}")

    cli_mode = "dock" if generation_mode == "dock" else "design"
    if generation_mode in {"fragment", "dock"} and frag_ligand is None:
        raise ValueError(f"generation_mode={generation_mode!r} requires a fragment_sdf / ligand input file")
    atoms_to_dock = parse_atoms_to_dock(params.get("atoms_to_dock"))

    n_samples_raw = params.get("n_samples")
    if n_samples_raw in (None, ""):
        n_samples_raw = params.get("num_samples")
    n_samples = 10 if n_samples_raw in (None, "") else int(n_samples_raw)
    if not (1 <= n_samples <= 1000):
        raise ValueError(f"n_samples must be in 1..1000, got {n_samples}")

    batch_size = int_param(params, "batch_size", min(n_samples, 10), 1, 64)
    batch_size = min(batch_size, n_samples)
    n_steps = int_param(params, "n_steps", 100, 10, 1000)
    sampler = str(params.get("sampler") or "ForwardEuler").strip()
    if sampler not in {"ForwardEuler", "HeunSampler"}:
        raise ValueError(f"sampler must be ForwardEuler or HeunSampler, got {sampler!r}")
    sampling_noise = float_param(params, "sampling_noise", 5.0, 0.0, 50.0)
    molecule_size = "" if cli_mode == "dock" else validate_molecule_size(params.get("molecule_size"))
    seed = int_param(params, "seed", 2020, 0)
    runtime_device = resolve_device(str(params.get("device") or args.device or "auto"))

    sdf_out = Path(args.sdf_out).resolve()
    metadata_path = Path(args.metadata_out).resolve()
    metadata = {
        "task_id": args.task_id,
        "generation_mode": generation_mode,
        "cli_mode": cli_mode,
        "protein_pdb": str(protein_pdb),
        "pocket_pdb": str(pocket_pdb) if pocket_pdb else None,
        "ref_ligand": str(ref_ligand),
        "ref_ligand_source": ref_source,
        "fragment_ligand": str(frag_ligand) if frag_ligand else None,
        "atoms_to_dock": atoms_to_dock,
        "checkpoint": str(checkpoint),
        "n_samples": n_samples,
        "batch_size": batch_size,
        "n_steps": n_steps,
        "sampler": sampler,
        "sampling_noise": sampling_noise,
        "molecule_size": molecule_size or "histogram",
        "seed": seed,
        "runtime_device": runtime_device,
        "output_sdf": str(sdf_out),
    }
    write_json(metadata_path, metadata)

    write_shell_env(
        Path(args.env_out).resolve(),
        {
            "LDDM_MODE": cli_mode,
            "LDDM_GENERATION_MODE": generation_mode,
            "LDDM_PROTEIN": protein_pdb,
            "LDDM_REF_LIGAND": ref_ligand,
            "LDDM_FRAG_LIGAND": frag_ligand or "",
            "LDDM_ATOMS_TO_DOCK": " ".join(str(idx) for idx in atoms_to_dock),
            "LDDM_CHECKPOINT": checkpoint,
            "LDDM_OUTPUT_SDF": sdf_out,
            "LDDM_N_SAMPLES": n_samples,
            "LDDM_BATCH_SIZE": batch_size,
            "LDDM_N_STEPS": n_steps,
            "LDDM_SAMPLER": sampler,
            "LDDM_SAMPLING_NOISE": sampling_noise,
            "LDDM_MOLECULE_SIZE": molecule_size,
            "LDDM_SEED": seed,
            "LDDM_RUNTIME_DEVICE": runtime_device,
            "LDDM_METADATA_JSON": metadata_path,
        },
    )
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    from rdkit import Chem

    output_dir = Path(args.output_dir).resolve()
    artifact_dir = output_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    sdf_path = Path(args.sdf_path).resolve()
    metadata = json.loads(Path(args.metadata_json).read_text(encoding="utf-8"))

    if not sdf_path.is_file():
        return write_failure(
            output_dir,
            "LDDM output SDF not generated",
            code="MODEL_EXECUTION_FAILED",
            details=str(sdf_path),
            start_ts=args.start_ts,
        )

    supplier = Chem.SDMolSupplier(str(sdf_path), sanitize=False, removeHs=False)
    valid_smiles: list[tuple[str, int]] = []
    valid_mols = []
    for idx, mol in enumerate(supplier, start=1):
        if mol is None:
            continue
        try:
            probe = Chem.Mol(mol)
            Chem.SanitizeMol(probe)
            smiles = Chem.MolToSmiles(Chem.RemoveHs(probe))
        except Exception:  # noqa: BLE001
            continue
        if smiles:
            valid_smiles.append((smiles, idx))
            valid_mols.append(mol)

    if not valid_smiles:
        return write_failure(
            output_dir,
            "LDDM did not produce any valid molecules",
            code="NO_VALID_MOLECULES",
            details=str(sdf_path),
            start_ts=args.start_ts,
        )

    clean_sdf = artifact_dir / "generated_molecules.sdf"
    writer = Chem.SDWriter(str(clean_sdf))
    for mol in valid_mols:
        writer.write(mol)
    writer.close()

    smiles_path = artifact_dir / "SMILES.txt"
    lines = ["smiles\tmol_index"]
    lines.extend(f"{smi}\t{idx}" for smi, idx in valid_smiles)
    smiles_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    elapsed = round(max(0.0, time.time() - float(args.start_ts)), 3) if args.start_ts else 0.0
    result_payload = {
        "success": True,
        "outputs": {
            "smiles_file": "artifacts/SMILES.txt",
            "combined_sdf": "artifacts/generated_molecules.sdf",
            "molecule_count": len(valid_smiles),
            "ref_ligand_source": metadata.get("ref_ligand_source"),
            "n_steps": metadata.get("n_steps"),
            "sampler": metadata.get("sampler"),
            "molecule_size": metadata.get("molecule_size"),
        },
        "metrics": {
            "generated_count": len(valid_smiles),
            "batch_size": metadata.get("batch_size"),
            "n_steps": metadata.get("n_steps"),
            "elapsed_seconds": elapsed,
        },
    }
    write_json(output_dir / "result.json", result_payload)
    return 0


def write_failure(
    output_dir: Path,
    message: str,
    *,
    code: str = "MODEL_EXECUTION_FAILED",
    details: str = "",
    start_ts: str = "",
) -> int:
    elapsed = round(max(0.0, time.time() - float(start_ts)), 3) if start_ts else 0.0
    write_json(
        output_dir / "result.json",
        {
            "success": False,
            "error": {"code": code, "message": message, "details": details},
            "metrics": {"elapsed_seconds": elapsed},
        },
    )
    return 1


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        return cmd_prepare(args)
    if args.command == "finalize":
        return cmd_finalize(args)
    if args.command == "fail":
        return write_failure(
            Path(args.output_dir).resolve(),
            args.message,
            code=args.code,
            details=args.details,
            start_ts=args.start_ts,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
