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


# MDTraj 1.10.3's GRO reader rewrites atom and residue names through its bundled
# pdbNames.xml. Both the topology PDB and the GRO file come from the same TPR, so
# normalise the PDB template exactly the way that reader normalises the GRO names
# before comparing them. The tables below are generated from that file: a
# per-residue entry overrides a base entry keyed by the *raw* name (PRO HT1 -> H2
# while other residues map HT1 -> H), and residues absent from the file (CYM,
# ASH, arbitrary ligands) keep their raw names.
_GRO_PROTEIN_ATOM_ALIASES = {
    'H': 'H', 'HN': 'H', 'H1': 'H', '1H': 'H', 'HN1': 'H', 'HT1': 'H',
    'H2': 'H2', '2H': 'H2', 'HN2': 'H2', 'HT2': 'H2', 'H3': 'H3', '3H': 'H3',
    'HN3': 'H3', 'HT3': 'H3', 'O': 'O', 'O1': 'O', 'OT1': 'O', 'OCT1': 'O',
    'OC1': 'O', 'OXT': 'OXT', 'O2': 'OXT', 'OT2': 'OXT', 'OCT2': 'OXT', 'OC2': 'OXT',
    'OT': 'OXT',
}

_GRO_NUCLEIC_ATOM_ALIASES = {
    'H': 'H', 'HN': 'H', 'OP1': 'OP1', 'O1P': 'OP1', 'OP2': 'OP2', 'O2P': 'OP2',
    'OP3': 'OP3', 'O3P': 'OP3', 'HOP2': 'HOP2', '2HOP': 'HOP2', 'HOP3': 'HOP3', '3HOP': 'HOP3',
    "C1'": "C1'", 'C1*': "C1'", "C2'": "C2'", 'C2*': "C2'", "C3'": "C3'", 'C3*': "C3'",
    "C4'": "C4'", 'C4*': "C4'", "C5'": "C5'", 'C5*': "C5'", "O2'": "O2'", 'O2*': "O2'",
    "O3'": "O3'", 'O3*': "O3'", "O4'": "O4'", 'O4*': "O4'", "O5'": "O5'", 'O5*': "O5'",
    "H1'": "H1'", 'H1*': "H1'", "H2'": "H2'", 'H2*': "H2'", '1H2*': "H2'", "H2''": "H2''",
    '2H2*': "H2''", "H3'": "H3'", 'H3*': "H3'", "H4'": "H4'", 'H4*': "H4'", "H5'": "H5'",
    '1H5*': "H5'", "H5''": "H5''", '2H5*': "H5''", "HO2'": "HO2'", '2HO*': "HO2'", "HO3'": "HO3'",
    'H3T': "HO3'",
}

_GRO_PROTEIN_RESNAMES = frozenset({
    'GLY', 'ALA', 'VAL', 'LEU', 'ILE', 'SER', 'THR', 'CYS', 'PRO', 'PHE', 'TYR', 'TRP', 'HIS', 'ASP', 'ASN', 'GLU', 'GLN', 'MET', 'LYS', 'ARG', 'ORN', 'AIB', 'PCA', 'FOR', 'ACE', 'NME', 'NH2', 'UNK'
})

_GRO_NUCLEIC_RESNAMES = frozenset({
    'A', 'G', 'C', 'U', 'DA', 'DG', 'DC', 'DT'
})

_GRO_RESIDUE_ALIASES = {
    'CYX': 'CYS', 'HSP': 'HIS', 'HSH': 'HIS', 'HIP': 'HIS', 'HIH': 'HIS',
    'HID': 'HIS', 'HIE': 'HIS', 'HSD': 'HIS', 'HSE': 'HIS', 'NMA': 'NME',
    'ADE': 'A', 'GUA': 'G', 'CYT': 'C', 'URA': 'U', 'DAD': 'DA',
    'DGU': 'DG', 'DCY': 'DC', 'THY': 'DT', 'H20': 'HOH', 'WAT': 'HOH',
    'SOL': 'HOH', 'TIP3': 'HOH',
}

