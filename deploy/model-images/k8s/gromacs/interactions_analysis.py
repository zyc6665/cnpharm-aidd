#!/usr/bin/env python3
"""Protein-ligand / protein-interface interaction analysis (clean-room, offline); writes contacts.csv + interactions.json, heavy deps imported lazily."""
from __future__ import annotations
import csv
import json
import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
CONTACTS_CSV_COLUMNS = ("residue_chain", "residue_seq", "residue_icode", "residue_name", "interaction_type",
                        "occupancy", "contact_frames", "total_frames", "min_distance_nm", "mean_distance_nm")
SUPPORTED_INTERACTION_TYPES = ("hbond_donor", "hbond_acceptor", "hydrophobic", "salt_bridge", "pi_stacking",
                               "cation_pi", "halogen", "water_bridge", "vdw_contact")
PROLIF_TO_CANONICAL_TYPE = {
    "HBDonor": "hbond_donor", "HBAcceptor": "hbond_acceptor", "Hydrophobic": "hydrophobic", "Anionic": "salt_bridge",
    "Cationic": "salt_bridge", "PiStacking": "pi_stacking", "EdgeToFace": "pi_stacking", "FaceToFace": "pi_stacking",
    "PiCation": "cation_pi", "CationPi": "cation_pi", "XBAcceptor": "halogen", "XBDonor": "halogen",
    "WaterBridge": "water_bridge", "VdWContact": "vdw_contact"}
# ProLIF 2.1+ takes the water AtomGroup as a WaterBridge constructor argument (parameters=), never fp.run(water=...).
DEFAULT_PROLIF_INTERACTIONS = tuple(name for name in PROLIF_TO_CANONICAL_TYPE if name != "WaterBridge")
# Only these ProLIF constructors accept `distance`; VdWContact(tolerance, vdwradii, preset) rejects it with TypeError.
PROLIF_DISTANCE_PARAMETER = {
    "HBDonor": "hbond_cutoff_nm", "HBAcceptor": "hbond_cutoff_nm", "Hydrophobic": "hydrophobic_cutoff_nm",
    "Anionic": "salt_bridge_cutoff_nm", "Cationic": "salt_bridge_cutoff_nm"}
_CANONICAL_BY_LOWER = {name.lower(): name for name in SUPPORTED_INTERACTION_TYPES}
_PROLIF_BY_LOWER = {name.lower(): kind for name, kind in PROLIF_TO_CANONICAL_TYPE.items()}
# ProLIF writes "ALA42.A"; an empty chain drops the dot ("ALA42"). Insertion codes stay attached when present.
_RESIDUE_ID = re.compile(
    r"^(?P<name>[A-Za-z0-9]{1,5}?)(?P<seq>-?\d+)(?P<icode>[A-Za-z]?)(?:\.(?P<chain>[A-Za-z0-9_]*))?$")
@dataclass(frozen=True)
class InteractionConfig:
    mode: str = "auto"
    ligand_resname: str = "LIG"
    stride: int = 1
    min_occupancy: float = 0.0
    hbond_cutoff_nm: float = 0.35
    hydrophobic_cutoff_nm: float = 0.45
    salt_bridge_cutoff_nm: float = 0.40
    contact_cutoff_nm: float = 0.45
    water_resname: str | None = None
    frame_dt_ps: float | None = None
@dataclass(frozen=True)
class FrameContact:
    frame: int
    time_ps: float
    residue_chain: str
    residue_seq: int
    residue_name: str
    interaction_type: str
    distance_nm: float | None = None
    residue_icode: str = ""
    residue_segment: int = 0
def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
def _residue_key(row: Mapping[str, Any] | FrameContact) -> tuple[str, int, str, str, int]:
    get = row.get if isinstance(row, Mapping) else lambda name, default=None: getattr(row, name, default)
    return (str(get("residue_chain", "")), int(get("residue_seq", 0) or 0), str(get("residue_icode", "") or ""),
            str(get("residue_name", "")), int(get("residue_segment", 0) or 0))
def normalize_interaction_type(raw_type: str | None) -> str | None:
    key = str(raw_type).strip().lower() if raw_type else ""
    return _CANONICAL_BY_LOWER.get(key) or _PROLIF_BY_LOWER.get(key)
def aggregate_contacts(frame_contacts: Iterable[FrameContact], *, total_frames: int,
                       min_occupancy: float = 0.0) -> list[dict[str, Any]]:
    if total_frames <= 0:
        return []
    per: dict[tuple[str, int, str, str, int, str], dict[int, float | None]] = {}
    for contact in frame_contacts:
        kind = normalize_interaction_type(contact.interaction_type)
        if kind is None:
            continue
        frames = per.setdefault((*_residue_key(contact), kind), {})
        value = None if contact.distance_nm is None else float(contact.distance_nm)
        if contact.frame not in frames:
            frames[contact.frame] = value
        elif value is not None:  # a later None must never erase an already recorded distance
            previous = frames[contact.frame]
            frames[contact.frame] = value if previous is None else min(previous, value)
    rows = []
    for (chain, seq, icode, name, segment, kind), frame_distances in per.items():
        contact_frames = min(len(frame_distances), int(total_frames))
        occupancy = _clamp01(contact_frames / int(total_frames))
        if occupancy < min_occupancy:
            continue
        distances = [value for value in frame_distances.values() if value is not None]
        rows.append({"residue_chain": chain, "residue_seq": seq, "residue_icode": icode, "residue_name": name,
                     "residue_segment": segment, "interaction_type": kind, "occupancy": occupancy,
                     "contact_frames": contact_frames, "total_frames": int(total_frames),
                     "min_distance_nm": min(distances) if distances else None,
                     "mean_distance_nm": sum(distances) / len(distances) if distances else None})
    rows.sort(key=lambda row: (-row["occupancy"], row["residue_chain"], row["residue_seq"],
                               row["residue_icode"], row["residue_name"], row["residue_segment"],
                               row["interaction_type"]))
    return rows
