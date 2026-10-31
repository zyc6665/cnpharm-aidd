#!/usr/bin/env python3
"""GROMACS molecular-dynamics entry for the SCIMINER Kubernetes runtime.

Input
  protein_structure@1 -> structure_file (PDB; protein or protein/peptide complex.
                          Small-molecule ligands must be parameterised before MD and
                          are intentionally out of scope for this tool.)

Output (result.v2)
  md_trajectory@1 : topology_pdb (starting structure), trajectory_dcd, analysis_csv,
                    metadata_json
  run_report@1    : report_json

The pipeline follows the standard GROMACS recipe: pdb2gmx -> editconf -> solvate ->
genion -> energy minimisation -> NVT -> NPT -> production.  GPU is used when the
container has a CUDA device, otherwise it falls back to CPU automatically.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

GMX = os.environ.get("GMX_BIN", "gmx")


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


def progress(pct: int, message: str) -> None:
    print(f"__DRP_PROGRESS__ {json.dumps({'pct': pct, 'message': message}, ensure_ascii=False)}", flush=True)


def resolve_input(input_dir: Path, value: str) -> Path:
    for candidate in (Path(value), input_dir / value, input_dir / Path(value).name, input_dir.parent / value):
        if candidate.is_file():
            return candidate
    raise SystemExit(f"input file not found: {value}")


def pick_protein(files: dict[str, str], input_dir: Path) -> Path:
    for key, value in files.items():
        low = key.lower()
        if any(word in low for word in ("protein", "structure", "receptor", "pdb")):
            candidate = resolve_input(input_dir, value)
            if candidate.suffix.lower() in (".pdb", ".cif"):
                return candidate
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in (".pdb", ".cif"):
            return path
    raise SystemExit("cannot find a protein PDB input")


def run(cmd: list[str], cwd: Path, stdin_text: str | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        input=stdin_text,
        text=True,
        capture_output=True,
        check=False,
    )
    (cwd / (Path(cmd[0]).name + ".console.log")).open("a", encoding="utf-8").write(
        "$ " + " ".join(cmd) + "\n" + result.stdout + "\n" + result.stderr + "\n"
    )
    if result.returncode != 0:
        tail = (result.stdout + "\n" + result.stderr).strip().splitlines()[-25:]
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(cmd)}\n" + "\n".join(tail))
    return result.stdout + result.stderr


def sanitize_pdb(source: Path, target: Path) -> None:
    """Keep protein/peptide ATOM records and TER; drop solvent/hetero records."""
    lines: list[str] = []
    for line in source.read_text(encoding="utf-8", errors="ignore").splitlines():
        record = line[:6].strip()
        if record in ("ATOM", "TER"):
            lines.append(line)
        elif record == "END":
            break
    if not any(line.startswith("ATOM") for line in lines):
        raise SystemExit("input PDB contains no ATOM records")
    lines.append("END")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def mdp_text(kind: str, nsteps: int, dt: float, temperature: float) -> str:
    common = f"""integrator  = md
dt          = {dt}
nsteps      = {nsteps}
nstxout-compressed = 500
nstenergy   = 500
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb    = 1.0
rvdw        = 1.0
DispCorr    = EnerPres
constraints = h-bonds
constraint-algorithm = lincs
"""
    if kind == "minim":
        return """integrator = steep
emtol = 1000.0
emstep = 0.01
nsteps = 500
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb = 1.0
rvdw = 1.0
"""
    if kind == "ions":
        return "integrator = steep\nnsteps = 0\n"
    if kind == "nvt":
        return common + f"""tcoupl = V-rescale
tc-grps = System
tau-t = 0.1
ref-t = {temperature}
gen-vel = yes
gen-temp = {temperature}
gen-seed = -1
pcoupl = no
"""
    if kind == "npt":
        return common + f"""tcoupl = V-rescale
tc-grps = System
tau-t = 0.1
ref-t = {temperature}
pcoupl = Parrinello-Rahman
pcoupltype = isotropic
tau-p = 2.0
ref-p = 1.0
compressibility = 4.5e-5
"""
    return common + f"""tcoupl = V-rescale