_GRO_RESIDUE_ATOM_ALIASES = {
    'GLY': {
        'HA2': 'HA2', '2HA': 'HA2', 'HA3': 'HA3', 'HA1': 'HA3', '1HA': 'HA3', '3HA': 'HA3',
    },
    'ALA': {
        'HB1': 'HB1', '1HB': 'HB1', 'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', '3HB': 'HB3',
    },
    'VAL': {
        'HG11': 'HG11', '1HG1': 'HG11', 'HG12': 'HG12', '2HG1': 'HG12', 'HG13': 'HG13', '3HG1': 'HG13',
        'HG21': 'HG21', '1HG2': 'HG21', 'HG22': 'HG22', '2HG2': 'HG22', 'HG23': 'HG23', '3HG2': 'HG23',
    },
    'LEU': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
        'HD11': 'HD11', '1HD1': 'HD11', 'HD12': 'HD12', '2HD1': 'HD12', 'HD13': 'HD13', '3HD1': 'HD13',
        'HD21': 'HD21', '1HD2': 'HD21', 'HD22': 'HD22', '2HD2': 'HD22', 'HD23': 'HD23', '3HD2': 'HD23',
    },
    'ILE': {
        'CD1': 'CD1', 'CD': 'CD1', 'HG12': 'HG12', '2HG1': 'HG12', 'HG13': 'HG13', 'HG11': 'HG13',
        '1HG1': 'HG13', '3HG1': 'HG13', 'HG21': 'HG21', '1HG2': 'HG21', 'HG22': 'HG22', '2HG2': 'HG22',
        'HG23': 'HG23', '3HG2': 'HG23', 'HD11': 'HD11', '1HD1': 'HD11', 'HD1': 'HD11', 'HD12': 'HD12',
        '2HD1': 'HD12', 'HD2': 'HD12', 'HD13': 'HD13', '3HD1': 'HD13', 'HD3': 'HD13',
    },
    'SER': {
        'OG': 'OG', 'OG1': 'OG', 'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3',
        '1HB': 'HB3', '3HB': 'HB3', 'HG': 'HG', 'HG1': 'HG', 'HOG': 'HG',
    },
    'THR': {
        'OG1': 'OG1', 'OG': 'OG1', 'CG2': 'CG2', 'CG': 'CG2', 'HG1': 'HG1', 'HOG': 'HG1',
        'HOG1': 'HG1', '1HG': 'HG1', 'HG21': 'HG21', '1HG2': 'HG21', 'HG22': 'HG22', '2HG2': 'HG22',
        'HG23': 'HG23', '3HG2': 'HG23',
    },
    'CYS': {
        'SG': 'SG', 'SG1': 'SG', 'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3',
        '1HB': 'HB3', '3HB': 'HB3', 'HG': 'HG', 'HG1': 'HG', 'HSG': 'HG',
    },
    'PRO': {
        'HT1': 'H2', 'HT2': 'H3', 'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3',
        '1HB': 'HB3', '3HB': 'HB3', 'HG2': 'HG2', '2HG': 'HG2', 'HG3': 'HG3', 'HG1': 'HG3',
        '1HG': 'HG3', '3HG': 'HG3', 'HD2': 'HD2', '2HD': 'HD2', 'HD3': 'HD3', 'HD1': 'HD3',
        '1HD': 'HD3', '3HD': 'HD3',
    },
    'PHE': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
    },
    'TYR': {
        'HH': 'HH', 'HOH': 'HH', 'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3',
        '1HB': 'HB3', '3HB': 'HB3',
    },
    'TRP': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
        'HE1': 'HE1', 'HNE': 'HE1',
    },
    'HIS': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
        'HD1': 'HD1', 'HND': 'HD1', 'HND1': 'HD1', 'HD2': 'HD2', 'HD': 'HD2', 'HE1': 'HE1',
        'HE': 'HE1', 'HE2': 'HE2', 'HNE': 'HE2', 'HNE2': 'HE2',
    },
    'ASP': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
    },
    'ASN': {
        'OD1': 'OD1', 'OD': 'OD1', 'ND2': 'ND2', 'ND': 'ND2', 'HB2': 'HB2', '2HB': 'HB2',
        'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3', 'HD21': 'HD21', '1HD2': 'HD21',
        'HND1': 'HD21', 'HD22': 'HD22', '2HD2': 'HD22', 'HND2': 'HD22',
    },
    'GLU': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
        'HG2': 'HG2', '2HG': 'HG2', 'HG3': 'HG3', 'HG1': 'HG3', '1HG': 'HG3', '3HG': 'HG3',
    },
    'GLN': {
        'OE1': 'OE1', 'OE': 'OE1', 'NE2': 'NE2', 'NE': 'NE2', 'HB2': 'HB2', '2HB': 'HB2',
        'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3', 'HG2': 'HG2', '2HG': 'HG2',
        'HG3': 'HG3', 'HG1': 'HG3', '1HG': 'HG3', '3HG': 'HG3', 'HE21': 'HE21', '1HE2': 'HE21',
        'HNE1': 'HE21', 'HE22': 'HE22', '2HE2': 'HE22', 'HNE2': 'HE22',
    },
    'MET': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
        'HG2': 'HG2', '2HG': 'HG2', 'HG3': 'HG3', 'HG1': 'HG3', '1HG': 'HG3', '3HG': 'HG3',
        'HE1': 'HE1', '1HE': 'HE1', 'HE2': 'HE2', '2HE': 'HE2', 'HE3': 'HE3', '3HE': 'HE3',
    },
    'LYS': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
        'HG2': 'HG2', '2HG': 'HG2', 'HG3': 'HG3', 'HG1': 'HG3', '1HG': 'HG3', '3HG': 'HG3',
        'HD2': 'HD2', '2HD': 'HD2', 'HD3': 'HD3', 'HD1': 'HD3', '1HD': 'HD3', '3HD': 'HD3',
        'HE2': 'HE2', '2HE': 'HE2', 'HE3': 'HE3', 'HE1': 'HE3', '1HE': 'HE3', '3HE': 'HE3',
        'HZ1': 'HZ1', '1HZ': 'HZ1', 'HNZ1': 'HZ1', 'HZ2': 'HZ2', '2HZ': 'HZ2', 'HNZ2': 'HZ2',
        'HZ3': 'HZ3', '3HZ': 'HZ3', 'HNZ3': 'HZ3',
    },
    'ARG': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
        'HG2': 'HG2', '2HG': 'HG2', 'HG3': 'HG3', 'HG1': 'HG3', '1HG': 'HG3', '3HG': 'HG3',
        'HD2': 'HD2', '2HD': 'HD2', 'HD3': 'HD3', 'HD1': 'HD3', '1HD': 'HD3', '3HD': 'HD3',
        'HH11': 'HH11', '1HH1': 'HH11', 'HN11': 'HH11', 'HH12': 'HH12', '2HH1': 'HH12', 'HN12': 'HH12',
        'HH21': 'HH21', '1HH2': 'HH21', 'HN21': 'HH21', 'HH22': 'HH22', '2HH2': 'HH22', 'HN22': 'HH22',
    },
    'ORN': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
        'HG2': 'HG2', '2HG': 'HG2', 'HG3': 'HG3', 'HG1': 'HG3', '1HG': 'HG3', '3HG': 'HG3',
        'HD2': 'HD2', '2HD': 'HD2', 'HD3': 'HD3', 'HD1': 'HD3', '1HD': 'HD3', '3HD': 'HD3',
        'HE1': 'HE1', '1HE': 'HE1', 'HNE1': 'HE1', 'HE2': 'HE2', '2HE': 'HE2', 'HNE2': 'HE2',
        'HE3': 'HE3', '3HE': 'HE3', 'HNE3': 'HE3',
    },
    'AIB': {
        'HB11': 'HB11', '1HB1': 'HB11', 'HB12': 'HB12', '2HB1': 'HB12', 'HB13': 'HB13', '3HB1': 'HB13',
        'HB21': 'HB21', '1HB2': 'HB21', 'HB22': 'HB22', '2HB2': 'HB22', 'HB23': 'HB23', '3HB2': 'HB23',
    },
    'PCA': {
        'HB2': 'HB2', '2HB': 'HB2', 'HB3': 'HB3', 'HB1': 'HB3', '1HB': 'HB3', '3HB': 'HB3',
        'HG2': 'HG2', '2HG': 'HG2', 'HG3': 'HG3', 'HG1': 'HG3', '1HG': 'HG3', '3HG': 'HG3',
    },
    'FOR': {
        'C': 'C', 'CY': 'C', 'OY': 'O', 'HY': 'H',
    },
    'ACE': {
        'H1': 'H1', '1H': 'H1', 'C': 'C', 'CY': 'C', 'CH3': 'CH3', 'CAY': 'CH3',
        'CA': 'CH3', 'OY': 'O', 'HY1': 'H1', 'HH31': 'H1', '1HH3': 'H1', 'HY2': 'H2',
        'HH32': 'H2', '2HH3': 'H2', 'HY3': 'H3', 'HH33': 'H3', '3HH3': 'H3',
    },
    'NME': {
        'H1': 'H1', '1H': 'H1', 'HT1': 'H1', 'N': 'N', 'NT': 'N', 'C': 'C',
        'CH3': 'C', 'CT': 'C', 'CAT': 'C', 'CA': 'C', 'HNT': 'H', '1HA': 'H1',
        'HH31': 'H1', '1HH3': 'H1', '2HA': 'H2', 'HH32': 'H2', '2HH3': 'H2', '3HA': 'H3',
        'HH33': 'H3', '3HH3': 'H3',
    },
    'NH2': {
        'H1': 'HN1', '1H': 'HN1', 'HN1': 'HN1', 'HT1': 'HN1', 'H2': 'HN2', '2H': 'HN2',
        'HN2': 'HN2', 'HT2': 'HN2', 'N': 'N', 'NT': 'N',
    },
    'A': {
        'H61': 'H61', '1H6': 'H61', 'H62': 'H62', '2H6': 'H62',
    },
    'G': {
        'H21': 'H21', '1H2': 'H21', 'H22': 'H22', '2H2': 'H22',
    },
    'C': {
        'H41': 'H41', '1H4': 'H41', 'H42': 'H42', '2H4': 'H42',
    },
    'DA': {
        'H61': 'H61', '1H6': 'H61', 'H62': 'H62', '2H6': 'H62',
    },
    'DG': {
        'H21': 'H21', '1H2': 'H21', 'H22': 'H22', '2H2': 'H22',
    },
    'DC': {
        'H41': 'H41', '1H4': 'H41', 'H42': 'H42', '2H4': 'H42',
    },
    'DT': {
        'C7': 'C7', 'C5M': 'C7', 'H71': 'H71', '1H5M': 'H71', 'H72': 'H72', '2H5M': 'H72',
        'H73': 'H73', '3H5M': 'H73',
    },
    'HOH': {
        'O': 'O', 'OW': 'O', 'OH2': 'O', 'O1': 'O', 'H1': 'H1', 'HW1': 'H1',
        'H2': 'H2', 'HW2': 'H2',
    },
}