def build_timeline(frame_contacts: Iterable[FrameContact], *,
                   frame_times_ps: Mapping[int, float] | Sequence[float]) -> list[dict[str, Any]]:
    times = ({int(key): float(value) for key, value in frame_times_ps.items()}
             if isinstance(frame_times_ps, Mapping) else {i: float(v) for i, v in enumerate(frame_times_ps)})
    seen: dict[int, set[tuple[str, int, str, str, int, str]]] = {}
    for contact in frame_contacts:
        kind = normalize_interaction_type(contact.interaction_type)
        if kind is not None:
            seen.setdefault(int(contact.frame), set()).add((*_residue_key(contact), kind))
    groups = {"hbond_count": ("hbond_donor", "hbond_acceptor"), "hydrophobic_count": ("hydrophobic",),
              "salt_bridge_count": ("salt_bridge",)}
    timeline = []
    for frame in sorted(set(times) | set(seen)):
        keys, counts = seen.get(frame, set()), {}
        for name, kinds in groups.items():
            counts[name] = sum(1 for key in keys if key[-1] in kinds)
        timeline.append({"frame": frame, "time_ps": times.get(frame, 0.0), "total_contacts": len(keys), **counts,
                         "other_count": len(keys) - sum(counts.values())})
    return timeline
def _connected_components(adjacency: Mapping[str, Iterable[str]]) -> int:
    try:
        import networkx as nx
    except ImportError:
        nx = None
    if nx is not None:
        return int(nx.number_connected_components(nx.from_dict_of_lists(adjacency)))
    remaining, components = set(adjacency), 0
    while remaining:
        components += 1
        stack = [remaining.pop()]
        while stack:
            for neighbour in adjacency.get(stack.pop(), ()):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    stack.append(neighbour)
    return components
def build_interaction_network(aggregated_rows: Iterable[Mapping[str, Any]], *, anchor_id: str = "LIG",
                              anchor_kind: str = "ligand", min_edge_occupancy: float = 0.0) -> dict[str, Any]:
    # One edge per (source, target, type): occupancy stays in [0, 1]; weighted_degree sums it.
    rows = [row for row in aggregated_rows if _clamp01(float(row.get("occupancy") or 0.0)) >= min_edge_occupancy]
    anchor = {"id": anchor_id, "kind": anchor_kind, "chain": "", "residue_seq": None, "residue_icode": "",
              "residue_name": anchor_id}
    nodes: dict[str, dict[str, Any]] = {anchor_id: anchor}
    keys = list(map(_residue_key, rows))
    clashes = {key[:4] for key in keys if len({other[4] for other in keys if other[:4] == key[:4]}) > 1}
    edges = []
    for row in rows:
        chain, seq, icode, name, segment = _residue_key(row)
        node_id = (f"{chain}#{segment}:{name}{seq}{icode}" if (chain, seq, icode, name) in clashes
                   else f"{chain}:{seq}{icode}:{name}")
        distance = row.get("mean_distance_nm")
        nodes.setdefault(node_id, {"id": node_id, "kind": "residue", "chain": chain, "residue_seq": seq,
                                   "residue_icode": icode, "residue_name": name})
        kind = str(row.get("interaction_type") or "")
        edges.append({"source": anchor_id, "target": node_id, "interaction_type": kind,
                      "occupancy": round(_clamp01(float(row.get("occupancy") or 0.0)), 6),
                      "mean_distance_nm": None if distance is None else round(float(distance), 6)})
    edges.sort(key=lambda edge: (edge["source"], edge["target"], edge["interaction_type"]))
    adjacency = {node_id: set() for node_id in nodes}
    weighted = {node_id: 0.0 for node_id in nodes}
    for edge in edges:
        adjacency[edge["source"]].add(edge["target"])
        adjacency[edge["target"]].add(edge["source"])
        weighted[edge["source"]] += edge["occupancy"]
        weighted[edge["target"]] += edge["occupancy"]
    node_rows = [{**meta, "degree": len(adjacency[node_id]), "weighted_degree": round(weighted[node_id], 6)}
                 for node_id, meta in nodes.items()]
    node_rows.sort(key=lambda node: (node["id"] != anchor_id, node["id"]))
    hubs = sorted((node for node in node_rows if node["id"] != anchor_id),
                  key=lambda node: (-node["weighted_degree"], node["id"]))[:5]
    return {"anchor_id": anchor_id, "nodes": node_rows, "edges": edges, "stats": {
        "node_count": len(nodes), "edge_count": len(edges), "connected_components": _connected_components(adjacency),
        "hub_residues": hubs}}
def write_contacts_csv(rows: Iterable[Mapping[str, Any]], out_csv: Path) -> Path:
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CONTACTS_CSV_COLUMNS)
        for row in rows:
            writer.writerow(["" if row.get(name) is None else str(row.get(name)) if isinstance(row.get(name), (int, str))
                             else f"{float(row.get(name)):.4f}" for name in CONTACTS_CSV_COLUMNS])
    return out_csv
