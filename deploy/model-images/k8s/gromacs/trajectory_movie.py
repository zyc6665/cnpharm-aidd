#!/usr/bin/env python3
"""Desolvated trajectory movie export for GROMACS MD results (clean-room, offline).

Turns a trajectory into a compact, water/ion-free multi-model PDB for Mol*: drop
solvent/ions (never the ligand), sample bounded frames under a byte budget, keep
fixed PDB columns, and write one CONECT block after the last ENDMDL. mdtraj/rdkit
load lazily; only the standard library is required at import time.
"""

from __future__ import annotations

import math
import numbers
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

try:
    from trajectory_movie_pdb import (
        ION_RESNAMES,
        PDB_MAX_ATOMS,
        WATER_RESNAMES,
        AtomTemplate,
        MovieAtomLayout,
        _assign_chain,
        _element_of,
        _format_atom_name,
        _is_ion,
        _is_ligand,
        _is_water,
        _itp_bond_pairs,
        _itp_edge_set,
        _ligand_bond_pairs,
        _pdb_atom_line,
        _render_movie,
        _sdf_template,
        _unique_atom_name,
        build_ligand_conect_lines,
        normalize_movie_templates,
        parse_pdb_atom_templates,
        select_desolvated_indices,
    )
except ImportError:
    _SELF_DIR = str(Path(__file__).resolve().parent)
    if _SELF_DIR not in sys.path:
        sys.path.insert(0, _SELF_DIR)
    from trajectory_movie_pdb import (
        ION_RESNAMES,
        PDB_MAX_ATOMS,
        WATER_RESNAMES,
        AtomTemplate,
        MovieAtomLayout,
        _assign_chain,
        _element_of,
        _format_atom_name,
        _is_ion,
        _is_ligand,
        _is_water,
        _itp_bond_pairs,
        _itp_edge_set,
        _ligand_bond_pairs,
        _pdb_atom_line,
        _render_movie,
        _sdf_template,
        _unique_atom_name,
        build_ligand_conect_lines,
        normalize_movie_templates,
        parse_pdb_atom_templates,
        select_desolvated_indices,
    )

__all__ = [
    "AtomTemplate",
    "DEFAULT_MOVIE_MAX_BYTES",
    "DEFAULT_MOVIE_MAX_FRAMES",
    "ION_RESNAMES",
    "MAX_MOVIE_MAX_FRAMES",
    "MIN_MOVIE_MAX_BYTES",
    "MIN_MOVIE_MAX_FRAMES",
    "MovieAtomLayout",
    "PDB_MAX_ATOMS",
    "TrajectoryMovieConfig",
    "WATER_RESNAMES",
    "_assign_chain",
    "_format_atom_name",
    "_itp_bond_pairs",
    "_itp_edge_set",
    "_ligand_bond_pairs",
    "_pdb_atom_line",
    "_render_movie",
    "_sdf_template",
    "_unique_atom_name",
    "build_ligand_conect_lines",
    "export_desolvated_pdb_movie",
    "normalize_movie_templates",
    "parse_pdb_atom_templates",
    "select_desolvated_indices",
    "select_frame_indices",
]

DEFAULT_MOVIE_MAX_FRAMES = 60
MIN_MOVIE_MAX_FRAMES = 1
MAX_MOVIE_MAX_FRAMES = 300
DEFAULT_MOVIE_MAX_BYTES = 25 * 1024 * 1024
MIN_MOVIE_MAX_BYTES = 1024
_ATOM_LINE_BYTES = 82
_MODEL_OVERHEAD_BYTES = 32       # per-frame MODEL / TER / ENDMDL lines
_GLOBAL_OVERHEAD_BYTES = 512     # global REMARK + unique CONECT + END lines


@dataclass(frozen=True)
class TrajectoryMovieConfig:
    """Rendering budget; keeps first/last frame so the movie never loses endpoints."""
    max_frames: int = DEFAULT_MOVIE_MAX_FRAMES
    stride: int | None = None
    max_bytes: int = DEFAULT_MOVIE_MAX_BYTES
    ligand_resname: str | None = None
    water_resname: str | None = None
    strip_ions: bool = True
    superpose: bool = True