# pdbNames.xml also carries non-protein, non-nucleic entries (water).
_GRO_OTHER_RESNAMES = frozenset({"HOH"})


def _canonical_gro_resname(resname: str) -> str:
    """Residue name exactly as MDTraj 1.10.3's GRO reader rewrites it.

    Both the replacement map and the per-residue atom tables are keyed by the
    raw XML names (upper case); MDTraj looks the raw record up without changing
    case, so ``ala`` stays ``ala`` and gets no atom replacements. Upper-casing
    here would apply a table the reader never applied.
    """
    name = (resname or "").strip()
    return _GRO_RESIDUE_ALIASES.get(name, name)


def _mdtraj_gro_atom_name(atom_name: str, resname: str = "") -> str:
    """Return the atom name MDTraj 1.10.3's GRO reader emits for a raw PDB name.

    The reader renames the residue first, then looks the raw atom name up in the
    merged table for that residue. Lookups are case-sensitive: the XML keys are
    upper case, so a lower-case ``h1`` is emitted unchanged and must be compared
    as ``h1`` instead of being silently rewritten to ``H``/``H1``. Residues
    outside pdbNames.xml are untouched. Compare the result against the
    trajectory name as MDTraj returned it -- never normalise both sides, or a
    canonical name such as ``H1`` would be mapped a second time (ACE ``HH31`` ->
    ``H1`` -> ``H``).
    """
    name = (atom_name or "").strip()
    res = _canonical_gro_resname(resname)
    if res in _GRO_PROTEIN_RESNAMES:
        base: dict[str, str] = _GRO_PROTEIN_ATOM_ALIASES
    elif res in _GRO_NUCLEIC_RESNAMES:
        base = _GRO_NUCLEIC_ATOM_ALIASES
    elif res in _GRO_OTHER_RESNAMES:
        base = {}
    else:
        return name
    return _GRO_RESIDUE_ATOM_ALIASES.get(res, {}).get(name, base.get(name, name))