def build_summary_payload(*, mode: str, engine: str, ligand_resname: str, stride: int, total_frames: int,
                          cutoffs_nm: Mapping[str, float], rows: Iterable[Mapping[str, Any]] = (),
                          timeline: Sequence[Mapping[str, Any]] = (), network: Mapping[str, Any] | None = None,
                          warnings: Sequence[str] = ()) -> dict[str, Any]:
    rows, by_type, residues = list(rows), {}, set()
    for row in rows:
        kind = str(row.get("interaction_type", ""))
        by_type[kind] = by_type.get(kind, 0) + 1
        residues.add(_residue_key(row))
    occupancies = [_clamp01(float(row.get("occupancy") or 0.0)) for row in rows]
    return {"schema_version": "1.0", "mode": mode, "engine": engine, "ligand_resname": ligand_resname, "stride": stride,
            "total_frames": total_frames, "cutoffs_nm": dict(cutoffs_nm),
            "cutoffs_angstrom": {key: round(float(value) * 10.0, 4) for key, value in cutoffs_nm.items()},
            "summary": {"total_interactions": len(rows), "residue_count": len(residues), "by_type": dict(sorted(by_type.items())),
                        "max_occupancy": max(occupancies) if occupancies else None},
            "timeline": list(timeline), "network": network or build_interaction_network([]), "warnings": list(warnings)}
def write_interactions_summary(payload: Mapping[str, Any], out_json: Path) -> Path:
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_json
def _detect_mode(topology_pdb: Path, ligand_resname: str) -> str:
    path = Path(topology_pdb)
    if not path.is_file():
        raise FileNotFoundError(f"topology not found: {path}")
    chains, has_ligand, wanted = set(), False, ligand_resname.upper()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        record = line[:6].strip()
        if record not in ("ATOM", "HETATM"):
            continue
        has_ligand = has_ligand or line[17:20].strip().upper() == wanted
        if record == "ATOM":
            chains.add(line[21:22].strip())  # "" (no chain) must stay distinct from "A"
    return "protein_ligand" if has_ligand else "protein_interface" if len(chains) >= 2 else "single_chain"
@dataclass(frozen=True)
class PdbResidue:
    chain: str
    seq: int
    icode: str
    name: str
    segment: int = 0
def _decode_resseq(raw: str, state: list[Any], group: tuple[int, str, str], resname: str, atom_name: str, altloc: str) -> int:
    text = raw.strip()
    mode, next_seq, cur_group, cur_seq, cur_name, cur_atoms, first_alt = state
    if mode is None and next_seq > 9999 and (text in ("2710", "A000", "****") or text[:1].isalpha()):
        mode = "hex" if text == "2710" else "chimera" if text[:1].isalpha() else "overflow"
    try:
        if mode == "hex":
            seq = int(text, 16)
        elif mode == "chimera" or (mode is None and len(text) == 4 and text[0].isalpha() and text[1:].isalnum()):
            mode = "chimera"
            seq = (int(text, 16) - 0xA000 + 10000 if len(text) == 4 and text[0] in "ABCDEFabcdef"
                   else int(text, 36) - 10 * 36**3 + 10000 if len(text) == 4 and text[0].isalpha() else int(text))
        elif mode is None:
            seq = int(text)
        else:
            raise ValueError
    except ValueError:
        if mode == "chimera" and len(text) == 4 and text[0].isalpha() and text[1:].isalnum():
            seq = int(text, 36) - 10 * 36**3 + 10000
        else:
            mode = "overflow"
            same_alt = bool(altloc and first_alt and altloc != first_alt)
            seq = next_seq if not same_alt and (group != cur_group or resname != cur_name or atom_name in cur_atoms) else cur_seq
    if group != cur_group or seq != cur_seq or (resname != cur_name and not altloc):
        cur_atoms.clear()
        state[2], state[3], state[4], state[6] = group, seq, resname, altloc
    state[0], state[1] = mode, seq + 1
    return seq
def _read_pdb_residues(topology_pdb: Path, *, dedupe_altloc: bool) -> tuple[list[PdbResidue], list[PdbResidue]]:
    # Keep per-residue identity & consecutive-residue altLoc deduplication aligned with OpenMM/MDTraj PdbStructure.
    path = Path(topology_pdb)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], []
    atoms, residues, seen = [], [], set()
    segment, seq_state = 0, [None, 1, None, 0, "", {}, ""]
    for line in text.splitlines():
        record = line[:6].strip().upper()
        if record == "TER":
            segment += 1
            continue
        if record not in ("ATOM", "HETATM") or len(line) < 27:
            continue
        chain, icode, resname = line[21:22].strip(), line[26:27].strip(), line[17:20].strip().upper()
        atom_name, altloc = line[12:16].strip(), line[16:17].strip()
        seq = _decode_resseq(line[22:26], seq_state, (segment, chain, icode), resname, atom_name, altloc)
        cur_atoms = seq_state[5]
        seen_alts = cur_atoms.get(atom_name)
        if dedupe_altloc and seen_alts is not None and altloc not in seen_alts:
            continue
        cur_atoms.setdefault(atom_name, set()).add(altloc)
        residue = PdbResidue(chain, seq, icode, seq_state[4] if dedupe_altloc else resname, segment)
        atoms.append(residue)
        if residue not in seen:
            seen.add(residue)
            residues.append(residue)
    return atoms, residues
def _residue_from_atom_index(atom_table: Sequence[PdbResidue], index: Any) -> PdbResidue | None:
    try:
        position = int(index)
    except (TypeError, ValueError):
        return None
    return atom_table[position] if 0 <= position < len(atom_table) else None
def _residue_index(value: Any) -> int | None:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return None
def _resolve_residue(parsed: tuple[str, int, str, str],
                     residue_table: Sequence[PdbResidue]) -> tuple[str, int, str, str, int]:
    # Fill in what ProLIF/mdtraj lost: empty chain gets its real chain, a unique residue gets its insertion code.
    chain, seq, name, icode = parsed
    if not residue_table:
        return (*parsed, 0)
    matches = [residue for residue in residue_table if residue.seq == seq
               and (not name or residue.name == name) and (not chain or residue.chain == chain)]
    hit = ([r for r in matches if r.icode == icode] if icode else []) or (matches if len(matches) == 1 else [])
    return (hit[0].chain, hit[0].seq, hit[0].name, hit[0].icode, hit[0].segment) if hit else (*parsed, 0)