def select_frame_indices(
    total_frames: int, *, stride: int | None = None, max_frames: int = DEFAULT_MOVIE_MAX_FRAMES,
) -> list[int]:
    """Pick increasing frame indices keeping both ends; total>=2 stays >= 2 frames."""
    total = int(total_frames or 0)
    if total <= 0:
        return []
    if total == 1:
        return [0]
    requested = DEFAULT_MOVIE_MAX_FRAMES if max_frames is None else int(max_frames)
    limit = max(MIN_MOVIE_MAX_FRAMES, min(MAX_MOVIE_MAX_FRAMES, requested))
    if total >= 2:
        limit = max(2, limit)
    if stride is not None:
        step = max(1, int(stride))
        candidates = list(range(0, total, step))
        if candidates[-1] != total - 1:
            candidates.append(total - 1)
    else:
        candidates = list(range(total))
    return candidates if len(candidates) <= limit else _uniform_subsample(candidates, limit)


def _uniform_subsample(values: Sequence[int], limit: int) -> list[int]:
    count = len(values)
    limit = max(1, min(int(limit), count))
    if limit == 1:
        return [values[0]]
    positions: list[int] = []
    for slot in range(limit):
        position = int(round(slot * (count - 1) / (limit - 1)))
        if positions and position <= positions[-1]:
            position = positions[-1] + 1
        if position >= count:
            break
        positions.append(position)
    if positions[-1] != count - 1:
        if len(positions) < limit:
            positions.append(count - 1)
        else:
            positions[-1] = count - 1
    return [values[position] for position in positions]


