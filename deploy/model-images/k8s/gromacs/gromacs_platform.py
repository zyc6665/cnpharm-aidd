#!/usr/bin/env python3
"""GROMACS molecular-dynamics entry for the AIDD Kubernetes runtime.

Inputs
  protein_structure@1 -> protein_pdb (PDB protein / receptor structure)
  ligand_structure@1  -> ligand_sdf (optional SDF/MOL/MOL2/PDB ligand for complex MD;
                         parameterised via GAFF2/acpype when no custom ITP/GRO is supplied)
  custom_itp / custom_gro / custom_prm / custom_zip (optional Mode 0 user topology bundle)

Output (result.v2)
  md_trajectory@1 : topology_pdb, trajectory_dcd, analysis_csv,
                    rmsf_csv (per-residue RMSF), contacts_csv (interaction summary),
                    interactions_json (timeline & residue network), metadata_json
  run_report@1    : report_json

The pipeline runs ``pdb2gmx`` -> (optional ligand GAFF2/Mode-0 merge & topology patch)
-> ``editconf`` -> ``solvate`` -> ``genion`` -> EM -> NVT -> NPT -> production MD ->
PBC centering -> trajectory/RMSF/interactions analysis.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

GMX = os.environ.get("GMX_BIN", "gmx")

_LIGAND_EXTS = (".sdf", ".mol", ".mol2", ".pdb")
_PROTEIN_EXTS = (".pdb", ".cif")
_CUSTOM_EXTS = (".zip", ".itp", ".gro", ".prm", ".rtp")


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


def _try_resolve_input(input_dir: Path, value: str) -> Path | None:
    for candidate in (Path(value), input_dir / value, input_dir / Path(value).name, input_dir.parent / value):
        if candidate.is_file():
            return candidate
    return None


def collect_input_slots(
    input_dir: Path,
    params: dict[str, Any],
    manifest_path: Path | None = None,
) -> dict[str, list[Path]]:
    """Collect non-metadata candidate files grouped by input slot name."""
    slots: dict[str, list[Path]] = {}

    def _add(slot: str, path: Path | None) -> None:
        if path is None or not path.is_file():
            return
        if path.suffix.lower() == ".json" or path.name.endswith(".metadata_json.json"):
            return
        bucket = slots.setdefault(slot, [])
        resolved = path.resolve()
        if resolved not in bucket:
            bucket.append(resolved)

    mpath = manifest_path if manifest_path is not None else (input_dir / "manifest.json")
    if mpath.is_file():
        staged = json.loads(mpath.read_text(encoding="utf-8"))
        for entry in staged:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            rel = entry.get("path")
            if not name or not rel or entry.get("role") == "metadata_json":
                continue
            _add(str(name), _try_resolve_input(input_dir, str(rel)))

    for key, value in (params.get("input_files") or {}).items():
        if isinstance(value, str) and value.strip():
            _add(str(key), _try_resolve_input(input_dir, value))

    return slots


def pick_protein(files: dict[str, str] | dict[str, list[Path]], input_dir: Path) -> Path:
    """Resolve protein PDB/CIF input while staying backward compatible with dict[str, str]."""
    for key, value in files.items():
        low = key.lower()
        if any(word in low for word in ("ligand", "custom", "topology_zip")):
            continue
        if any(word in low for word in ("protein", "structure", "receptor", "pdb")):
            candidates = value if isinstance(value, list) else [resolve_input(input_dir, value)]
            for candidate in candidates:
                if candidate.suffix.lower() in _PROTEIN_EXTS:
                    return candidate
    for path in sorted(input_dir.rglob("*")):
        low = path.as_posix().lower()
        if any(word in low for word in ("/ligand", "/custom")):
            continue
        if path.is_file() and path.suffix.lower() in _PROTEIN_EXTS:
            return path
    raise SystemExit("cannot find a protein PDB input")


def pick_ligand_inputs(
    slots: dict[str, list[Path]],
    input_dir: Path,
    protein_path: Path,
) -> dict[str, Path | None]:
    """Extract optional ligand SDF/MOL/MOL2/PDB and Mode-0 custom topology paths."""
    resolved_protein = protein_path.resolve()
    result: dict[str, Path | None] = {
        "ligand_sdf": None,
        "custom_itp": None,
        "custom_prm": None,
        "custom_gro": None,
        "custom_zip": None,
    }

    def _first_matching(keys: tuple[str, ...], exts: tuple[str, ...]) -> Path | None:
        for slot_name, paths in slots.items():
            low = slot_name.lower()
            if not any(token in low for token in keys):
                continue
            for path in paths:
                if path.resolve() == resolved_protein:
                    continue
                if path.suffix.lower() in exts:
                    return path
        return None

    result["ligand_sdf"] = _first_matching(("ligand_sdf", "ligand_structure", "ligand"), _LIGAND_EXTS)
    result["custom_zip"] = _first_matching(("custom_zip", "topology_zip", "ligand_topology", "custom"), (".zip",))
    result["custom_itp"] = _first_matching(("custom_itp", "ligand_itp", "ligand_topology", "itp"), (".itp",))
    result["custom_prm"] = _first_matching(("custom_prm", "ligand_prm", "ligand_topology", "prm", "rtp"), (".prm", ".rtp"))
    result["custom_gro"] = _first_matching(("custom_gro", "ligand_gro", "ligand_topology", "gro"), (".gro",))

    # Avoid passing a Mode-0 custom_itp zip folder's files twice if ligand_sdf matched nothing
    if result["ligand_sdf"] is None:
        for path in sorted(input_dir.rglob("*")):
            if not path.is_file() or path.resolve() == resolved_protein:
                continue
            if path.suffix.lower() in (".sdf", ".mol", ".mol2"):
                result["ligand_sdf"] = path.resolve()
                break
            if path.suffix.lower() == ".zip" and result["custom_zip"] is None:
                result["custom_zip"] = path.resolve()
            elif path.suffix.lower() == ".itp" and result["custom_itp"] is None:
                result["custom_itp"] = path.resolve()
            elif path.suffix.lower() == ".gro" and result["custom_gro"] is None:
                result["custom_gro"] = path.resolve()
            elif path.suffix.lower() in (".prm", ".rtp") and result["custom_prm"] is None:
                result["custom_prm"] = path.resolve()

    return result


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


def write_analysis_csv(work: Path, out_csv: Path, trajectory_name: str = "md.xtc") -> None:
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
            [GMX, "rms", "-s", "md.tpr", "-f", trajectory_name, "-o", "rmsd.xvg"],
            work,
            stdin_text="Backbone\nBackbone\n",
        )
        for row in parse_xvg(work / "rmsd.xvg"):
            rmsd[round(row[0], 3)] = row[1]
    except SystemExit:
        pass

    # 回转半径是逐帧量（gyrate 的 xvg 第 2 列就是 Rg，单位 nm），
    # 与 analysis.csv 的时间序列天然对齐。
    gyration: dict[float, float] = {}
    try:
        run(
            [GMX, "gyrate", "-s", "md.tpr", "-f", trajectory_name, "-o", "gyrate.xvg"],
            work,
            stdin_text="Backbone\n",
        )
        for row in parse_xvg(work / "gyrate.xvg"):
            gyration[round(row[0], 3)] = row[1]
    except SystemExit:
        pass

    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns + ["rmsd_nm", "rg_nm"])
        for row in energy_rows:
            key = round(row[0], 3)
            writer.writerow([f"{value:.4f}" if isinstance(value, float) else value for value in row]
                            + [rmsd.get(key, ""), gyration.get(key, "")])


def backbone_residues(pdb: Path) -> list[tuple[str, str, str]]:
    """按 CA 出现顺序返回 (chain, residue_seq, residue_name)。

    ``gmx rmsf -res`` 的横轴是「选中组里的第几个残基」，要和 PDB 里的残基
    顺序对齐才能给出残基名；用 CA 原子做锚点，避免把氢原子或 altloc 算进去。
    """
    residues: list[tuple[str, str, str]] = []
    if not pdb.is_file():
        return residues
    for line in pdb.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        key = (line[21:22].strip() or "A", line[22:26].strip(), line[17:20].strip())
        if key not in residues:
            residues.append(key)
    return residues


def write_rmsf_csv(work: Path, out_csv: Path, topology: Path, trajectory_name: str = "md.xtc") -> bool:
    """写逐残基 RMSF 表。RMSF 是「时间平均后的每残基涨落」，

    不是逐帧量，所以它不能塞进 analysis.csv 的时间序列里——这一列过去一直
    是空的，页面上「RMSF」图恒为空白（``docs/26`` H-3）。这里单独出一张表：
    ``residue_seq, residue_name, rmsf_nm``。
    """
    try:
        run(
            [GMX, "rmsf", "-s", "md.tpr", "-f", trajectory_name, "-o", "rmsf.xvg", "-res"],
            work,
            stdin_text="Backbone\n",
        )
    except SystemExit:
        return False
    rows = parse_xvg(work / "rmsf.xvg")
    if not rows:
        return False
    residues = backbone_residues(topology)
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["residue_seq", "residue_name", "rmsf_nm"])
        for index, row in enumerate(rows, start=1):
            try:
                position = int(round(float(row[0])))
            except (TypeError, ValueError):
                position = index
            if 1 <= position <= len(residues):
                chain, residue_seq, residue_name = residues[position - 1]
            else:
                chain, residue_seq, residue_name = "", str(position), ""
            del chain  # 链信息不在表里：残基序号已经能唯一定位（单链 MD）
            writer.writerow([residue_seq, residue_name, f"{row[1]:.4f}"])
    return True


def _stage_ligand_topology_into_work(work: Path, param_lig: Any) -> tuple[str | None, str, str | None]:
    """Copy delivered ligand ITP/posre files into ``work/`` so topol.top resolves them locally."""
    atomtypes_name: str | None = None
    if param_lig.atomtypes_itp is not None and Path(param_lig.atomtypes_itp).is_file():
        target = work / "ligand_atomtypes.itp"
        shutil.copyfile(param_lig.atomtypes_itp, target)
        atomtypes_name = target.name

    ligand_target = work / "ligand.itp"
    shutil.copyfile(param_lig.ligand_itp, ligand_target)

    posre_name: str | None = None
    if param_lig.posre_itp is not None and Path(param_lig.posre_itp).is_file():
        posre_target = work / "posre_ligand.itp"
        shutil.copyfile(param_lig.posre_itp, posre_target)
        posre_name = posre_target.name

    return atomtypes_name, ligand_target.name, posre_name


def center_pbc_trajectory(work: Path) -> tuple[Path, Path]:
    """Run ``gmx trjconv -pbc mol -center`` so complex/protein stays whole and centered.

    Falls back cleanly to raw ``md.xtc`` / ``md.gro`` if centering fails (e.g. non-standard groups).
    """
    xtc_out = work / "md_pbc.xtc"
    gro_out = work / "md_pbc.gro"
    try:
        run(
            [GMX, "trjconv", "-s", "md.tpr", "-f", "md.xtc", "-o", str(xtc_out.name), "-pbc", "mol", "-center"],
            work,
            stdin_text="Protein\nSystem\n",
        )
        run(
            [GMX, "trjconv", "-s", "md.tpr", "-f", "md.gro", "-o", str(gro_out.name), "-pbc", "mol", "-center"],
            work,
            stdin_text="Protein\nSystem\n",
        )
        if xtc_out.is_file() and gro_out.is_file():
            return xtc_out, gro_out
    except SystemExit as exc:
        print(f"[gromacs] PBC centering skipped, using raw trajectory: {exc}", flush=True)
    return work / "md.xtc", work / "md.gro"


def run_interactions_postprocess(
    topology_pdb: Path,
    trajectory_path: Path,
    out_dir: Path,
    *,
    ligand_resname: str = "LIG",
    ligand_template_sdf: Path | None = None,
    stride: int = 1,
    water_resname: str | None = None,
) -> dict[str, Any]:
    """Run ``interactions_analysis.analyze_trajectory`` and emit ``contacts.csv`` + ``interactions.json``.

    Degrades gracefully if post-processing fails so a completed GROMACS trajectory is preserved.
    """
    try:
        try:
            from interactions_analysis import InteractionConfig, analyze_trajectory
        except ImportError:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from interactions_analysis import InteractionConfig, analyze_trajectory

        cfg = InteractionConfig(
            ligand_resname=ligand_resname,
            stride=max(1, int(stride)),
            water_resname=(water_resname or None),
        )
        return analyze_trajectory(
            topology_pdb,
            trajectory_path,
            output_contacts_csv=out_dir / "contacts.csv",
            output_summary_json=out_dir / "interactions.json",
            config=cfg,
            ligand_template_sdf=ligand_template_sdf,
        )
    except Exception as exc:  # noqa: BLE001 - never discard a finished MD trajectory
        print(f"[gromacs] interaction postprocess skipped: {exc}", flush=True)
        return {
            "mode": "skipped",
            "engine": "skipped",
            "summary": {"total_interactions": 0},
            "warnings": [f"interaction analysis failed: {exc}"],
        }


_INTEGER_RE = re.compile(r"[+-]?\d+(?:\.0+)?")


def _strict_int(value: Any, *, minimum: int, warnings: list[str], label: str, maximum: int | None = None) -> int | None:
    """Parse one movie setting without ``float()`` (which rounds ``1024.000…01``
    and raises ``OverflowError`` on ``10**400``): bool is rejected, int passes
    through, float must be finite and integral, str must match a strict integer
    pattern, then the range bounds are enforced."""
    if value is None:
        return None
    if isinstance(value, bool):
        warnings.append(f"{label} rejected non-numeric {value!r}")
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if not (math.isfinite(value) and value.is_integer()):
            warnings.append(f"{label} ignored non-integer {value!r}")
            return None
        number = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if _INTEGER_RE.fullmatch(text) is None:
            warnings.append(f"{label} ignored invalid {value!r}")
            return None
        try:
            number = int(text.split(".", 1)[0])
        except (ValueError, OverflowError):
            warnings.append(f"{label} ignored out-of-range {value!r}")
            return None
    else:
        warnings.append(f"{label} ignored invalid {value!r}")
        return None
    if number < minimum or (maximum is not None and number > maximum):
        warnings.append(f"{label} out of range: {number} (min {minimum}, max {maximum})")
        return None
    return number


def _movie_file_ready(path: Path, summary: dict[str, Any]) -> bool:
    """True only when the movie was declared written *and* the file is non-empty."""
    if summary.get("written") is not True:
        return False
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _movie_metadata_fields(summary: dict[str, Any]) -> dict[str, Any]:
    """Metadata keys the result page reads; ``movie_time_ps`` is a per-MODEL list."""
    frames = int(summary.get("movie_frames") or 0)
    try:
        times = [float(value) for value in (summary.get("frame_times_ps") or [])]
    except (TypeError, ValueError):
        times = []
    if not all(math.isfinite(value) for value in times):
        times = []
    return {
        "movie_frames": frames,
        "movie_stride": int(summary.get("movie_stride") or 1),
        "movie_desolvated": bool(summary.get("desolvated")),
        "movie_aligned": bool(summary.get("aligned")),
        "movie_time_ps": times if (summary.get("written") and frames and len(times) == frames) else [],
    }


def _empty_movie_summary(warnings: list[str]) -> dict[str, Any]:
    """Neutral movie result used whenever the optional movie cannot be produced."""
    return {
        "written": False, "movie_frames": 0, "total_source_frames": 0, "movie_stride": 1,
        "frame_indices": [], "frame_times_ps": [], "atom_count": 0, "desolvated": False,
        "aligned": False, "conect_count": 0, "size_bytes": 0,
        "warnings": warnings,
    }


def _first_existing_file(candidates: Sequence[Path]) -> Path | None:
    """First readable candidate; callers run this inside the movie guard because
    ``Path.is_file`` can raise ``PermissionError`` on an unreadable parent."""
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def _remove_movie_path(path: Path) -> bool:
    """Best-effort removal, including files left unreadable by an earlier attempt."""
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        try:
            os.chmod(path, 0o600)
            path.unlink(missing_ok=True)
            return True
        except OSError:
            return False


def _discard_movie_target(output_dir: Path, warnings: list[str]) -> None:
    """Drop a movie left by an earlier attempt before this run decides anything.

    The uploader publishes ``result.json`` last and treats every file under
    ``output_dir`` as part of the result: a stale movie is either uploaded without
    a reference or, when unreadable, blocks the whole MD result.
    """
    target = Path(output_dir) / "artifacts" / "trajectory_movie.pdb"
    if not _remove_movie_path(target):
        warnings.append(f"stale trajectory movie could not be removed: {target}")


def _publish_movie(
    output_dir: Path, staging_target: Path, movie_summary: dict[str, Any], warnings: list[str],
) -> dict[str, str] | None:
    """Move a validated movie into ``artifacts`` and return its SHA-256 reference.

    The movie is exported outside ``artifacts`` so a hashing or permission failure
    can never leave an unreadable file behind for the output uploader, which
    publishes ``result.json`` last and would otherwise fail on that file.  Any
    failure also clears the final path so a movie from an earlier attempt cannot
    survive without a matching reference.
    """
    target = Path(output_dir) / "artifacts" / "trajectory_movie.pdb"
    if not _movie_file_ready(staging_target, movie_summary):
        _remove_movie_path(target)
        return None
    try:
        digest = sha256_file(staging_target)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_target, target)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - a broken/missing movie ref must not lose the MD result
        warnings.append(f"trajectory movie reference failed: {exc}")
        if not _remove_movie_path(target):
            warnings.append(f"failed trajectory movie could not be removed: {target}")
        return None
    return {"path": "artifacts/trajectory_movie.pdb", "sha256": digest}


def run_trajectory_movie_postprocess(
    topology_pdb: Path, trajectory_path: Path, out_dir: Path, *,
    ligand_resname: str = "LIG", ligand_template_sdf: Path | None = None,
    ligand_itp_candidates: Sequence[Path] = (), water_resname: str | None = None,
    run_params: dict[str, Any] | None = None,
    topology_gro_candidates: Sequence[Path] = (), superpose: bool = True,
) -> dict[str, Any]:
    """Export ``trajectory_movie.pdb`` isolated from the MD run.  Every movie
    setting is parsed inside this guard (run params -> env -> default) so a bad
    value only records a warning; a finished trajectory is never discarded."""
    warnings: list[str] = []
    try:
        try:
            import trajectory_movie
        except ImportError:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import trajectory_movie
        params = run_params if isinstance(run_params, dict) else {}
        movie_target = Path(out_dir) / "trajectory_movie.pdb"
        movie_target.unlink(missing_ok=True)  # drop a stale movie inside the guard
        ligand_itp = _first_existing_file(ligand_itp_candidates)
        topology_gro = _first_existing_file(topology_gro_candidates)

        def _pick(key: str, env: str, minimum: int, maximum: int | None = None) -> int | None:
            found = _strict_int(params.get(key), minimum=minimum, maximum=maximum, warnings=warnings, label=key)
            if found is not None:
                return found
            return _strict_int(os.environ.get(env), minimum=minimum, maximum=maximum, warnings=warnings, label=env)

        max_frames = _pick("movie_max_frames", "MD_MOVIE_MAX_FRAMES",
                           trajectory_movie.MIN_MOVIE_MAX_FRAMES, trajectory_movie.MAX_MOVIE_MAX_FRAMES)
        stride = _pick("movie_stride", "MD_MOVIE_STRIDE", 1)
        max_bytes = _pick("movie_max_bytes", "MD_MOVIE_MAX_BYTES", trajectory_movie.MIN_MOVIE_MAX_BYTES)
        cfg = trajectory_movie.TrajectoryMovieConfig(
            max_frames=trajectory_movie.DEFAULT_MOVIE_MAX_FRAMES if max_frames is None else max_frames,
            stride=stride, max_bytes=trajectory_movie.DEFAULT_MOVIE_MAX_BYTES if max_bytes is None else max_bytes,
            ligand_resname=ligand_resname, water_resname=water_resname, superpose=bool(superpose),
        )
        summary = trajectory_movie.export_desolvated_pdb_movie(
            topology_pdb, trajectory_path, movie_target,
            config=cfg, ligand_template_sdf=ligand_template_sdf, ligand_itp=ligand_itp, topology_gro=topology_gro,
        )
        summary["warnings"] = [*warnings, *(summary.get("warnings") or [])]
        if summary.get("written") is True and not _movie_file_ready(movie_target, summary):
            summary["written"] = False
            summary["warnings"].append("trajectory movie file missing or empty after export")
        return summary
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - never discard a finished MD trajectory
        print(f"[gromacs] trajectory movie skipped: {exc}", flush=True)
        return _empty_movie_summary([*warnings, f"trajectory movie failed: {exc}"])


def ensure_pdb_elements(
    pdb_path: Path,
    element_symbols: list[str],
    *,
    ligand_resname: str | None = None,
    ligand_elements: list[str] | None = None,
) -> bool:
    """Populate blank PDB columns 77-78 so MDAnalysis/ProLIF see atomic elements."""
    lines = pdb_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    atom_indices = [
        idx for idx, line in enumerate(lines)
        if line[:6].strip() in ("ATOM", "HETATM")
    ]
    if not atom_indices or len(atom_indices) != len(element_symbols):
        return False

    lig_map: dict[int, str] = {}
    if ligand_resname and ligand_elements:
        target = ligand_resname.strip().upper()
        lig_line_indices = [
            idx for idx in atom_indices
            if lines[idx][17:20].strip().upper() == target
        ]
        if len(lig_line_indices) == len(ligand_elements):
            lig_map = dict(zip(lig_line_indices, ligand_elements))

    changed = False
    for pos, line_idx in enumerate(atom_indices):
        line = lines[line_idx]
        existing = line[76:78].strip() if len(line) >= 78 else ""
        sym = (lig_map.get(line_idx) or element_symbols[pos] or "").strip()
        if not sym or sym.upper() == "VS":
            continue
        if not existing or line_idx in lig_map:
            padded = line.ljust(76)[:76]
            formatted_sym = (sym[0].upper() + sym[1:].lower()) if len(sym) > 1 else sym.upper()
            tail = line[78:] if len(line) > 78 else ""
            lines[line_idx] = f"{padded}{formatted_sym:>2}{tail}".rstrip()
            changed = True

    if changed:
        pdb_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _ligand_elements_from_sdf(template_sdf: Path | None) -> list[str] | None:
    if template_sdf is None or not Path(template_sdf).is_file():
        return None
    try:
        from rdkit import Chem
    except ImportError:
        return None
    mol = Chem.MolFromMolFile(str(template_sdf), removeHs=False, sanitize=False)
    if mol is None:
        return None
    return [atom.GetSymbol().strip() for atom in mol.GetAtoms()]


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
    ligand_sdf: Path | None = None,
    custom_itp: Path | None = None,
    custom_prm: Path | None = None,
    custom_gro: Path | None = None,
    custom_zip: Path | None = None,
    ligand_config: Any | None = None,
) -> dict[str, Any]:
    clean = work / "protein_clean.pdb"
    sanitize_pdb(protein, clean)

    progress(5, "pdb2gmx")
    run([GMX, "pdb2gmx", "-f", str(clean), "-o", "processed.gro", "-water", water_model,
         "-ff", force_field, "-ignh"], work)

    param_lig = None
    start_gro = "processed.gro"
    if any(item is not None for item in (ligand_sdf, custom_itp, custom_zip)):
        progress(10, "parameterize ligand")
        try:
            from ligand_parameterizer import (
                LigandPrepConfig,
                merge_gro_files,
                parameterize_ligand,
                patch_topol_top,
            )
        except ImportError:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from ligand_parameterizer import (
                LigandPrepConfig,
                merge_gro_files,
                parameterize_ligand,
                patch_topol_top,
            )

        prep_cfg = ligand_config if ligand_config is not None else LigandPrepConfig()
        param_lig = parameterize_ligand(
            work / "ligand_prep",
            config=prep_cfg,
            ligand_sdf=ligand_sdf,
            custom_itp=custom_itp,
            custom_prm=custom_prm,
            custom_gro=custom_gro,
            custom_zip=custom_zip,
        )
        atomtypes_name, ligand_itp_name, posre_name = _stage_ligand_topology_into_work(work, param_lig)
        merge_gro_files(work / "processed.gro", param_lig.ligand_gro, work / "complex.gro")
        patch_topol_top(
            work / "topol.top",
            ligand_itp_name=ligand_itp_name,
            moleculetype_name=param_lig.moleculetype or param_lig.ligand_resname,
            atomtypes_itp_name=atomtypes_name,
            posre_itp_name=posre_name,
            ligand_count=1,
        )
        start_gro = "complex.gro"

    progress(15, "editconf")
    run([GMX, "editconf", "-f", start_gro, "-o", "boxed.gro", "-c", "-d", str(box_distance), "-bt", "cubic"], work)
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

    progress(86, "convert trajectory")
    xtc_path, gro_path = center_pbc_trajectory(work)
    # GROMACS trjconv 不直接写 DCD；用 mdtraj 把 XTC 转为标准 DCD。
    import mdtraj as _mdtraj

    _traj = _mdtraj.load(str(xtc_path), top=str(gro_path))
    _traj.save_dcd(str(work / "trajectory.dcd"))
    run([GMX, "trjconv", "-s", "md.tpr", "-f", gro_path.name, "-o", "topology.pdb"], work, stdin_text="0\n")
    _elements = [
        str(getattr(getattr(atom, "element", None), "symbol", "") or "")
        for atom in _traj.topology.atoms
    ]
    ensure_pdb_elements(
        work / "topology.pdb",
        _elements,
        ligand_resname=param_lig.ligand_resname if param_lig is not None else None,
        ligand_elements=_ligand_elements_from_sdf(param_lig.template_sdf if param_lig is not None else None),
    )
    return {
        "duration_ns": nsteps * dt / 1000.0,
        "trajectory_xtc": str(xtc_path),
        "trajectory_gro": str(gro_path),
        "ligand": param_lig,
    }


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
    slots = collect_input_slots(input_dir, params)
    run_params = params.get("params") or params.get("parameters") or {}
    force_field = str(run_params.get("force_field") or "amber99sb-ildn")
    water_model = str(run_params.get("water_model") or "tip3p")
    box_distance = float(run_params.get("box_distance") or 1.0)
    nsteps = int(run_params.get("nsteps") or 2500)
    dt = float(run_params.get("dt") or 0.002)
    temperature = float(run_params.get("temperature") or 300.0)

    ligand_mode = str(run_params.get("ligand_mode") or "auto")
    ligand_resname = str(run_params.get("ligand_resname") or "LIG").strip().upper() or "LIG"
    charge_method = str(run_params.get("charge_method") or "bcc").strip().lower() or "bcc"
    raw_charge = run_params.get("net_charge")
    net_charge = int(raw_charge) if raw_charge not in (None, "") else None
    analysis_stride = max(1, int(run_params.get("analysis_stride") or 1))
    water_resname = str(run_params.get("water_resname") or "").strip() or None

    protein = pick_protein(slots, input_dir)
    ligand_inputs = pick_ligand_inputs(slots, input_dir, protein)

    ligand_config = None
    if any(ligand_inputs.values()):
        try:
            from ligand_parameterizer import LigandPrepConfig
        except ImportError:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from ligand_parameterizer import LigandPrepConfig
        ligand_config = LigandPrepConfig(
            mode=ligand_mode,
            ligand_resname=ligand_resname,
            net_charge=net_charge,
            charge_method=charge_method,
            amber_root=os.environ.get("AMBER_ROOT", "/opt/amber"),
        )

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
        ligand_sdf=ligand_inputs["ligand_sdf"],
        custom_itp=ligand_inputs["custom_itp"],
        custom_prm=ligand_inputs["custom_prm"],
        custom_gro=ligand_inputs["custom_gro"],
        custom_zip=ligand_inputs["custom_zip"],
        ligand_config=ligand_config,
    )

    out = output_dir / "artifacts"
    shutil.copyfile(work / "topology.pdb", out / "topology.pdb")
    shutil.copyfile(work / "trajectory.dcd", out / "trajectory.dcd")
    xtc_path = Path(info.get("trajectory_xtc") or (work / "md.xtc"))
    traj_rel_name = xtc_path.name if xtc_path.parent == work else "md.xtc"
    write_analysis_csv(work, out / "analysis.csv", trajectory_name=traj_rel_name)
    rmsf_written = write_rmsf_csv(work, out / "rmsf.csv", work / "topology.pdb", trajectory_name=traj_rel_name)

    progress(94, "interaction analysis")
    param_lig = info.get("ligand")
    effective_resname = param_lig.ligand_resname if param_lig is not None else ligand_resname
    interaction_summary = run_interactions_postprocess(
        work / "topology.pdb",
        xtc_path,
        out,
        ligand_resname=effective_resname,
        ligand_template_sdf=param_lig.template_sdf if param_lig is not None else None,
        stride=analysis_stride,
        water_resname=water_resname,
    )

    progress(96, "trajectory movie")
    # Reuse only the ITP this task actually produced; never a stale file left in work/.
    # File probes stay inside run_trajectory_movie_postprocess so a permission error
    # cannot abort a finished MD result before result.json is written.
    ligand_itp_candidates: list[Path] = []
    if param_lig is not None:
        ligand_itp_candidates = [work / "ligand.itp", Path(getattr(param_lig, "ligand_itp", "") or "")]
    gro_path = Path(info.get("trajectory_gro") or (work / "md.gro"))
    movie_warnings: list[str] = []
    movie_summary = _empty_movie_summary(movie_warnings)
    movie_ref: dict[str, str] | None = None
    # A retry can find the previous attempt's movie under artifacts. Drop it before
    # any early exit (e.g. a failing mkdtemp) so an unreferenced or unreadable file
    # can never block the uploader from publishing this run's result.json.
    _discard_movie_target(output_dir, movie_warnings)
    # Export outside output_dir: a movie that cannot be hashed/moved must leave
    # nothing behind that the output uploader would try (and fail) to upload.
    try:
        staging_dir = Path(tempfile.mkdtemp(prefix=".trajectory-movie-", dir=str(output_dir.parent)))
    except OSError as exc:
        movie_warnings.append(f"trajectory movie failed: {exc}")
    else:
        try:
            movie_summary = run_trajectory_movie_postprocess(
                work / "topology.pdb",
                xtc_path,
                staging_dir,
                ligand_resname=effective_resname,
                ligand_template_sdf=param_lig.template_sdf if param_lig is not None else None,
                ligand_itp_candidates=ligand_itp_candidates,
                water_resname=water_resname,
                run_params=run_params,
                topology_gro_candidates=[gro_path],
            )
            movie_warnings = list(movie_summary.get("warnings") or [])
            movie_ref = _publish_movie(
                output_dir, staging_dir / "trajectory_movie.pdb", movie_summary, movie_warnings,
            )
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
    effective_movie_summary = (
        movie_summary
        if movie_ref is not None
        else {
            **movie_summary,
            "written": False,
            "movie_frames": 0,
            "movie_stride": 1,
            "desolvated": False,
            "aligned": False,
            "frame_times_ps": [],
        }
    )

    metadata = {
        "source_task_id": args.task_id,
        "force_field": force_field,
        "duration_ns": info["duration_ns"],
        # Matches mdp_text() nstxout-compressed = 500 output frequency (frame 0 + nsteps/500).
        "frames": nsteps // 500 + 1,
        "temperature_k": temperature,
        "engine": "GROMACS 2024.1",
        "water_model": water_model,
        "device": args.device,
        "complex_mode": bool(param_lig is not None),
        "ligand_mode": param_lig.mode if param_lig is not None else "protein_only",
        "ligand_resname": effective_resname if param_lig is not None else None,
        "interaction_mode": interaction_summary.get("mode"),
        "interaction_engine": interaction_summary.get("engine"),
        **_movie_metadata_fields(effective_movie_summary),
        **({"movie_warnings": movie_warnings} if movie_warnings else {}),
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
        "ligand_mode": metadata["ligand_mode"],
        "ligand_resname": metadata["ligand_resname"],
        "interaction_mode": interaction_summary.get("mode"),
        "interaction_engine": interaction_summary.get("engine"),
        "contacts_count": int((interaction_summary.get("summary") or {}).get("total_interactions") or 0),
        "movie_frames": metadata["movie_frames"],
    }
    write_json(out / "report.json", report)

    trajectory_files: dict[str, dict[str, str]] = {
        "topology_pdb": file_ref(output_dir, "artifacts/topology.pdb"),
        "trajectory_dcd": file_ref(output_dir, "artifacts/trajectory.dcd"),
        "analysis_csv": file_ref(output_dir, "artifacts/analysis.csv"),
        "metadata_json": file_ref(output_dir, "artifacts/metadata.json"),
        **({"rmsf_csv": file_ref(output_dir, "artifacts/rmsf.csv")} if rmsf_written else {}),
        **({"contacts_csv": file_ref(output_dir, "artifacts/contacts.csv")} if (out / "contacts.csv").is_file() else {}),
        **({"interactions_json": file_ref(output_dir, "artifacts/interactions.json")}
           if (out / "interactions.json").is_file() else {}),
        **({"trajectory_movie_pdb": movie_ref} if movie_ref is not None else {}),
    }

    result = {
        "result_version": "aidd.platform/result",
        "artifacts": {
            "trajectory": {
                "type": "md_trajectory@1",
                "files": trajectory_files,
                "metadata": {"source_task_id": args.task_id},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, "artifacts/report.json")},
                "metadata": {"source_task_id": args.task_id},
            },
        },
        "metrics": {
            "duration_ns": info["duration_ns"],
            "nsteps": nsteps,
            "temperature_k": temperature,
            "contacts_count": report["contacts_count"],
        },
    }
    write_json(output_dir / "result.json", result)
    progress(100, "done")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