def _parse_residue_id(raw: Any) -> tuple[str, int, str, str]:
    # Returns (chain, seq, name, icode) from a ProLIF ResidueId, its str() form, or legacy chain:seq[:name[:icode]].
    if not isinstance(raw, str):
        number, name = getattr(raw, "number", None), getattr(raw, "name", None)
        if number is not None and name is not None:
            return (str(getattr(raw, "chain", "") or ""), int(number), str(name),
                    str(getattr(raw, "icode", "") or ""))
    text = str(raw).strip()
    if ":" in text:
        parts = text.split(":")
        if len(parts) >= 2:
            return (parts[0], int(parts[1]), parts[2] if len(parts) > 2 else "", parts[3] if len(parts) > 3 else "")
    match = _RESIDUE_ID.match(text)
    if match:
        return match.group("chain") or "", int(match.group("seq")), match.group("name"), match.group("icode")
    raise ValueError(f"cannot parse residue identifier: {raw!r}")
def _iter_scalars(raw: Any) -> Iterable[float]:
    # Flatten scalars, lists, tuples and numpy arrays of numbers; anything unparsable is silently skipped.
    if raw is None or isinstance(raw, Mapping):
        return
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            yield float(raw)
        except ValueError:
            return
        return
    if hasattr(raw, "__len__"):
        try:
            items = list(raw)
        except TypeError:
            items = None
        if items is not None:
            for item in items:
                yield from _iter_scalars(item)
            return
    try:
        yield float(raw)
    except (TypeError, ValueError):
        return
def _lookup_mapping(mapping: Any, key: Any, as_str: Callable[[Any], Any] = str) -> Any:
    # ProLIF indexes fp.ifp by int frames and ResidueId objects; str() is the stable bridge between versions.
    if not isinstance(mapping, Mapping):
        return None
    try:
        return mapping[key]
    except (KeyError, TypeError):
        pass
    wanted = as_str(key)
    return next((value for candidate, value in mapping.items() if as_str(candidate) == wanted), None)
def _prolif_metadata(fingerprint: Any, frame: int, ligand_id: Any, protein_id: Any,
                     interaction: str) -> list[Mapping[str, Any]]:
    # ProLIF 2.1+ fp.ifp: {frame: {(lig_resid, prot_resid): {interaction: (metadata_dict, ...)}}}
    ifp: Any = getattr(fingerprint, "ifp", None) or {}
    frame_entries = _lookup_mapping(ifp, frame)
    pair_entries = _lookup_mapping(frame_entries, (ligand_id, protein_id),
                                   lambda item: (str(item[0]), str(item[1])) if isinstance(item, tuple) and len(item) == 2 else None)
    entries = _lookup_mapping(pair_entries, interaction)
    if isinstance(entries, Mapping):
        return [entries]
    if isinstance(entries, (list, tuple)):
        return [entry for entry in entries if isinstance(entry, Mapping)]
    return []
def _prolif_distance_nm(entries: Sequence[Mapping[str, Any]]) -> float | None:
    # Metadata stores atom distances in Å: convert the smallest valid value back to nm.
    distances = [value for entry in entries for value in _iter_scalars(entry.get("distance"))
                 if math.isfinite(value) and value > 0]
    return min(distances) / 10.0 if distances else None
def _metadata_protein_references(entry: Mapping[str, Any]) -> Iterable[tuple[float, bool]]:
    # ProLIF 2.1 parent_indices["protein"] is selection-local; legacy metadata["protein"] was system-wide.
    parent = entry.get("parent_indices")
    is_local = isinstance(parent, Mapping) and parent.get("protein") is not None
    raw = parent.get("protein") if is_local else entry.get("protein")
    return ((value, is_local) for value in _iter_scalars(raw))
def _map_protein_atom_index(value: float, protein_indices: Sequence[int] | None) -> int | None:
    local = _residue_index(value)
    if local is None:
        return None
    if protein_indices is None:
        return local  # legacy metadata already refers to system-wide indices
    if 0 <= local < len(protein_indices):
        return _residue_index(protein_indices[local])
    return None
def _assign_resid(residue: Any, value: int, universe: Any) -> bool:
    try:
        residue.resid = value
        return True
    except (AttributeError, TypeError, ValueError):
        pass
    if universe is None:
        return False
    try:
        universe.add_TopologyAttr("resids")
        residue.resid = value
        return True
    except (AttributeError, TypeError, ValueError):
        return False
def _renumber_protein_residues(protein_atoms: Any, atom_table: Sequence[PdbResidue],
                               universe: Any = None) -> dict[int, PdbResidue]:
    # ProLIF's ResidueId has no insertion code, so 42/42A collide; a unique temporary resid separates them and atom_table maps back.
    residues = list(getattr(protein_atoms, "residues", ()) or ())
    mapping: dict[int, PdbResidue] = {}
    for position, residue in enumerate(residues, start=1):
        atoms = list(getattr(residue, "atoms", ()) or ())
        index = _atom_global_index(atoms[0], 0) if atoms else -1
        identity = _residue_from_atom_index(atom_table, index)
        if identity is not None:
            mapping[position] = identity
        _assign_resid(residue, position, universe)
    return mapping