def _apply_byte_budget(
    frame_indices: Sequence[int], atom_count: int, max_bytes: int | None, warnings: list[str],
    *, min_frames: int = 1,
) -> list[int]:
    """Rough cap so frames fit max_bytes; never below ``min_frames`` because the
    exporter re-measures the real UTF-8 size before committing a decision."""
    if max_bytes is None or int(max_bytes) <= 0 or atom_count <= 0:
        return list(frame_indices)
    per_frame = atom_count * _ATOM_LINE_BYTES + _MODEL_OVERHEAD_BYTES
    budget = max(0, int(max_bytes) - _GLOBAL_OVERHEAD_BYTES)
    allowed = max(int(min_frames), budget // per_frame)
    if len(frame_indices) <= allowed:
        return list(frame_indices)
    reduced = _uniform_subsample(frame_indices, min(allowed, len(frame_indices)))
    warnings.append(
        f"movie byte budget reduced frames from {len(frame_indices)} to {len(reduced)} "
        f"(~{per_frame} bytes/frame, limit {int(max_bytes)} bytes)"
    )
    return reduced


def _default_trajectory_loader(topology_pdb: Path, trajectory_path: Path, topology_gro: Path | None = None) -> Any:
    import mdtraj as md  # lazy: only needed in the model image
    return md.load(str(trajectory_path), top=str(topology_gro or topology_pdb))


def _frame_box_lengths(vectors_row: Any) -> list[float]:
    """Per-frame box edge lengths from a row of unitcell vectors, or ``[]``."""
    try:
        lengths = [math.sqrt(sum(float(value) ** 2 for value in row)) for row in vectors_row]
    except (TypeError, ValueError):
        return []
    return lengths if lengths and all(length > 0 for length in lengths) else []


def _axis_span(first: Sequence[float], second: Sequence[float]) -> float:
    return max(abs(first[0] - second[0]), abs(first[1] - second[1]), abs(first[2] - second[2]))


def _imaging_bonds(
    templates: Sequence[AtomTemplate] | None, ligand_resname: str | None, ligand_itp: Path | None,
) -> tuple[list[int] | None, set[tuple[int, int]] | None]:
    """Return (heavy indices, bonded/same-chain heavy pairs) for PBC split checks."""
    if not templates:
        return None, None
    heavy = [i for i, atom in enumerate(templates) if _element_of(atom) != "H"]
    groups: list[tuple[tuple[int, str], list[int]]] = []
    for i, atom in enumerate(templates):
        marker = (atom.segment_index, atom.chain_id)
        if not groups or groups[-1][0] != marker:
            groups.append((marker, []))
        if _element_of(atom) != "H":
            groups[-1][1].append(i)
    edges = {pair for _, group in groups for pair in zip(group, group[1:])}
    for (marker_a, group_a), (marker_b, group_b) in zip(groups, groups[1:]):
        if marker_a == marker_b and group_a and group_b:
            edges.add((group_a[-1], group_b[0]))
    edges.update(_ligand_bond_pairs(templates, ligand_resname, ligand_itp))
    return heavy, edges


def _bond_index_pair(bond: Any) -> tuple[int, int] | None:
    """Normalize an MDTraj ``Bond`` or a plain ``(a, b)`` pair to atom indices."""
    first = getattr(bond, "atom1", None)
    second = getattr(bond, "atom2", None)
    if first is None or second is None:
        try:
            first, second = bond[0], bond[1]
        except (TypeError, KeyError, IndexError):
            return None
    first = getattr(first, "index", first)
    second = getattr(second, "index", second)
    try:
        return int(first), int(second)
    except (TypeError, ValueError):
        return None


def _topology_bond_pairs(topology: Any) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for bond in getattr(topology, "bonds", None) or []:
        pair = _bond_index_pair(bond)
        if pair is not None:
            pairs.add((min(pair), max(pair)))
    return pairs


def _inject_ligand_topology_bonds(
    trajectory: Any, templates: Sequence[AtomTemplate] | None,
    ligand_resname: str | None, ligand_itp: Path | None,
) -> None:
    """Add trusted ligand bonds to a GRO-loaded topology before ``image_molecules``,
    so the ligand is imaged as one molecule instead of shifting its atoms apart.
    Best-effort: a topology without ``add_bond`` (or a fake one) is left untouched."""
    pairs = _ligand_bond_pairs(templates, ligand_resname, ligand_itp)
    topology = getattr(trajectory, "topology", None)
    if not pairs or topology is None:
        return
    add_bond = getattr(topology, "add_bond", None)
    atoms = list(getattr(topology, "atoms", []) or [])
    if not callable(add_bond) or len(atoms) < max(max(pair) for pair in pairs) + 1:
        return
    existing = _topology_bond_pairs(topology)
    for first, second in pairs:
        if (first, second) in existing:
            continue
        try:
            add_bond(atoms[first], atoms[second])
        except Exception:  # noqa: BLE001 - topology injection is best-effort
            return
        existing.add((first, second))


def _needs_imaging(
    trajectory: Any, *, templates: Sequence[AtomTemplate] | None = None,
    ligand_resname: str | None = None, ligand_itp: Path | None = None,
) -> bool:
    """Detect non-finite/far coords, bonded atoms split across a box, or per-frame PBC
    wraps. Each frame uses its *own* box vectors so NPT variable boxes hold."""
    xyz = getattr(trajectory, "xyz", None)
    if xyz is None:
        return False
    vectors = getattr(trajectory, "unitcell_vectors", None)
    available = len(vectors) if vectors is not None else 0
    heavy, edges = _imaging_bonds(templates, ligand_resname, ligand_itp)
    previous: list[tuple[float, float, float]] | None = None
    try:
        for frame in range(len(xyz)):
            points = [tuple(float(value) for value in position) for position in xyz[frame]]
            if any(not math.isfinite(value) for point in points for value in point):
                return True
            lengths = _frame_box_lengths(vectors[frame] if frame < available else vectors[-1]) if available else []
            if lengths:
                span = max(lengths)
                half = 0.5 * min(lengths)
                if any(abs(value) > span * 1.5 for point in points for value in point):
                    return True
                if edges is not None:
                    if any(_axis_span(points[a], points[b]) > half for a, b in edges):
                        return True
                elif any(_axis_span(points[i], points[i + 1]) > half for i in range(len(points) - 1)):
                    return True
                if previous is not None:
                    indices = heavy if heavy is not None else range(len(points))
                    if any(_axis_span(previous[i], points[i]) > half for i in indices):
                        return True
            previous = points
    except (TypeError, ValueError, IndexError):
        return False
    return False


def _alignment_indices(
    atoms: Sequence[AtomTemplate], *, ligand_resname: str | None = None,
    water_resname: str | None = None, strip_ions: bool = True,
) -> list[int]:
    """Protein CA atoms, else protein heavy atoms; never ligand/solvent/ions (even a
    retained calcium ``CA`` when strip_ions is False must not be an anchor)."""
    ligand = (ligand_resname or "").strip().upper()
    water_names = set(WATER_RESNAMES)
    if water_resname and water_resname.strip():
        water_names.add(water_resname.strip().upper())
    protein = [p for p, atom in enumerate(atoms) if atom.record.strip().upper() == "ATOM"
               and not _is_ligand(atom, ligand) and not _is_water(atom, water_names) and not _is_ion(atom)]
    calphas = [p for p in protein if atoms[p].atom_name.strip().upper() == "CA"]
    if len(calphas) >= 3:
        return calphas
    heavy = [p for p in protein if _element_of(atoms[p]) != "H"]
    return heavy if len(heavy) >= 3 else []


def _frames_to_angstrom(xyz: Any, frame_count: int, atom_count: int) -> list[list[tuple[float, float, float]]]:
    return [[(float(xyz[f][p][0]) * 10.0, float(xyz[f][p][1]) * 10.0, float(xyz[f][p][2]) * 10.0)
             for p in range(atom_count)] for f in range(frame_count)]


def _strict_frame_times(times: Any, frame_indices: Sequence[int]) -> list[float]:
    """Per-frame times in ps, or ``[]`` when any sampled frame lacks a real finite
    time (never fabricate ``0.0``/``1.0`` to fill the column). Accepts NumPy
    ``floating``/``integer`` scalars (e.g. MDTraj XTC ``time`` is ``float32``)."""
    if times is None or not frame_indices:
        return []
    try:
        if len(times) < max(frame_indices) + 1:
            return []
        values = [times[index] for index in frame_indices]
        if any(isinstance(v, bool) or not isinstance(v, numbers.Real) or not math.isfinite(float(v)) for v in values):
            return []
        return [float(v) for v in values]
    except (TypeError, ValueError, IndexError, OverflowError):
        return []


def _skipped_movie(warnings: list[str], *, total_frames: int = 0, desolvated: bool = False) -> dict[str, Any]:
    return {"written": False, "movie_frames": 0, "total_source_frames": total_frames, "movie_stride": 1,
            "frame_indices": [], "frame_times_ps": [], "atom_count": 0, "desolvated": desolvated,
            "aligned": False, "conect_count": 0, "size_bytes": 0, "warnings": list(warnings)}


def _coords_valid(frames_angstrom) -> bool:
    """Reject non-finite values and anything that does not fit ``%8.3f`` (e.g. a
    9-char ``-1000.000``), so coordinate columns never overflow."""
    for frame in frames_angstrom:
        for triple in frame:
            for value in triple:
                if not math.isfinite(value) or len(f"{float(value):8.3f}") != 8:
                    return False
    return True


_GRO_ATOM_ALIASES = {
    "H1": "H",
    "1H": "H",
    "HN": "H",
    "OC1": "O",
    "OT1": "O",
    "O1": "O",
    "OC2": "OXT",
    "OT2": "OXT",
    "O2": "OXT",
}

# MDTraj 1.10.3 applies its terminal/ILE atom aliases through the residue alias table,
# i.e. only to amino-acid residues. Include the common GROMACS/Amber protonation and
# disulfide names so those residues keep the same alias behaviour.
_PROTEIN_RESNAMES = frozenset({
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "HID", "HIE", "HIP", "HSD", "HSE", "HSP", "CYX", "CYM", "ASH", "GLH", "LYN",
})


def _canonical_gro_atom_name(atom_name: str, resname: str = "") -> str:
    """Normalize MDTraj 1.10.3 GRO/pdbNames.xml aliases for protein residues only.

    H1/1H/HN->H, OC1/OT1/O1->O, OC2/OT2/O2->OXT and ILE CD->CD1 are amino-acid
    aliases. Applying them to ligands would let a swapped same-element pair such as
    ``O``/``O1`` pass validation and bind coordinates to the wrong atom name.
    """
    name = (atom_name or "").strip().upper()
    res = (resname or "").strip().upper()
    if res not in _PROTEIN_RESNAMES:
        return name
    if res == "ILE" and name == "CD":
        return "CD1"
    return _GRO_ATOM_ALIASES.get(name, name)


def _validate_trajectory_topology(
    trajectory: Any, templates: Sequence[AtomTemplate], keep_indices: Sequence[int],
    *, using_gro: bool = False,
) -> None:
    """Raise when the loaded trajectory no longer matches the altLoc-de-duped template.
    Checks total atom count on the full system (ignoring stripped virtual-site/water
    element labels) and kept solute order. Under a GRO topology, MDTraj lacks an
    element column (inferring e.g. ``CL1`` as ``C`` and a digit-prefixed terminal
    ``1H`` as virtual-site ``VS``) and canonicalizes GROMACS terminal/ILE names, so
    the canonical name comparison is the authoritative check; a second element
    comparison would only re-read the same inferred name and reject valid atoms."""
    traj_atoms = list(getattr(getattr(trajectory, "topology", None), "atoms", []) or [])
    if not traj_atoms:
        return
    traj_n_atoms = getattr(trajectory, "n_atoms", None)
    expected = len(templates)
    if traj_n_atoms is not None and int(traj_n_atoms) != expected:
        raise ValueError(f"trajectory n_atoms ({traj_n_atoms}) != topology PDB atoms ({expected})")
    if len(traj_atoms) != expected:
        return
    kept = {int(index) for index in keep_indices}
    for index, (template, traj_atom) in enumerate(zip(templates, traj_atoms)):
        if index not in kept:
            continue
        if using_gro:
            traj_raw = (getattr(traj_atom, "name", "") or "").strip().upper()
            traj_res = (getattr(getattr(traj_atom, "residue", None), "name", "") or template.resname)
            if traj_raw:
                if (
                    _canonical_gro_atom_name(traj_raw, traj_res)
                    != _canonical_gro_atom_name(template.atom_name, template.resname)
                ):
                    raise ValueError("GRO trajectory atom order differs from topology PDB; refusing to render")
                continue
        symbol = (getattr(getattr(traj_atom, "element", None), "symbol", "") or "").strip().upper()
        expected_el = _element_of(template)
        gro_initial = template.atom_name.strip()[:1].upper()
        if symbol and symbol != expected_el and not (using_gro and symbol == gro_initial):
            raise ValueError("trajectory element order differs from topology PDB; refusing to render")


def _movie_remarks(
    total_frames: int, frame_indices: Sequence[int], atom_count: int, desolvated: bool, aligned: bool,
):
    """Return (effective_stride, remark lines) so header and result dict stay in sync."""
    stride = max(1, int(round((total_frames - 1) / (len(frame_indices) - 1)))) if len(frame_indices) >= 2 else 1
    remarks = [
        "AIDD GROMACS desolvated trajectory movie",
        f"source frames {total_frames} selected {len(frame_indices)} stride {stride}",
        f"atoms {atom_count} (desolvated: {'yes' if desolvated else 'no'}, aligned: {'yes' if aligned else 'no'})",
        "coordinates in Angstrom; the CONECT block applies to every MODEL",
    ]
    return stride, remarks


def export_desolvated_pdb_movie(
    topology_pdb: Path, trajectory_path: Path, output_pdb: Path, *,
    config: TrajectoryMovieConfig | None = None, ligand_template_sdf: Path | None = None,
    ligand_itp: Path | None = None, topology_gro: Path | None = None,
    trajectory_loader: Callable[..., Any] | None = None, warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Export a desolvated, PBC-fixed, optionally superposed PDB movie.
    ``trajectory_loader`` is injectable so unit tests drive the path without MDTraj."""
    cfg = config or TrajectoryMovieConfig()
    warnings = warnings if warnings is not None else []
    topology, trajectory_file, target = Path(topology_pdb), Path(trajectory_path), Path(output_pdb)
    if not topology.is_file():
        raise FileNotFoundError(f"topology PDB not found: {topology}")
    if not trajectory_file.is_file():
        raise FileNotFoundError(f"trajectory not found: {trajectory_file}")
    templates = parse_pdb_atom_templates(topology)
    if not templates:
        raise ValueError(f"topology PDB has no ATOM/HETATM records: {topology}")
    ligand_resname = (cfg.ligand_resname or "").strip().upper()
    keep_indices = select_desolvated_indices(
        templates, ligand_resname=ligand_resname or None,
        water_resname=cfg.water_resname, strip_ions=cfg.strip_ions,
    )
    kept_templates = [templates[position] for position in keep_indices]
    desolvated = len(keep_indices) < len(templates)
    if not kept_templates:
        warnings.append("desolvation removed every atom; movie not written")
        return _skipped_movie(warnings, desolvated=True)
    if len(kept_templates) > PDB_MAX_ATOMS:
        warnings.append(f"movie has {len(kept_templates)} atoms (> {PDB_MAX_ATOMS}); movie not written (PDB serial limit)")
        return _skipped_movie(warnings, desolvated=desolvated)
    loader = trajectory_loader or (lambda top, traj: _default_trajectory_loader(top, traj, topology_gro))
    trajectory = loader(topology, trajectory_file)
    total_frames = int(getattr(trajectory, "n_frames", 0) or 0)
    if total_frames <= 0:
        raise ValueError("trajectory contains no frames")
    _validate_trajectory_topology(trajectory, templates, keep_indices, using_gro=bool(topology_gro))
    frame_indices = select_frame_indices(total_frames, stride=cfg.stride, max_frames=cfg.max_frames)
    frame_indices = _apply_byte_budget(
        frame_indices, len(kept_templates), cfg.max_bytes, warnings,
        min_frames=2 if total_frames >= 2 else 1,
    )
    if not frame_indices:
        raise ValueError("no frames selected for the movie")
    sampled = trajectory.slice(frame_indices, copy=True).atom_slice(keep_indices)
    if _needs_imaging(sampled, templates=kept_templates, ligand_resname=ligand_resname or None, ligand_itp=ligand_itp):
        _inject_ligand_topology_bonds(sampled, kept_templates, ligand_resname or None, ligand_itp)
        try:
            sampled.image_molecules(inplace=True)
        except Exception as exc:  # noqa: BLE001 - a broken image must not kill the movie
            warnings.append(f"PBC imaging failed: {exc}")
    layout = normalize_movie_templates(kept_templates, ligand_resname=ligand_resname or None)
    if layout is None:
        warnings.append("ligand atom names or chain ids exhausted; movie not written")
        return _skipped_movie(warnings, total_frames=total_frames, desolvated=desolvated)
    aligned = False
    align_indices = _alignment_indices(
        [entry.atom for entry in layout], ligand_resname=ligand_resname or None,
        water_resname=cfg.water_resname, strip_ions=cfg.strip_ions,
    )
    if cfg.superpose and align_indices:
        try:
            sampled.superpose(sampled, frame=0, atom_indices=align_indices)
            aligned = True
        except Exception as exc:  # noqa: BLE001 - alignment is cosmetic
            warnings.append(f"structure superposition failed: {exc}")
    elif not align_indices:
        warnings.append("fewer than three protein heavy atoms; movie is not superposed")
    xyz = getattr(sampled, "xyz", None)
    if xyz is None:
        raise ValueError("trajectory exposes no coordinates (xyz)")
    movie_frames = min(int(getattr(sampled, "n_frames", len(frame_indices)) or 0), len(xyz))
    frames_angstrom = _frames_to_angstrom(xyz, movie_frames, len(kept_templates))
    frame_indices = frame_indices[:movie_frames]
    times = getattr(trajectory, "time", None)
    frame_times = _strict_frame_times(times, frame_indices)
    if not _coords_valid(frames_angstrom):
        warnings.append("movie coordinates are non-finite or exceed the %8.3f column; movie not written")
        return _skipped_movie(warnings, total_frames=total_frames, desolvated=desolvated)
    conect_lines = build_ligand_conect_lines(
        kept_templates, ligand_resname=ligand_resname or None,
        ligand_template_sdf=ligand_template_sdf, ligand_itp=ligand_itp, warnings=warnings,
    )
    max_bytes = cfg.max_bytes
    budget = int(max_bytes) if max_bytes else 0

    def _apply_subset(keep: Sequence[int]):
        nonlocal frames_angstrom, frame_indices, frame_times, movie_frames
        frames_angstrom = [frames_angstrom[idx] for idx in keep]
        frame_indices = [frame_indices[idx] for idx in keep]
        frame_times = _strict_frame_times(times, frame_indices)
        movie_frames = len(frames_angstrom)
        stride, remark_lines = _movie_remarks(
            total_frames, frame_indices, len(layout), desolvated, aligned,
        )
        return stride, remark_lines, _render_movie(layout, frames_angstrom, remark_lines, conect_lines)

    effective_stride, remarks, text = _apply_subset(list(range(len(frames_angstrom))))
    if budget > 0 and len(text.encode("utf-8")) > budget and len(frames_angstrom) > 2:
        # Charge real CONECT and fixed header/END overhead before sizing remaining frames.
        measured = len(text.encode("utf-8"))
        fixed_bytes = len(_render_movie(layout, [], remarks, conect_lines).encode("utf-8"))
        per_frame = max(1, math.ceil((measured - fixed_bytes) / len(frames_angstrom)))
        allowed = max(2, (budget - fixed_bytes) // per_frame)
        effective_stride, remarks, text = _apply_subset(
            _uniform_subsample(list(range(len(frames_angstrom))), min(allowed, len(frames_angstrom)))
        )
        warnings.append(f"movie byte budget tightened frames to {movie_frames} after measuring real size")
    if budget > 0 and len(text.encode("utf-8")) > budget and len(frames_angstrom) > 2:
        # Stubborn oversized renders still get one explicit first/last two-frame try.
        effective_stride, remarks, text = _apply_subset([0, len(frames_angstrom) - 1])
        warnings.append("movie byte budget tightened frames to 2 (first and last) after measuring real size")
    if budget > 0 and len(text.encode("utf-8")) > budget:
        if total_frames >= 2 and len(frames_angstrom) <= 2:
            warnings.append("byte budget cannot fit two frames; movie skipped")
        else:
            warnings.append(f"movie exceeds byte budget ({len(text.encode('utf-8'))} > {budget} bytes); movie not written")
        return _skipped_movie(warnings, total_frames=total_frames, desolvated=desolvated)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    return {"written": True, "movie_frames": movie_frames, "total_source_frames": total_frames,
            "movie_stride": effective_stride, "frame_indices": list(frame_indices[:movie_frames]),
            "frame_times_ps": frame_times, "atom_count": len(layout), "desolvated": desolvated,
            "aligned": aligned, "conect_count": len(conect_lines), "size_bytes": target.stat().st_size,
            "warnings": list(warnings)}