_HYBRID36_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# GROMACS' PDB writer stores only resSeq % 10000 in the four-column field while
# GRO keeps the full five-column number, so the two files describe one residue
# with e.g. 0 (PDB) and 10000 (GRO) once a system has more than 9999 residues.
_PDB_RESSEQ_MODULUS = 10000


def _residue_number(value: Any) -> int | None:
    """Parse a residue number, decoding the hybrid-36 upper-case block.

    GROMACS writes plain decimals, but a topology PDB produced by other tools
    may encode resSeq > 9999 as hybrid-36 (``A000`` == 10000). Decoding it keeps
    the comparison honest instead of treating that residue as unparsable.
    """
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    if text[:1] in ("+", "-"):
        digits = text[1:]
        return int(text) if digits.isdigit() else None
    if text.isdigit():
        return int(text)
    if len(text) != 4 or not text.isupper():
        return None
    if any(character not in _HYBRID36_DIGITS for character in text):
        return None
    return int(text, 36) - 10 * 36 ** 3 + 10 ** 4


def _residue_numbers_match(expected: int, actual: int) -> bool:
    """Whether two numbers denote the same residue of the same ``.tpr``.

    A folded PDB number (0) still identifies the GRO residue 10000. Hybrid-36
    numbers decode to >= 10000 and were not folded, so they compare directly.
    """
    if expected == actual:
        return True
    return (
        expected >= 0
        and actual >= _PDB_RESSEQ_MODULUS
        and expected == actual % _PDB_RESSEQ_MODULUS
    )