def _prolif_residue_identity(protein_id: Any, entries: Sequence[Mapping[str, Any]], atom_table: Sequence[PdbResidue],
                            residue_table: Sequence[PdbResidue], protein_indices: Sequence[int] | None = None,
                            temp_residues: Mapping[int, PdbResidue] | None = None) -> tuple[str, int, str, str, int] | None:
    # Metadata atom indices pin the exact PDB residue even when ProLIF merged 42 and 42A into one ResidueId.
    for entry in entries:
        for value, selection_local in _metadata_protein_references(entry):
            index = _map_protein_atom_index(value, protein_indices) if selection_local else _residue_index(value)
            residue = _residue_from_atom_index(atom_table, index)
            if residue is not None:
                return residue.chain, residue.seq, residue.name, residue.icode, residue.segment
    try:
        parsed = _parse_residue_id(protein_id)
    except ValueError:
        return None
    identity = temp_residues.get(parsed[1]) if temp_residues else None
    if identity is not None:
        return identity.chain, identity.seq, identity.name, identity.icode, identity.segment
    return _resolve_residue(parsed, residue_table)
def _element_symbol(atom: Any) -> str:
    element = getattr(atom, "element", None)
    symbol = getattr(element, "symbol", element) if element is not None else None
    if symbol is None or not str(symbol).strip():
        symbol = re.sub(r"\d", "", str(getattr(atom, "name", "")))
    return str(symbol).strip().upper()
def _atom_global_index(atom: Any, position: int) -> int:
    try:
        return int(getattr(atom, "index", position))
    except (TypeError, ValueError):
        return int(position)
def _template_bond_graph(molecule: Any, atoms: Sequence[Any]) -> tuple[list[tuple[int, int]], list[float], list[int]]:
    # The template is indexed 0..N-1 locally; the topology carries system-wide atom indices.
    global_indices = [_atom_global_index(atom, position) for position, atom in enumerate(atoms)]
    pairs = [(global_indices[b.GetBeginAtomIdx()], global_indices[b.GetEndAtomIdx()]) for b in molecule.GetBonds()]
    orders = [float(bond.GetBondTypeAsDouble()) for bond in molecule.GetBonds()]
    return pairs, orders, global_indices
def _existing_bond_graph(universe: Any) -> list[tuple[tuple[int, int], float]]:
    # Writing "bonds" replaces the whole attribute, so CONECT/force-field bonds are snapshotted first (order 1.0).
    bonds, entries = getattr(universe, "bonds", None), []
    if bonds is None:
        return []
    try:
        for bond in bonds:
            indices = tuple(int(index) for index in getattr(bond, "indices", ()))
            if len(indices) == 2:
                order = getattr(bond, "order", None)
                entries.append((indices, 1.0 if order is None else float(order)))
    except (AttributeError, TypeError, ValueError):
        pass
    if entries:
        return entries
    to_indices = getattr(bonds, "to_indices", None)  # array-only back-ends expose no Bond wrappers
    try:
        return [(tuple(int(index) for index in pair), 1.0) for pair in to_indices()] if callable(to_indices) else []
    except (AttributeError, TypeError, ValueError):
        return []
def _merge_bond_graph(existing: Sequence[tuple[tuple[int, int], float]], pairs: Sequence[tuple[int, int]],
                      orders: Sequence[float]) -> tuple[list[tuple[int, int]], list[float]]:
    merged: dict[frozenset[int], tuple[tuple[int, int], float]] = {}
    for pair, order in (*existing, *zip(pairs, orders)):  # a template bond overrides an inferred duplicate
        merged[frozenset(pair)] = (tuple(pair), float(order))
    return [pair for pair, _ in merged.values()], [order for _, order in merged.values()]
def _bonds_topology_attr(pairs: Sequence[tuple[int, int]], orders: Sequence[float]) -> Any:
    # 2.10.0 rejects add_TopologyAttr("bondorders", ...) and has no order setter: write one topologyattrs.Bonds.
    try:
        from MDAnalysis.core.topologyattrs import Bonds
    except (ImportError, AttributeError):
        return None
    values = [tuple(pair) for pair in pairs]
    for kwargs in ({"order": list(orders), "types": list(orders), "guessed": False}, {"order": list(orders)}):
        try:
            return Bonds(values, **kwargs)
        except (TypeError, ValueError):
            continue
    return None
def _guess_selection_bonds(universe: Any, selection: Any, indices: Sequence[int] | None, *, force: bool = False) -> list[tuple[tuple[int, int], float]]:
    existing = _existing_bond_graph(universe)
    group_ids = None if indices is None else {int(index) for index in indices}
    bonded = {atom for (a, b), _ in existing if group_ids and a in group_ids and b in group_ids for atom in (a, b)}
    needs_guess = force or (not existing if group_ids is None else len(group_ids) >= 2 and not group_ids.issubset(bonded))
    if needs_guess:
        target = selection if selection is not None else getattr(universe, "atoms", None)
        guess = getattr(target, "guess_bonds", None) or getattr(getattr(universe, "atoms", None), "guess_bonds", None)
        if callable(guess):
            try:
                guess()
            except Exception:  # noqa: BLE001
                pass
            existing = _existing_bond_graph(universe)
    return existing
def _write_topology_bonds(universe: Any, pairs: Sequence[tuple[int, int]], orders: Sequence[float],
                          ligand_indices: Sequence[int] | None = None,
                          protein_indices: Sequence[int] | None = None, protein_atoms: Any = None) -> bool:
    if protein_indices is not None:
        existing = _guess_selection_bonds(universe, protein_atoms, protein_indices)
    else:
        existing = _existing_bond_graph(universe)
        ligand = None if ligand_indices is None else {int(index) for index in ligand_indices}
        has_other = bool(existing) if ligand is None else any(not (first in ligand and second in ligand) for (first, second), _order in existing)
        if not has_other:
            existing = _guess_selection_bonds(universe, protein_atoms, None, force=True)
    merged_pairs, merged_orders = _merge_bond_graph(existing, pairs, orders)
    bonds_attr = _bonds_topology_attr(merged_pairs, merged_orders)
    if bonds_attr is not None:
        for write in (getattr(universe, "add_TopologyAttr", None), getattr(universe, "add_bonds", None)):
            try:
                write(bonds_attr)
            except (AttributeError, TypeError, ValueError):
                continue
            if _bond_orders_persisted(universe, merged_pairs, merged_orders):
                return True
    try:
        universe.add_TopologyAttr("bonds", merged_pairs)
    except (AttributeError, TypeError, ValueError):
        return False
    try:
        universe.add_TopologyAttr("bondorders", merged_orders)
    except (AttributeError, TypeError, ValueError):
        pass
    return _bond_orders_persisted(universe, merged_pairs, merged_orders)