tc-grps = System
tau-t = 0.1
ref-t = {temperature}
pcoupl = Parrinello-Rahman
pcoupltype = isotropic
tau-p = 2.0
ref-p = 1.0
compressibility = 4.5e-5
"""


def run_mdrun(work: Path, device: str) -> str:
    base = [GMX, "mdrun", "-deffnm", "md", "-ntmpi", "1", "-ntomp", str(max(1, min(8, os.cpu_count() or 1)))]
    if device in ("auto", "gpu"):
        try:
            return run(base + ["-nb", "gpu", "-pme", "cpu", "-gpu_id", "0"], work)
        except SystemExit as exc:
            if device == "gpu":
                raise
            print(f"[gromacs] GPU mdrun failed, retrying on CPU: {exc}", flush=True)
            for pattern in ("md.log", "md.edr", "md.trr", "md.xtc", "md.gro", "md.cpt"):
                (work / pattern).unlink(missing_ok=True)
    return run(base + ["-nb", "cpu", "-pme", "cpu"], work)


def parse_xvg(path: Path) -> list[tuple[float, ...]]:
    rows: list[tuple[float, ...]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line[0] in ("#", "@"):
            continue
        parts = line.split()
        try:
            rows.append(tuple(float(item) for item in parts))
        except ValueError:
            continue
    return rows


def xvg_legends(path: Path) -> dict[int, str]:
    legends: dict[int, str] = {}
    if not path.is_file():
        return legends
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(r'@\s+s(\d+)\s+legend\s+"([^"]+)"', line.strip())
        if match:
            legends[int(match.group(1)) + 1] = match.group(2)
    return legends


def write_analysis_csv(work: Path, out_csv: Path) -> None:
    energy_xvg = work / "energy.xvg"
    run(
        [GMX, "energy", "-f", "md.edr", "-o", "energy.xvg"],
        work,
        stdin_text="Temperature\nPotential\nPressure\n\n",
    )
    energy_rows = parse_xvg(energy_xvg)
    legends = xvg_legends(energy_xvg)
    max_col = max(legends.keys() or [0])
    columns = ["time_ps"] + [legends.get(index, f"col{index}") for index in range(1, max_col + 1)]

    rmsd: dict[float, float] = {}
    try:
        run(
            [GMX, "rms", "-s", "md.tpr", "-f", "md.xtc", "-o", "rmsd.xvg"],
            work,
            stdin_text="Backbone\nBackbone\n",
        )
        for row in parse_xvg(work / "rmsd.xvg"):
            rmsd[round(row[0], 3)] = row[1]
    except SystemExit:
        pass

    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns + ["rmsd_nm"])
        for row in energy_rows:
            writer.writerow([f"{value:.4f}" if isinstance(value, float) else value for value in row]
                            + [rmsd.get(round(row[0], 3), "")])


def run_pipeline(
    protein: Path,
    work: Path,
    *,
    force_field: str,
    water_model: str,
    box_distance: float,
    nsteps: int,
    dt: float,
    temperature: float,
    device: str,
) -> dict[str, Any]:
    clean = work / "protein_clean.pdb"
    sanitize_pdb(protein, clean)

    progress(5, "pdb2gmx")
    run([GMX, "pdb2gmx", "-f", str(clean), "-o", "processed.gro", "-water", water_model,
         "-ff", force_field, "-ignh"], work)
    progress(15, "editconf")
    run([GMX, "editconf", "-f", "processed.gro", "-o", "boxed.gro", "-c", "-d", str(box_distance), "-bt", "cubic"], work)
    progress(20, "solvate")
    run([GMX, "solvate", "-cp", "boxed.gro", "-cs", "spc216.gro", "-o", "solvated.gro", "-p", "topol.top"], work)

    (work / "ions.mdp").write_text(mdp_text("ions", 0, dt, temperature), encoding="utf-8")
    progress(28, "genion")
    run([GMX, "grompp", "-f", "ions.mdp", "-c", "solvated.gro", "-p", "topol.top", "-o", "ions.tpr", "-maxwarn", "2"], work)
    run([GMX, "genion", "-s", "ions.tpr", "-o", "ionized.gro", "-p", "topol.top",
         "-pname", "NA", "-nname", "CL", "-neutral"], work, stdin_text="SOL\n")

    (work / "minim.mdp").write_text(mdp_text("minim", 0, dt, temperature), encoding="utf-8")
    progress(35, "energy-minimisation")
    run([GMX, "grompp", "-f", "minim.mdp", "-c", "ionized.gro", "-p", "topol.top", "-o", "em.tpr", "-maxwarn", "2"], work)
    run([GMX, "mdrun", "-deffnm", "em", "-ntmpi", "1", "-ntomp", str(max(1, min(8, os.cpu_count() or 1)))], work)

    (work / "nvt.mdp").write_text(mdp_text("nvt", 500, dt, temperature), encoding="utf-8")
    progress(45, "NVT equilibration")
    run([GMX, "grompp", "-f", "nvt.mdp", "-c", "em.gro", "-r", "em.gro", "-p", "topol.top", "-o", "nvt.tpr", "-maxwarn", "2"], work)
    run([GMX, "mdrun", "-deffnm", "nvt", "-ntmpi", "1", "-ntomp", str(max(1, min(8, os.cpu_count() or 1)))], work)

    (work / "npt.mdp").write_text(mdp_text("npt", 500, dt, temperature), encoding="utf-8")
    progress(55, "NPT equilibration")
    run([GMX, "grompp", "-f", "npt.mdp", "-c", "nvt.gro", "-r", "nvt.gro", "-t", "nvt.cpt", "-p", "topol.top", "-o", "npt.tpr", "-maxwarn", "2"], work)
    run([GMX, "mdrun", "-deffnm", "npt", "-ntmpi", "1", "-ntomp", str(max(1, min(8, os.cpu_count() or 1)))], work)

    (work / "md.mdp").write_text(mdp_text("md", nsteps, dt, temperature), encoding="utf-8")
    progress(65, f"production MD ({nsteps} steps)")
    run([GMX, "grompp", "-f", "md.mdp", "-c", "npt.gro", "-t", "npt.cpt", "-p", "topol.top", "-o", "md.tpr", "-maxwarn", "2"], work)
    run_mdrun(work, device)

    progress(88, "convert trajectory")
    # GROMACS trjconv 不直接写 DCD；用 mdtraj 把 XTC 转为标准 DCD。
    import mdtraj as _mdtraj

    _traj = _mdtraj.load(str(work / "md.xtc"), top=str(work / "md.gro"))
    _traj.save_dcd(str(work / "trajectory.dcd"))
    run([GMX, "trjconv", "-s", "md.tpr", "-f", "md.gro", "-o", "topology.pdb"], work, stdin_text="0\n")
    return {"duration_ns": nsteps * dt / 1000.0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default="unknown")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--params-json", required=True)
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    work = Path(args.work_dir or (output_dir / "work")).resolve()
    work.mkdir(parents=True, exist_ok=True)
    (output_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    work = work / "md"

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
    nsteps = int(run_params.get("nsteps") or 2500)
    dt = float(run_params.get("dt") or 0.002)
    temperature = float(run_params.get("temperature") or 300.0)

    protein = pick_protein(files, input_dir)
    work.mkdir(parents=True, exist_ok=True)
    progress(1, "prepare")
    info = run_pipeline(
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

    out = output_dir / "artifacts"
    shutil.copyfile(work / "topology.pdb", out / "topology.pdb")
    shutil.copyfile(work / "trajectory.dcd", out / "trajectory.dcd")
    write_analysis_csv(work, out / "analysis.csv")

    metadata = {
        "source_task_id": args.task_id,
        "force_field": force_field,
        "duration_ns": info["duration_ns"],
        "frames": nsteps // 500 + 1,
        "temperature_k": temperature,
        "engine": "GROMACS 2024.1",
        "water_model": water_model,
        "device": args.device,
    }
    write_json(out / "metadata.json", metadata)
    report = {
        "source_task_id": args.task_id,
        "tool": "gromacs-md",
        "status": "succeeded",
        "force_field": force_field,
        "duration_ns": info["duration_ns"],
        "nsteps": nsteps,
        "dt_ps": dt,
        "temperature_k": temperature,
    }
    write_json(out / "report.json", report)

    result = {
        "result_version": "aidd.sciminer/result",
        "artifacts": {
            "trajectory": {
                "type": "md_trajectory@1",
                "files": {
                    "topology_pdb": file_ref(output_dir, "artifacts/topology.pdb"),
                    "trajectory_dcd": file_ref(output_dir, "artifacts/trajectory.dcd"),
                    "analysis_csv": file_ref(output_dir, "artifacts/analysis.csv"),
                    "metadata_json": file_ref(output_dir, "artifacts/metadata.json"),
                },
                "metadata": {"source_task_id": args.task_id},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, "artifacts/report.json")},
                "metadata": {"source_task_id": args.task_id},
            },
        },
        "metrics": {"duration_ns": info["duration_ns"], "nsteps": nsteps, "temperature_k": temperature},
    }
    write_json(output_dir / "result.json", result)
    progress(100, "done")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