def _atom_serial(atom: Any) -> int | None:
    """Atom serial as a positive int, or None when the source cannot prove one."""
    value = getattr(atom, "serial", None)
    if value is None or isinstance(value, bool):
        return None
    try:
        serial = int(value)
    except (TypeError, ValueError):
        return None
    return serial if serial > 0 else None


def _trusted_serial_positions(serials: Sequence[int | None]) -> dict[int, int]:
    """Positions whose serial uniquely identifies an atom in this file.

    GROMACS PDB and GRO writers both store ``serial % 100000`` (PDB columns
    7-11 / GRO atom-number columns), so atom 100000 is written as 0 and atom
    100001 repeats 1. Zeros arrive here as ``None``; any value that repeats in
    the same file is ambiguous for the same reason and is dropped as well.
    """
    counts: dict[int, int] = {}
    for serial in serials:
        if serial is not None:
            counts[serial] = counts.get(serial, 0) + 1
    return {
        position: serial
        for position, serial in enumerate(serials)
        if serial is not None and counts.get(serial) == 1
    }


def _template_residue_runs(
    templates: Sequence[AtomTemplate],
) -> tuple[list[int], list[tuple[str, str]]]:
    """0-based residue ordinal per atom plus each run's raw (resname, resSeq).

    MDTraj 1.10.3 starts a new GRO residue only when the consecutive raw
    ``(resname, resSeq)`` pair changes; GRO records carry neither chain nor
    insertion code, so those PDB-only distinctions must not split a run here.
    """
    positions: list[int] = []
    runs: list[tuple[str, str]] = []
    last_key: tuple[str, str] | None = None
    for template in templates:
        # MDTraj compares the raw resname/resSeq pair before any replacement.
        key = ((template.resname or "").strip(), (template.resseq or "").strip())
        if key != last_key:
            runs.append(key)
            last_key = key
        positions.append(len(runs) - 1)
    return positions, runs


def _trajectory_residue_runs(
    traj_atoms: Sequence[Any],
) -> tuple[list[int], list[tuple[str, Any]]]:
    """Ordinal per trajectory atom, using MDTraj's residue index when present and
    the GRO reader's own run rule for injected topologies that lack one."""
    positions: list[int] = []
    runs: list[tuple[str, Any]] = []
    last_key: tuple[Any, ...] | None = None
    for atom in traj_atoms:
        residue = getattr(atom, "residue", None)
        index = getattr(residue, "index", None)
        # MDTraj already applied its case-sensitive residue replacement; keep the
        # name exactly as returned and never normalise it a second time.
        name = (getattr(residue, "name", "") or "").strip()
        seq = getattr(residue, "resSeq", None)
        if index is not None:
            key: tuple[Any, ...] = ("index", index)
        else:
            key = ("seq", name, "" if seq is None else str(seq).strip())
        if key != last_key:
            runs.append((name, seq))
            last_key = key
        positions.append(len(runs) - 1)
    return positions, runs