def _bond_orders_persisted(universe: Any, pairs: Sequence[tuple[int, int]], orders: Sequence[float]) -> bool:
    bonds = getattr(universe, "bonds", None)
    expected = {frozenset(pair): float(order) for pair, order in zip(pairs, orders)}
    if bonds is None or not expected:
        return False
    found: dict[frozenset[int], float] = {}
    try:
        for bond in bonds:
            key = frozenset(int(index) for index in getattr(bond, "indices", ()))
            order = getattr(bond, "order", None)
            if key in expected and order is not None:
                found[key] = float(order)
    except (AttributeError, TypeError, ValueError):
        return False
    return all(key in found and abs(found[key] - value) <= 1e-6 for key, value in expected.items())
def _apply_template_bond_orders(ligand_atoms: Any, template_sdf: Path, universe: Any = None,
                                protein_atoms: Any = None, protein_indices: Sequence[int] | None = None) -> bool:
    from rdkit import Chem
    molecule = Chem.MolFromMolFile(str(template_sdf), removeHs=False, sanitize=False)
    if molecule is None:
        raise ValueError(f"cannot read ligand template SDF: {template_sdf}")
    atoms = list(ligand_atoms)
    if molecule.GetNumAtoms() != len(atoms):
        raise ValueError(f"ligand template has {molecule.GetNumAtoms()} atoms; selection has {len(atoms)}")
    if [a.GetSymbol().strip().upper() for a in molecule.GetAtoms()] != [_element_symbol(a) for a in atoms]:
        raise ValueError("ligand template atom order does not match the trajectory selection")
    pairs, orders, ligand_indices = _template_bond_graph(molecule, atoms)
    if not pairs:
        return False
    universe = universe if universe is not None else getattr(ligand_atoms, "universe", None)
    if universe is not None and _write_topology_bonds(universe, pairs, orders, ligand_indices, protein_indices, protein_atoms):
        return True
    wanted, assigned = {frozenset(pair): order for pair, order in zip(pairs, orders)}, 0
    for bond in getattr(ligand_atoms, "bonds", None) or ():
        order = wanted.get(frozenset(tuple(getattr(bond, "indices", ()))))
        if order is not None:
            try:
                bond.order = order
                assigned += 1
            except (AttributeError, TypeError, ValueError):
                pass
    return _bond_orders_persisted(universe, pairs, orders) if universe is not None else assigned > 0
def _prolif_parameters(config: InteractionConfig, interactions: Sequence[str],
                       water: Any = None) -> dict[str, dict[str, Any]]:
    # Thresholds are configured in nm and handed to ProLIF in Å; WaterBridge only accepts its water AtomGroup.
    return {name: ({"water": water} if name == "WaterBridge"
                   else {"distance": round(float(getattr(config, PROLIF_DISTANCE_PARAMETER[name])) * 10.0, 4)})
            for name in interactions if name == "WaterBridge" or name in PROLIF_DISTANCE_PARAMETER}
def _prepare_mda_topology_pdb(source: Path, atom_table: Sequence[PdbResidue], tmp_dir: Path) -> Path:
    # MDAnalysis 2.10 merges identical (chain, seq, name) residues across TER before ProLIF sees them; a temp copy with unique resSeq/icode/segid keeps them apart.
    if not any(r.segment > 0 for r in atom_table) and len(set(atom_table)) == len({(r.chain, r.seq) for r in atom_table}):
        return source
    out, cursor, seq_id, previous = [], 0, 0, None
    for line in Path(source).read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True):
        if line[:6].strip().upper() in ("ATOM", "HETATM") and len(line) >= 27:
            residue = atom_table[cursor]
            cursor += 1
            if residue != previous:
                seq_id, previous = seq_id + 1, residue
            body = line.rstrip("\r\n").ljust(76)
            ending = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
            res_seq, seg_id = (seq_id - 1) % 9999 + 1, f"S{(seq_id - 1) // 9999:03X}"
            line = f"{body[:22]}{res_seq:4d} {body[27:72]}{seg_id}{body[76:]}{ending}"
        out.append(line)
    mda_pdb = Path(tmp_dir) / "mda_topology.pdb"
    mda_pdb.write_text("".join(out), encoding="utf-8")
    return mda_pdb
def _selection_indices(selection: Any) -> tuple[int, ...] | None:
    raw = getattr(selection, "indices", None)
    return (tuple(int(index) for index in raw) or None) if raw is not None else None
