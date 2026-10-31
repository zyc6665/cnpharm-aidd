#!/usr/bin/env python3
"""gmx_MMPBSA binding-free-energy entry for the SCIMINER Kubernetes runtime.

Input
  protein_structure@1 -> structure_file (PDB containing the receptor and ligand as
                          separate chains; protein/peptide complexes are supported).

The tool runs a short GROMACS equilibration/production internally (so that a single
PDB input yields a valid trajectory), then evaluates the binding free energy with
gmx_MMPBSA (GB model) and reports the DELTA TOTAL term.

Output (result.v2)
  molecule_table@1 : binding_energy (mean ΔG_bind, gas/solv components)
  run_report@1     : report_json (full gmx_MMPBSA log summary)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gromacs_platform import (  # noqa: E402
    GMX,
    file_ref,
    pick_protein,
    progress,
    run_pipeline,
    write_json,
)

AMBER_ROOT = Path(os.environ.get("AMBER_ROOT", "/opt/amber"))
AMBER_ENV = AMBER_ROOT / "anaconda3" / "envs" / "AmberTools"
MPIRUN = AMBER_ROOT / "anaconda3" / "bin" / "mpirun"


def chain_residue_ranges(pdb: Path) -> tuple[int, int]:
    """Return (receptor_residue_count, total_residue_count) by TER/chain order."""
    counts: list[int] = []
    current: set[tuple[str, str, str]] = set()
    for line in pdb.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("TER"):
            if current:
                counts.append(len(current))
                current = set()
            continue
        if not line.startswith("ATOM"):
            continue
        key = (line[21:22], line[22:27].strip(), line[26:27])
        current.add(key)
    if current:
        counts.append(len(current))
    if len(counts) < 2:
        raise SystemExit(
            "gmx_MMPBSA requires a receptor/ligand complex with at least two chains "
            "(PDB TER records); this input has " + str(len(counts)) + " chain(s)"
        )
    return counts[0], sum(counts)


def make_index(work: Path, receptor_residues: int, total_residues: int) -> tuple[int, int]:
    """Create Receptor/Ligand groups with gmx make_ndx and return their indices."""
    commands = f"ri 1-{receptor_residues}\nname 19 Receptor\nri {receptor_residues + 1}-{total_residues}\nname 20 Ligand\nq\n"
    result = subprocess.run(
        [GMX, "make_ndx", "-f", "npt.gro", "-o", "index.ndx"],
        cwd=str(work),
        input=commands,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not (work / "index.ndx").is_file():
        raise SystemExit("gmx make_ndx failed:\n" + result.stdout[-2000:] + result.stderr[-2000:])
    match_rec = re.search(r"group\s+(\d+)\s+Receptor", result.stdout)
    match_lig = re.search(r"group\s+(\d+)\s+Ligand", result.stdout)
    if match_rec and match_lig:
        return int(match_rec.group(1)), int(match_lig.group(1))
    # Parse the generated index file: gmx names the residue-range groups
    # "r_1-<receptor>" and "r_<receptor+1>-<total>"; return their 0-based positions.
    names: list[str] = []
    for line in (work / "index.ndx").read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("[") and line.rstrip().endswith("]"):
            names.append(line.strip()[1:-1].strip())
    receptor_name = f"r_1-{receptor_residues}"
    ligand_name = f"r_{receptor_residues + 1}-{total_residues}"
    try:
        return names.index(receptor_name), names.index(ligand_name)
    except ValueError as exc:
        raise SystemExit("cannot locate receptor/ligand index groups in index.ndx: " + str(names)) from exc


def parse_mmpbsa_csv(csv_path: Path) -> dict[str, Any]:
    rows = list(csv.reader(csv_path.open(encoding="utf-8", errors="ignore")))
    if not rows:
        return {}
    # gmx_MMPBSA CSV concatenates several sections; the binding result is the
    # "Delta Energy Terms" block whose header ends with the TOTAL column.
    section_start = None
    for index, row in enumerate(rows):
        if row and row[0].strip().lower().startswith("delta energy"):
            section_start = index + 1
            break
    search_rows = rows[section_start:] if section_start is not None else rows
    header_index = None
    for index, row in enumerate(search_rows):
        if row and any(cell.strip() == "TOTAL" for cell in row):
            header_index = index
            break
    if header_index is None:
        return {"terms": rows[0] if rows else [], "values": rows[1:]}
    header = [item.strip() for item in search_rows[header_index]]
    data = search_rows[header_index + 1:]
    if "TOTAL" in header:
        idx = header.index("TOTAL")
        values = []
        for row in data:
            if not row or not row[0].strip():
                continue
            try:
                values.append(float(row[idx]))
            except (ValueError, IndexError):
                continue
        if values:
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / max(1, len(values) - 1)
            return {"delta_g_bind_kcal_mol": mean, "delta_g_std": variance ** 0.5,
                    "frames": len(values), "terms": header, "values": data}
    return {"terms": header, "values": data}


def parse_mmpbsa_dat(dat_path: Path) -> str:
    text = dat_path.read_text(encoding="utf-8", errors="ignore") if dat_path.is_file() else ""
    lines = [line for line in text.splitlines() if "DELTA" in line or "TOTAL" in line]
    return "\n".join(lines[-40:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default="unknown")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--params-json", required=True)
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    work_root = Path(args.work_dir or (output_dir / "work")).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    (output_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    work = work_root / "md"
    work.mkdir(parents=True, exist_ok=True)

    params = json.loads(Path(args.params_json).read_text(encoding="utf-8"))
    files = params.get("input_files") or {}
    manifest_path = input_dir / "manifest.json"
    if manifest_path.is_file():
        staged = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = {
            entry["name"]: str((input_dir.parent / entry["path"]).resolve())
            for entry in staged
            if entry.get("name") and entry.get("path") and entry.get("role") != "metadata_json"
            and not str(entry.get("path", "")).endswith(".metadata_json.json")
        }
    run_params = params.get("params") or {}
    force_field = str(run_params.get("force_field") or "amber99sb-ildn")
    water_model = str(run_params.get("water_model") or "tip3p")
    box_distance = float(run_params.get("box_distance") or 1.0)
    nsteps = int(run_params.get("nsteps") or 500)
    dt = float(run_params.get("dt") or 0.002)
    temperature = float(run_params.get("temperature") or 300.0)

    protein = pick_protein(files, input_dir)
    receptor_residues, total_residues = chain_residue_ranges(protein)
    progress(2, "short MD for MMPBSA")
    run_pipeline(
        protein,
        work,
        force_field=force_field,
        water_model=water_model,
        box_distance=box_distance,
        nsteps=nsteps,
        dt=dt,
        temperature=temperature,
        device=args.device,
    )

    progress(78, "build index groups")
    rec_idx, lig_idx = make_index(work, receptor_residues, total_residues)

    frames = max(1, nsteps // 500)
    (work / "mmpbsa.in").write_text(
        "&general\n"
        f'  sys_name="Complex", startframe=1, endframe={frames}, interval=1, temperature={temperature}, verbose=2,\n'
        "/\n&gb\n  igb=5, saltcon=0.150,\n/\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "OPAL_PREFIX": str(AMBER_ROOT / "anaconda3"),
            "AMBERHOME": str(AMBER_ENV),
            "PATH": f"{AMBER_ENV / 'bin'}:{AMBER_ROOT / 'anaconda3' / 'bin'}:" + env.get("PATH", ""),
            "OMPI_MCA_plm": "isolated",
            "OMPI_MCA_rmaps_base_oversubscribe": "1",
            "LD_LIBRARY_PATH": ":".join(
                [
                    str(AMBER_ROOT / "anaconda3" / "lib"),
                    str(AMBER_ENV / "lib"),
                    str(Path("/opt/gromacs/lib")),
                    env.get("LD_LIBRARY_PATH", ""),
                ]
            ),
        }
    )
    progress(82, "gmx_MMPBSA")
    command = [
        str(MPIRUN), "--allow-run-as-root", "-n", "1",
        str(AMBER_ENV / "bin" / "python"), str(AMBER_ENV / "bin" / "gmx_MMPBSA"),
        "-O", "-i", "mmpbsa.in", "-cs", "md.tpr", "-ci", "index.ndx",
        "-cg", str(rec_idx), str(lig_idx), "-ct", "md.xtc", "-cp", "topol.top",
        "-o", "FINAL_RESULTS_MMPBSA.dat", "-eo", "FINAL_RESULTS_MMPBSA.csv", "-nogui",
    ]
    result = subprocess.run(command, cwd=str(work), env=env, text=True, capture_output=True, check=False)
    (work / "mmpbsa.console.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise SystemExit("gmx_MMPBSA failed:\n" + (result.stdout + result.stderr)[-3000:])

    summary = parse_mmpbsa_csv(work / "FINAL_RESULTS_MMPBSA.csv")
    details = parse_mmpbsa_dat(work / "FINAL_RESULTS_MMPBSA.dat")

    out = output_dir / "artifacts"
    table_path = out / "binding_energy.csv"
    delta = summary.get("delta_g_bind_kcal_mol")
    with table_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["molecule_id", "delta_g_bind_kcal_mol", "delta_g_std_kcal_mol", "frames"])
        writer.writerow(["complex_001", f"{delta:.3f}" if isinstance(delta, (int, float)) else "",
                         f"{summary.get('delta_g_std', ''):.3f}" if isinstance(summary.get("delta_g_std"), (int, float)) else "",
                         summary.get("frames", "")])
    write_json(out / "metadata.json", {"molecule_id_field": "molecule_id", "source_task_id": args.task_id})
    report = {
        "source_task_id": args.task_id,
        "tool": "gmx_MMPBSA",
        "status": "succeeded",
        "delta_g_bind_kcal_mol": delta,
        "frames": summary.get("frames"),
        "receptor_group": rec_idx,
        "ligand_group": lig_idx,
        "summary": details,
    }
    write_json(out / "report.json", report)
    result_payload = {
        "result_version": "aidd.sciminer/result",
        "artifacts": {
            "binding_energy": {
                "type": "molecule_table@1",
                "files": {"table_file": file_ref(output_dir, "artifacts/binding_energy.csv"),
                          "metadata_json": file_ref(output_dir, "artifacts/metadata.json")},
                "metadata": {"molecule_id_field": "molecule_id", "source_task_id": args.task_id},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, "artifacts/report.json")},
                "metadata": {"source_task_id": args.task_id},
            },
        },
        "metrics": {"delta_g_bind_kcal_mol": delta, "frames": summary.get("frames")},
    }
    write_json(output_dir / "result.json", result_payload)
    progress(100, "done")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
