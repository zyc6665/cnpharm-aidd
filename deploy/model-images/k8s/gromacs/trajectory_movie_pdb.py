#!/usr/bin/env python3
"""PDB template parsing, desolvation, ligand CONECT, and model rendering helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

PDB_MAX_ATOMS = 99999
WATER_RESNAMES = frozenset({
    "SOL", "HOH", "WAT", "TIP3", "TIP3P", "TIP4", "TIP4P", "SPC", "SPCE",
    "OPC", "T3P", "T4P", "H2O", "OH2",
})
ION_RESNAMES = frozenset({
    "NA", "NA+", "SOD", "CL", "CL-", "CLA", "K", "K+", "POT", "MG", "MG2",
    "CA", "CA2", "LI", "CS", "RB", "BR", "I", "F",
})
_SECTION_RE = re.compile(r"^\[\s*([^\]]+?)\s*\]")
_MAX_TARGETS = 4


@dataclass(frozen=True)
class AtomTemplate:
    """One ATOM/HETATM record with fixed columns kept as raw text."""
    record: str
    atom_name: str
    altloc: str
    resname: str
    chain_id: str
    resseq: str
    icode: str
    occupancy: float
    temp_factor: float
    element: str
    segment_index: int = 0
    serial: int | None = None


@dataclass(frozen=True)
class MovieAtomLayout:
    """A normalized atom plus whether a ``TER`` must precede it in every model."""
    atom: AtomTemplate
    ter_before: bool = False


def _as_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _element_of(atom: AtomTemplate) -> str:
    return atom.element.strip().upper() or re.sub(r"[^A-Za-z]", "", atom.atom_name)[:1].upper()


def _is_water(atom: AtomTemplate, water_names: set[str]) -> bool:
    return atom.resname.strip().upper() in water_names


def _is_ion(atom: AtomTemplate) -> bool:
    return atom.resname.strip().upper() in ION_RESNAMES


def _is_ligand(atom: AtomTemplate, ligand_resname: str) -> bool:
    return bool(ligand_resname) and atom.resname.strip().upper() == ligand_resname


def parse_pdb_atom_templates(topology_pdb: Path) -> list[AtomTemplate]:
    """Parse ATOM/HETATM records, collapsing altLocs by (segment, chain, resseq, icode) like MDTraj 1.10.3."""
    path = Path(topology_pdb)
    if not path.is_file():
        raise FileNotFoundError(f"topology PDB not found: {path}")
    templates: list[AtomTemplate] = []
    segment = 0
    residue_key: tuple | None = None
    locked_resname = ""
    seen_alts: dict[str, set[str]] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        record = line[:6].strip().upper()
        if record == "TER":
            segment += 1
            residue_key, locked_resname, seen_alts = None, "", {}
            continue
        if record not in ("ATOM", "HETATM") or len(line) < 27:
            continue
        atom_name, altloc = line[12:16].strip(), line[16:17].strip()
        resname, chain_id = line[17:20].strip(), line[21:22].strip()
        resseq, icode = line[22:26].strip(), line[26:27].strip()
        serial_text = line[6:11].strip()
        key = (segment, chain_id, resseq, icode)
        if key != residue_key:
            residue_key, seen_alts = key, {}
            locked_resname = resname  # first resname wins for the whole residue
        alts = seen_alts.get(atom_name)
        if alts is not None and altloc not in alts:  # alternate conformer: keep first
            continue
        seen_alts.setdefault(atom_name, set()).add(altloc)
        templates.append(AtomTemplate(
            record=record, atom_name=atom_name, altloc=altloc, resname=locked_resname,
            chain_id=chain_id, resseq=resseq, icode=icode,
            occupancy=_as_float(line[54:60], 1.0), temp_factor=_as_float(line[60:66], 0.0),
            element=line[76:78].strip() if len(line) >= 78 else "", segment_index=segment,
            # Hybrid-36 and blank serials cannot prove identity; leave them unknown.
            serial=int(serial_text) if serial_text.isdigit() and int(serial_text) > 0 else None,
        ))
    return templates


def select_desolvated_indices(
    templates: Sequence[AtomTemplate], *, ligand_resname: str | None = None,
    water_resname: str | None = None, strip_ions: bool = True,
) -> list[int]:
    """Keep non-water/non-ion atoms, protecting the ligand; degrade to non-water if empty."""
    ligand = (ligand_resname or "").strip().upper()
    water_names = set(WATER_RESNAMES) | ({water_resname.strip().upper()} if water_resname and water_resname.strip() else set())
    kept, removed_water = [], []
    for position, atom in enumerate(templates):
        if _is_ligand(atom, ligand):
            kept.append(position)
        elif _is_water(atom, water_names):
            removed_water.append(position)
        elif not (strip_ions and _is_ion(atom)):
            kept.append(position)
    if kept:
        return kept
    removed = set(removed_water)
    return [position for position in range(len(templates)) if position not in removed]


def _assign_chain(used: set[str]) -> str:
    """Return a free 1-char chain id, or ``""`` when all 36 candidates are taken."""
    for candidate in "LZYXWVUTSRQPONMKJIHGFEDCBA0123456789":
        if candidate not in used:
            return candidate
    return ""


def _format_atom_name(name: str, element: str) -> str:
    name = name[:4]
    if len(name) >= 4:
        return name
    return f"{(' ' if len(element.strip()) <= 1 else '') + name:<4}"


def _unique_atom_name(name: str, used: set[str], element: str) -> str:
    """Find a de-duplicated 4-column atom name, or ``""`` if every candidate is used."""
    for number in range(1, 10000):
        digits = str(number)
        candidate = f"{name[: max(1, 4 - len(digits))]}{digits}"
        if _format_atom_name(candidate, element) not in used:
            return candidate
    return ""


def _ligand_residue_key(atom: AtomTemplate) -> tuple[int, str, str, str, str]:
    return (atom.segment_index, atom.chain_id.strip(), atom.resseq, atom.icode, atom.resname.strip().upper())


def normalize_movie_templates(
    templates: Sequence[AtomTemplate], *, ligand_resname: str | None = None,
) -> list[MovieAtomLayout] | None:
    """Ligand->HETATM, free-chain assignment, atom-name de-dupe by final 4-col field
    (so a truncated C1000 cannot collide to C100) and TER boundaries. Returns ``None``
    when chain-id or atom-name candidates are exhausted, never ambiguous duplicates."""
    ligand = (ligand_resname or "").strip().upper()
    used_chains = {atom.chain_id.strip().upper() for atom in templates if atom.chain_id.strip()}
    blank_ligand_chain = any(_is_ligand(a, ligand) and not a.chain_id.strip() for a in templates)
    ligand_chain = _assign_chain(used_chains) if blank_ligand_chain else ""
    if blank_ligand_chain and not ligand_chain:
        return None
    used_names: dict[tuple, set[str]] = {}
    layout: list[MovieAtomLayout] = []
    previous: AtomTemplate | None = None
    previous_ligand = False
    for original in templates:
        is_ligand = _is_ligand(original, ligand)
        atom = original
        if is_ligand:
            atom = replace(original, record="HETATM", chain_id=original.chain_id.strip() or ligand_chain,
                           element=original.element.strip() or _element_of(original))
            names = used_names.setdefault(_ligand_residue_key(atom), set())
            final = _format_atom_name(atom.atom_name, atom.element)
            if final in names:
                fresh = _unique_atom_name(atom.atom_name, names, atom.element)
                if not fresh:
                    return None
                atom = replace(atom, atom_name=fresh)
                final = _format_atom_name(atom.atom_name, atom.element)
            names.add(final)
        ter_before = previous is not None and (
            atom.segment_index != previous.segment_index
            or atom.chain_id != previous.chain_id
            or is_ligand != previous_ligand
            or (is_ligand and _ligand_residue_key(atom) != _ligand_residue_key(previous))
        )
        layout.append(MovieAtomLayout(atom, ter_before))
        previous, previous_ligand = atom, is_ligand
    return layout


def _sdf_template(path: Path, expected_atoms: int) -> tuple[list[str], list[tuple[int, int, int]]] | None:
    """Return (element symbols, bond orders) from a ligand SDF, or None."""
    try:
        from rdkit import Chem
    except ImportError:
        return None
    sdf_path = Path(path)
    if not sdf_path.is_file():
        return None
    molecule = Chem.MolFromMolFile(str(sdf_path), removeHs=False, sanitize=False)
    if molecule is None or molecule.GetNumAtoms() != expected_atoms:
        return None
    try:
        Chem.Kekulize(molecule, clearAromaticFlags=True)
    except Exception:  # noqa: BLE001 - aromatic perception is best-effort
        pass
    elements = [atom.GetSymbol().strip() for atom in molecule.GetAtoms()]
    orders: dict[tuple[int, int], int] = {}
    for bond in molecule.GetBonds():
        first, second = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        try:
            raw = float(bond.GetBondTypeAsDouble())
        except (TypeError, ValueError):
            raw = 1.0
        order = 2 if raw == 2 else 3 if raw == 3 else 1
        key = (min(first, second), max(first, second))
        orders[key] = max(order, orders.get(key, 1))
    return elements, [(first, second, order) for (first, second), order in sorted(orders.items())]


def _itp_bond_pairs(ligand_itp: Path) -> list[tuple[int, int]]:
    path = Path(ligand_itp)
    if not path.is_file():
        return []
    pairs: list[tuple[int, int]] = []
    in_bonds = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        code = line.split(";", 1)[0].strip()
        if not code or code.startswith("#"):
            continue
        match = _SECTION_RE.match(code)
        if match:
            in_bonds = match.group(1).strip().lower() == "bonds"
            continue
        if not in_bonds:
            continue
        parts = code.split()
        if len(parts) < 2:
            continue
        try:
            pairs.append((int(parts[0]), int(parts[1])))
        except ValueError:
            continue
    return pairs


def _itp_edge_set(ligand_itp: Path, n_atoms: int) -> set[tuple[int, int]]:
    """Undirected 0-based bond graph from the ITP, filtered to valid ligand atoms."""
    edges: set[tuple[int, int]] = set()
    for first, second in _itp_bond_pairs(Path(ligand_itp)):
        a, b = first - 1, second - 1
        if 0 <= a < n_atoms and 0 <= b < n_atoms and a != b:
            edges.add((min(a, b), max(a, b)))
    return edges


def _ligand_bond_pairs(
    templates: Sequence[AtomTemplate] | None, ligand_resname: str | None, ligand_itp: Path | None,
) -> list[tuple[int, int]]:
    """Trusted ITP ligand bonds mapped to indices in the supplied templates
    (already desolvated when called from the exporter). Empty without an ITP."""
    ligand = (ligand_resname or "").strip().upper()
    if not templates or not ligand or ligand_itp is None:
        return []
    positions = [index for index, atom in enumerate(templates) if _is_ligand(atom, ligand)]
    local = {number + 1: position for number, position in enumerate(positions)}
    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for first, second in _itp_bond_pairs(Path(ligand_itp)):
        a, b = local.get(first), local.get(second)
        if a is None or b is None or a == b:
            continue
        key = (min(a, b), max(a, b))
        if key not in seen:  # collapse an undirected pair written twice
            seen.add(key)
            pairs.append(key)
    return pairs


def _conect_lines_for_atom(serial: int, targets: Sequence[int]) -> list[str]:
    return [
        f"CONECT{serial:>5}" + "".join(f"{target:>5}" for target in targets[start:start + _MAX_TARGETS])
        for start in range(0, len(targets), _MAX_TARGETS)
    ]


def build_ligand_conect_lines(
    kept_atoms: Sequence[AtomTemplate], *, ligand_resname: str | None = None,
    ligand_template_sdf: Path | None = None, ligand_itp: Path | None = None,
    warnings: list[str] | None = None,
) -> list[str]:
    """Build the one CONECT block: SDF bond orders only when both the element order
    and the bond graph match the topology ITP, else de-duplicated ITP single bonds."""
    warnings = warnings if warnings is not None else []
    ligands = (ligand_resname or "").strip().upper()
    ligand_positions = [p for p, atom in enumerate(kept_atoms) if _is_ligand(atom, ligands)]
    if not ligands or not ligand_positions:
        return []
    if len(kept_atoms) > PDB_MAX_ATOMS:
        warnings.append("movie has more than 99999 atoms; CONECT block skipped (PDB serial limit)")
        return []
    ligand_atoms = [kept_atoms[position] for position in ligand_positions]
    template_elements = [_element_of(atom) for atom in ligand_atoms]
    sdf_bonds: list[tuple[int, int, int]] | None = None
    if ligand_template_sdf is not None:
        parsed = _sdf_template(Path(ligand_template_sdf), len(ligand_positions))
        if parsed is None:
            warnings.append(f"ligand template SDF unusable for {ligand_template_sdf}; falling back to ITP bonds")
        else:
            sdf_elements, candidate_bonds = parsed
            if [symbol.upper() for symbol in sdf_elements] != template_elements:
                warnings.append("SDF element order differs from topology; skipping SDF bond orders and using ITP bonds")
            elif ligand_itp is not None:
                itp_edges = _itp_edge_set(ligand_itp, len(ligand_positions))
                sdf_edges = {(min(i, j), max(i, j)) for i, j, _ in candidate_bonds}
                # Compare unconditionally: an ITP with no bonds must not be read as
                # "unknown" and silently let SDF bond orders through.
                if itp_edges != sdf_edges:
                    warnings.append("SDF bond topology differs from ligand ITP; skipping SDF bond orders and using ITP bonds")
                else:
                    sdf_bonds = candidate_bonds
            else:
                sdf_bonds = candidate_bonds
    bonds: list[tuple[int, int, int]] = []
    if sdf_bonds is not None:
        bonds = [(ligand_positions[i] + 1, ligand_positions[j] + 1, order) for i, j, order in sdf_bonds]
    elif ligand_itp is not None:
        local_to_serial = {i + 1: position + 1 for i, position in enumerate(ligand_positions)}
        seen: set[tuple[int, int]] = set()
        for first, second in _itp_bond_pairs(Path(ligand_itp)):
            key = (min(first, second), max(first, second))
            if key in seen:  # collapse an undirected pair written twice
                continue
            seen.add(key)
            sa, sb = local_to_serial.get(first), local_to_serial.get(second)
            if sa is None or sb is None or sa == sb:
                continue
            bonds.append((sa, sb, 1))
    adjacency: dict[int, list[int]] = {}
    for first, second, order in bonds:
        for _ in range(max(1, order)):
            adjacency.setdefault(first, []).append(second)
            adjacency.setdefault(second, []).append(first)
    lines: list[str] = []
    for serial in sorted(adjacency):
        targets = sorted(adjacency[serial])
        if targets:
            lines.extend(_conect_lines_for_atom(serial, targets))
    return lines


def _pdb_atom_line(serial: int, atom: AtomTemplate, coordinates: Sequence[float]) -> str:
    x, y, z = (float(value) for value in coordinates)
    element = (atom.element or _element_of(atom))[:2]
    return (
        f"{atom.record:<6}{serial:>5} {_format_atom_name(atom.atom_name, element)}"
        f"{atom.altloc[:1] or ' '}{atom.resname[:3]:>3} {atom.chain_id[:1] or ' '}"
        f"{atom.resseq[:4].rjust(4)}{atom.icode[:1] or ' '}   {x:8.3f}{y:8.3f}{z:8.3f}"
        f"{atom.occupancy:6.2f}{atom.temp_factor:6.2f}          {element:>2}"
    )


def _render_movie(layout, frames_angstrom, remark_lines, conect_lines) -> str:
    lines: list[str] = [t if t.startswith("REMARK") else f"REMARK   {t}" for t in remark_lines]
    for model_index, frame in enumerate(frames_angstrom, start=1):
        # wwPDB: "MODEL " cols 1-6, cols 7-10 blank, serial right-aligned cols 11-14.
        lines.append(f"MODEL     {model_index:>4}")
        for position, entry in enumerate(layout):
            if entry.ter_before:
                lines.append("TER")
            if position >= len(frame):
                break
            lines.append(_pdb_atom_line(position + 1, entry.atom, frame[position]))
        lines.append("TER")
        lines.append("ENDMDL")
    lines.extend(conect_lines)
    lines.append("END")
    return "\n".join(lines) + "\n"