def _extract_with_prolif(topology_pdb, trajectory_path, config, ligand_template_sdf=None):
    import MDAnalysis as mda
    import prolif as plf
    warnings: list[str] = []
    atom_table, residue_table = _read_pdb_residues(Path(topology_pdb), dedupe_altloc=False)
    with tempfile.TemporaryDirectory() as tmp_dir:
        mda_pdb = _prepare_mda_topology_pdb(Path(topology_pdb), atom_table, Path(tmp_dir))
        universe = mda.Universe(str(mda_pdb), str(trajectory_path))
    ligand, protein = universe.select_atoms(f"resname {config.ligand_resname}"), universe.select_atoms("protein")
    if ligand.n_atoms == 0 or protein.n_atoms == 0:
        raise ValueError("ligand or protein selection is empty")
    protein_indices, ligand_indices = _selection_indices(protein), _selection_indices(ligand)
    temp_residues = _renumber_protein_residues(protein, atom_table, universe)
    if ligand_template_sdf:
        if not _apply_template_bond_orders(ligand, ligand_template_sdf, universe, protein, protein_indices):
            warnings.append("ligand template supplied no bond orders; ProLIF infers them from the trajectory")
    else:
        _guess_selection_bonds(universe, protein, protein_indices)
        _guess_selection_bonds(universe, ligand, ligand_indices)
    frame_indices = list(range(0, len(universe.trajectory), max(1, int(config.stride))))
    interactions, water = list(DEFAULT_PROLIF_INTERACTIONS), None
    if config.water_resname:
        water = universe.select_atoms(f"resname {config.water_resname}")
        if water.n_atoms:
            _guess_selection_bonds(universe, water, _selection_indices(water))
            interactions.append("WaterBridge")
        else:
            water = None
            warnings.append(f"water selection {config.water_resname!r} is empty; WaterBridge disabled")
    fingerprint = plf.Fingerprint(interactions, parameters=_prolif_parameters(config, interactions, water))
    frames = universe.trajectory[frame_indices]
    fingerprint.run(frames, ligand, protein)  # the water AtomGroup travels via parameters={"WaterBridge": ...}
    suffix = Path(trajectory_path).suffix.lower()
    times = {index: _frame_time_ps(universe.trajectory[index], index, suffix, config, warnings)
             for index in frame_indices}
    contacts: list[FrameContact] = []
    for frame, row in fingerprint.to_dataframe().iterrows():
        raw_frame = int(frame)
        for column, value in row.items():
            if not value:
                continue
            # ProLIF 2.1+ columns are 3-tuples (ligand, protein, interaction); the row index is a real frame.
            if not isinstance(column, tuple) or len(column) < 3:
                continue
            ligand_id, protein_id, interaction = column[0], column[-2], column[-1]
            kind = normalize_interaction_type(str(interaction))
            if kind is None:
                continue
            entries = _prolif_metadata(fingerprint, raw_frame, ligand_id, protein_id, str(interaction))
            identity = _prolif_residue_identity(protein_id, entries, atom_table, residue_table,
                                                protein_indices, temp_residues)
            if identity is None:
                continue
            chain, seq, name, icode, segment = identity
            contacts.append(FrameContact(raw_frame, times.get(raw_frame, 0.0), chain, seq, name, kind,
                                         _prolif_distance_nm(entries), icode, segment))
    return contacts, times, warnings
def _heavy(atom: Any) -> bool:
    return _element_symbol(atom) != "H"
def _scalar_time(value: Any, default: float = 0.0) -> float:
    # MDTraj may hand back a one-element array; NumPy 2.x rejects float(array([2.5])): unwrap to a scalar first.
    reshape = getattr(value, "reshape", None)
    if callable(reshape):
        try:
            value = reshape(-1)[0]
        except (AttributeError, IndexError, TypeError, ValueError):
            pass
    elif isinstance(value, (list, tuple)) and len(value) == 1:
        value = value[0]
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
def _frame_time_ps(frame: Any, raw_frame: int, suffix: str, config: InteractionConfig, warnings: list[str]) -> float:
    if config.frame_dt_ps is not None:
        return float(raw_frame) * float(config.frame_dt_ps)
    if suffix == ".dcd":
        message = "DCD frames carry frame numbers, not physical times; set frame_dt_ps for real time_ps"
        if message not in warnings:
            warnings.append(message)
        return float(raw_frame)
    return _scalar_time(getattr(frame, "time", None))
def _mdtraj_resname(atom: Any, atom_table: Sequence[PdbResidue], raw_names: Sequence[str] | None = None) -> str:
    index = _residue_index(getattr(atom, "index", None))
    if raw_names is not None and index is not None and 0 <= index < len(raw_names):
        return raw_names[index]
    identity = _residue_from_atom_index(atom_table, index)
    return identity.name if identity is not None else str(getattr(getattr(atom, "residue", None), "name", "")).upper()