def _validate_trajectory_topology(
    trajectory: Any, templates: Sequence[AtomTemplate], keep_indices: Sequence[int],
    *, using_gro: bool = False,
) -> None:
    """Raise when the loaded trajectory no longer matches the altLoc-de-duped template.
    Checks total atom count on the full system (ignoring stripped virtual-site/water
    element labels) and kept solute order. Under a GRO topology, MDTraj lacks an
    element column (inferring e.g. ``CL1`` as ``C`` and a digit-prefixed terminal
    ``1H`` as virtual-site ``VS``) and canonicalizes GROMACS terminal/ILE names, so
    the name comparison is the authoritative check; a second element comparison
    would only re-read the same inferred name and reject valid atoms. Only the PDB
    template is normalised -- trajectory names come back already normalised from
    MDTraj, and mapping them again would reject e.g. ACE ``HH31`` -> ``H1`` ->
    ``H``. Atom serials decide residue identity when both files carry them."""
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
    if using_gro:
        expected_positions, expected_runs = _template_residue_runs(templates)
        traj_positions, traj_runs = _trajectory_residue_runs(traj_atoms)
        for index in kept:
            if traj_positions[index] != expected_positions[index]:
                raise ValueError("GRO trajectory residue order differs from topology PDB; refusing to render")
        kept_runs = sorted({expected_positions[index] for index in kept})
        for run in kept_runs:
            expected_name = _canonical_gro_resname(expected_runs[run][0])
            traj_name = _canonical_gro_resname(traj_runs[run][0])
            if expected_name and traj_name and expected_name != traj_name:
                raise ValueError("GRO trajectory residue order differs from topology PDB; refusing to render")
        # A whole-residue swap of the same residue type keeps every ordinal and
        # atom name. Atom serials are the per-atom identity both writers preserve
        # for a shared TPR (PDB columns 7-11, GRO atom-number columns), so compare
        # every position both sides can prove: a partial proof still exposes an
        # in-place swap, and a full proof accepts a legal renumbering (42.. -> 1..).
        kept_order = sorted(kept)
        # Count uniqueness over the whole file, solvent included: a serial that
        # repeats on a filtered water atom is still ambiguous evidence for the
        # kept solute atom that shares it. Only kept positions are compared.
        expected_trusted = _trusted_serial_positions(
            [template.serial for template in templates]
        )
        traj_trusted = _trusted_serial_positions(
            [_atom_serial(atom) for atom in traj_atoms]
        )
        kept_positions = set(kept_order)
        comparable = set(expected_trusted) & set(traj_trusted) & kept_positions
        for position in sorted(comparable):
            if expected_trusted[position] != traj_trusted[position]:
                raise ValueError(
                    "GRO trajectory atom serials differ from topology PDB; refusing to render"
                )
        serials_prove_order = len(comparable) == len(kept_order)
        # Residue numbers are the fallback identity, but a rebuilt topology may
        # legitimately renumber (42.. -> 1..) or drop solvent residues (1, 3).
        # Only two cases are provably in order: identical numbering, or a changed
        # numbering backed by an atom-serial match at every kept position.
        # Otherwise the movie is skipped instead of risking an atom-order mismatch.
        expected_numbers = [_residue_number(expected_runs[run][1]) for run in kept_runs]
        traj_numbers = [_residue_number(traj_runs[run][1]) for run in kept_runs]
        # Compare pair by pair: an unparseable residue number must not mask a
        # provable change at another residue, and a PDB field folded modulo
        # 10000 must not read as a renumbering of the same .tpr residue.
        numbering_changed = any(
            expected_number is not None
            and traj_number is not None
            and not _residue_numbers_match(expected_number, traj_number)
            for expected_number, traj_number in zip(expected_numbers, traj_numbers)
        )
        if numbering_changed and not serials_prove_order:
            raise ValueError(
                "GRO trajectory residue numbering differs from topology PDB "
                "without atom-serial proof; refusing to render"
            )
    for index, (template, traj_atom) in enumerate(zip(templates, traj_atoms)):
        if index not in kept:
            continue
        if using_gro:
            # Case-sensitive: MDTraj leaves an unknown-case name untouched, so
            # upper-casing only this side would compare ``h1`` against ``H``.
            traj_raw = (getattr(traj_atom, "name", "") or "").strip()
            if traj_raw:
                # MDTraj already normalised its own name; normalise only the raw
                # PDB template, or a canonical name would be mapped twice.
                if _mdtraj_gro_atom_name(template.atom_name, template.resname) != traj_raw:
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