def _extract_with_mdtraj_fallback(topology_pdb, trajectory_path, config, ligand_template_sdf=None, *,
                                  mode="protein_ligand"):
    import mdtraj as md
    trajectory = md.load(str(trajectory_path), top=str(topology_pdb), stride=max(1, int(config.stride)))
    topology, warnings = trajectory.topology, []
    # mdtraj 1.10.3 renames residues like ADE -> A and drops altLocs/icodes; match raw PDB residue names per atom.
    atom_table, residue_table = _read_pdb_residues(Path(topology_pdb), dedupe_altloc=True)
    load_pdb, raw_names = getattr(md, "load_pdb", None), None
    if callable(load_pdb):
        try:
            raw_top = load_pdb(str(topology_pdb), frame=0, no_boxchk=True, standard_names=False).topology
            if len(list(raw_top.atoms)) == len(list(topology.atoms)):
                raw_names = [str(a.residue.name).upper() for a in raw_top.atoms]
        except Exception:  # noqa: BLE001
            raw_names = None
    wanted = str(config.ligand_resname).strip().upper()
    ligand_atoms = [a.index for a in topology.atoms if _heavy(a) and _mdtraj_resname(a, atom_table, raw_names) == wanted]
    protein_atoms = [a.index for a in topology.atoms
                     if a.residue.is_protein and _heavy(a) and _mdtraj_resname(a, atom_table, raw_names) != wanted]
    if mode == "protein_interface":
        chains: dict[str, list[int]] = {}
        for residue in (item for item in topology.residues if item.is_protein):
            chains.setdefault(getattr(getattr(residue, "chain", None), "chain_id", "") or "", []).extend(
                a.index for a in residue.atoms if _heavy(a))
        if len(chains) < 2:
            raise ValueError("protein interface analysis needs at least two protein chains")
        anchor = sorted(chains)[0]
        ligand_atoms, protein_atoms = chains[anchor], [i for n in chains if n != anchor for i in chains[n]]
    if not ligand_atoms or not protein_atoms:
        raise ValueError("ligand or interface selection is empty after heavy-atom filtering")
    pairs = topology.select_pairs(selection1=ligand_atoms, selection2=protein_atoms)
    suffix, stride = Path(trajectory_path).suffix.lower(), max(1, int(config.stride))
    contacts, times = [], {}
    for sample in range(int(trajectory.n_frames)):
        raw_frame, frame = sample * stride, trajectory[sample]
        distances = md.compute_distances(frame, pairs, periodic=frame.unitcell_vectors is not None)[0]
        best: dict[tuple[str, int, str, str, int], float] = {}
        for position, (_, protein_index) in enumerate(pairs):
            residue = topology.atom(int(protein_index)).residue
            identity = _residue_from_atom_index(atom_table, protein_index)
            if identity is not None:
                key = (identity.chain, identity.seq, identity.icode, identity.name, identity.segment)
            else:
                chain = getattr(getattr(residue, "chain", None), "chain_id", "") or ""
                resolved = _resolve_residue((chain, int(residue.resSeq), residue.name, ""), residue_table)
                key = (resolved[0], resolved[1], resolved[3], resolved[2], resolved[4])  # (chain, seq, icode, name, seg)
            value = float(distances[position])
            if value <= config.contact_cutoff_nm and value < best.get(key, float("inf")):
                best[key] = value
        times[raw_frame] = _frame_time_ps(frame, raw_frame, suffix, config, warnings)
        contacts.extend(FrameContact(raw_frame, times[raw_frame], chain, seq, name, "vdw_contact", value, icode,
                                     segment) for (chain, seq, icode, name, segment), value in best.items())
    return contacts, times, warnings
def analyze_trajectory(topology_pdb: Path, trajectory_path: Path, *, output_contacts_csv: Path, output_summary_json: Path,
                       config: InteractionConfig | None = None, ligand_template_sdf: Path | None = None,
                       frame_extractor: Callable[..., Any] | None = None) -> dict[str, Any]:
    config = config or InteractionConfig()
    topology, trajectory = Path(topology_pdb), Path(trajectory_path)
    if not topology.is_file():
        raise FileNotFoundError(f"topology not found: {topology}")
    if not trajectory.is_file():
        raise FileNotFoundError(f"trajectory not found: {trajectory}")
    stride, warnings = max(1, int(config.stride)), []
    mode = (config.mode if config.mode in ("protein_ligand", "protein_interface")
            else _detect_mode(topology, config.ligand_resname))
    cutoffs = {"hbond": config.hbond_cutoff_nm, "hydrophobic": config.hydrophobic_cutoff_nm,
               "salt_bridge": config.salt_bridge_cutoff_nm, "contact": config.contact_cutoff_nm}
    if mode == "single_chain":
        warnings.append("no ligand residue and fewer than two protein chains; analysis skipped")
        payload = build_summary_payload(mode=mode, engine="skipped", ligand_resname=config.ligand_resname,
                                        stride=stride, total_frames=0, cutoffs_nm=cutoffs, warnings=warnings)
        write_contacts_csv([], output_contacts_csv)
        write_interactions_summary(payload, output_summary_json)
        return payload
    engine = "injected"
    if frame_extractor is not None:
        result = frame_extractor(topology, trajectory, config, ligand_template_sdf)
        contacts, times = list(result[0]), {int(key): _scalar_time(value) for key, value in dict(result[1]).items()}
        warnings.extend(result[2] if len(result) > 2 else ())
    elif mode == "protein_interface":
        contacts, times, backend_warnings = _extract_with_mdtraj_fallback(
            topology, trajectory, config, ligand_template_sdf, mode=mode)
        engine, warnings = "mdtraj", warnings + backend_warnings
    else:
        try:
            contacts, times, backend_warnings = _extract_with_prolif(topology, trajectory, config, ligand_template_sdf)
            engine, warnings = "prolif", warnings + backend_warnings
        except Exception as exc:  # noqa: BLE001 - any back-end failure degrades
            warnings.append(f"prolif extraction unavailable: {exc}; falling back to mdtraj")
            try:
                contacts, times, backend_warnings = _extract_with_mdtraj_fallback(
                    topology, trajectory, config, ligand_template_sdf, mode=mode)
                engine, warnings = "mdtraj", warnings + backend_warnings
            except Exception as fallback_exc:  # noqa: BLE001
                raise RuntimeError(f"interaction extraction failed (prolif: {exc}; mdtraj: {fallback_exc})") from fallback_exc
    if engine in ("prolif", "mdtraj"):
        cutoffs = ({"contact": cutoffs["contact"]} if engine == "mdtraj"
                   else {key: value for key, value in cutoffs.items() if key != "contact"})
    total_frames = len(times) if times else max((int(c.frame) for c in contacts), default=-1) + 1
    rows = aggregate_contacts(contacts, total_frames=total_frames, min_occupancy=config.min_occupancy)
    network = build_interaction_network(rows, anchor_id=config.ligand_resname if mode == "protein_ligand" else "INTERFACE",
                                        anchor_kind="ligand" if mode == "protein_ligand" else "interface", min_edge_occupancy=config.min_occupancy)
    payload = build_summary_payload(mode=mode, engine=engine, ligand_resname=config.ligand_resname, stride=stride, total_frames=total_frames, cutoffs_nm=cutoffs, rows=rows, timeline=build_timeline(contacts, frame_times_ps=times), network=network, warnings=warnings)
    write_contacts_csv(rows, output_contacts_csv)
    write_interactions_summary(payload, output_summary_json)
    return payload
