"""相互作用分析内核的离线回归测试。

重依赖（MDAnalysis / ProLIF / mdtraj）以最小假模块注入，覆盖评审指出的
Blocker/Major：ProLIF 2.x 的 AtomGroup-per-frame + 三元组 MultiIndex、
nm→Å 阈值、Å→nm 距离、水桥显式开启、mdtraj 重原子/周期/步长/icode、
缺失输入报错、无 networkx 的 BFS 回退、网络边占用率语义。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "deploy" / "model-images" / "k8s" / "gromacs" / "interactions_analysis.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("md_interactions_analysis_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


interactions = _load_module()


def _pdb_line(serial: int, atom: str, resname: str, chain: str, seq: int, icode: str = " ",
              altloc: str = " ", record: str = "ATOM", element: str = "C") -> str:
    return (f"{record:<6s}{serial:5d} {atom:4s}{altloc}{resname:3s} {chain}{seq:4d}{icode}"
            f"   {10.0:8.3f}{10.0:8.3f}{10.0:8.3f}  1.00 20.00          {element:>2s}")


def _write_topology(path: Path, *, with_ligand: bool, two_chains: bool = False, icode: str = " ") -> Path:
    lines = [_pdb_line(1, "CA", "ALA", "A", 10), _pdb_line(2, "CB", "ALA", "A", 10, icode)]
    if two_chains:
        lines.append(_pdb_line(3, "CA", "GLY", "B", 20))
    if with_ligand:
        lines.append(_pdb_line(4, "C1", "LIG", "A", 901))
    path.write_text("\n".join(lines + ["END"]) + "\n", encoding="utf-8")
    return path


def _contact(frame, kind="hbond_donor", *, seq=10, name="ALA", distance=0.3, chain="A", icode="", time=None,
             segment=0):
    return interactions.FrameContact(frame, float(frame) * 10.0 if time is None else time,
                                     chain, seq, name, kind, distance, icode, segment)


# ---------------------------------------------------------------------------
# 假 MDAnalysis / ProLIF
# ---------------------------------------------------------------------------


class FakeMdaAtom:
    def __init__(self, index, element="C", name="C1"):
        self.index, self.element, self.name = index, element, name
        self.residue = None


class FakeMdaResidue:
    """Same writable `resid` surface MDAnalysis residues expose; ProLIF keys residues by it."""

    def __init__(self, resid, atoms):
        self.resid = resid
        self._atoms = list(atoms)
        for atom in self._atoms:
            atom.residue = self

    @property
    def atoms(self):
        return list(self._atoms)


class FakeAtomGroup:
    def __init__(self, atoms):
        self._atoms = list(atoms)
        self.n_atoms = len(self._atoms)

    def __iter__(self):
        return iter(self._atoms)

    def __getitem__(self, index):
        return self._atoms[index]

    @property
    def indices(self):
        return [atom.index for atom in self._atoms]

    @property
    def residues(self):
        unique = []
        for atom in self._atoms:
            residue = getattr(atom, "residue", None)
            if residue is not None and residue not in unique:
                unique.append(residue)
        return unique


class FakeTrajectory:
    def __init__(self, times):
        self._times = list(times)

    def __len__(self):
        return len(self._times)

    def __getitem__(self, index):
        if isinstance(index, list):
            return [self._times[i] for i in index]
        if isinstance(index, slice):
            return self._times[index]
        return SimpleNamespace(time=self._times[index])


class FakeUniverse:
    # Ligand atoms first, then one protein atom per residue; the PDB written by each test follows this order.
    ligand_global = (0, 1)
    protein_residues = ((10, (2,)), (20, (3,)), (30, (4,)))

    def __init__(self, _topology=None, _trajectory=None):
        self.trajectory = FakeTrajectory([0.0, 100.0, 200.0])
        self.topology_attrs = {}
        ligand_atoms = [FakeMdaAtom(index) for index in self.ligand_global]
        residues = [FakeMdaResidue(resid, [FakeMdaAtom(index, name="CA") for index in indices])
                    for resid, indices in self.protein_residues]
        self.residues = residues
        protein_atoms = [atom for residue in residues for atom in residue.atoms]
        self.selections = {"resname LIG": FakeAtomGroup(ligand_atoms), "protein": FakeAtomGroup(protein_atoms)}

    def select_atoms(self, query):
        return self.selections.get(query, FakeAtomGroup([]))

    def add_TopologyAttr(self, name, values=None, orders=None):
        if name == "bonds":
            pairs = list(values or ())
            order_values = list(orders) if orders is not None else [None] * len(pairs)
            self.topology_attrs["bonds"] = [FakeBond(pair, order) for pair, order in zip(pairs, order_values)]
        else:
            self.topology_attrs[name] = values

    @property
    def bonds(self):
        return self.topology_attrs.get("bonds")


class FakeResidueId:
    """Same surface as prolif.residue.ResidueId: attributes plus a "ALA42.A" style __str__."""

    def __init__(self, name, number, chain=""):
        self.name, self.number, self.chain = name, number, chain

    def __str__(self):
        return f"{self.name}{self.number}{f'.{self.chain}' if self.chain else ''}"


class _FakeRow:
    def __init__(self, columns, values):
        self._pairs = list(zip(columns, values))

    def items(self):
        return iter(self._pairs)


class _FakeDataFrame:
    def __init__(self, rows, *, index, columns):
        self._rows = list(rows)
        self._index = list(index)
        self._columns = list(columns)

    def iterrows(self):
        for frame, values in zip(self._index, self._rows):
            yield frame, _FakeRow(self._columns, values)


class FakeFingerprint:
    """Mirrors ProLIF 2.1+: VdWContact has no `distance`, WaterBridge takes its water AtomGroup via parameters."""

    instances: list["FakeFingerprint"] = []

    def __init__(self, interactions_list, parameters=None):
        self.interactions = list(interactions_list)
        self.parameters = parameters or {}
        # ProLIF 2.x raises TypeError for these two calling conventions; the fake must do the same.
        if "distance" in self.parameters.get("VdWContact", {}):
            raise TypeError("VdWContact() got an unexpected keyword argument 'distance'")
        if "WaterBridge" in self.interactions and "water" not in self.parameters.get("WaterBridge", {}):
            raise TypeError("WaterBridge() missing 1 required positional argument: 'water'")
        self.ifp = {0: {("LIG1", "ALA10.A"): {"HBDonor": ({"distance": 3.0, "protein": [2]},)}}}
        self.run_args = None
        FakeFingerprint.instances.append(self)

    def run(self, frames, ligand, protein, **kwargs):
        if "water" in kwargs:
            raise TypeError("run() got an unexpected keyword argument 'water'")
        self.run_args = (frames, ligand, protein)

    def to_dataframe(self):
        columns = [("LIG1", "ALA10.A", "HBDonor"), ("LIG1", "GLY20.A", "Hydrophobic")]
        return _FakeDataFrame([[True, False], [True, True]], index=[0, 2], columns=columns)


def _install_prolif(monkeypatch):
    FakeFingerprint.instances.clear()
    monkeypatch.setitem(sys.modules, "MDAnalysis", SimpleNamespace(Universe=FakeUniverse))
    monkeypatch.setitem(sys.modules, "prolif", SimpleNamespace(Fingerprint=FakeFingerprint))


def test_prolif_uses_atomgroups_per_frame_and_parses_multiiindex(monkeypatch, tmp_path):
    _install_prolif(monkeypatch)
    topology, trajectory = tmp_path / "top.pdb", tmp_path / "traj.xtc"
    topology.write_text("", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    contacts, times, warnings = interactions._extract_with_prolif(topology, trajectory, interactions.InteractionConfig())

    fingerprint = FakeFingerprint.instances[-1]
    frames, ligand, protein = fingerprint.run_args
    # 帧列表 + 每帧 AtomGroup（绝不是静态 Molecule）且默认不传 water（传了替身会抛 TypeError）
    assert frames == [0.0, 100.0, 200.0] and len(frames) == 3
    assert isinstance(ligand, FakeAtomGroup) and isinstance(protein, FakeAtomGroup)
    assert "WaterBridge" not in fingerprint.interactions and "WaterBridge" not in fingerprint.parameters
    # nm → Å 阈值；VdWContact 不接受 distance（替身收到会抛 TypeError）
    assert fingerprint.parameters["HBDonor"]["distance"] == 3.5
    assert fingerprint.parameters["Hydrophobic"]["distance"] == 4.5
    # VdWContact(tolerance, vdwradii, preset) 根本没有 distance 参数：一律走 ProLIF 默认，不传任何关键字
    assert "VdWContact" in fingerprint.interactions and "VdWContact" not in fingerprint.parameters
    # 3 元组列解析 + 真实帧号 + Å → nm（fp.ifp 为 {(lig, prot): {interaction: ({distance},)}}）
    ala = next(c for c in contacts if c.residue_name == "ALA")
    gly = next(c for c in contacts if c.residue_name == "GLY")
    assert (ala.frame, ala.interaction_type, ala.distance_nm) == (0, "hbond_donor", 0.3)
    assert (gly.frame, gly.interaction_type, gly.distance_nm) == (2, "hydrophobic", None)
    assert times == {0: 0.0, 1: 100.0, 2: 200.0}
    assert warnings == []


def test_prolif_honours_stride_and_opt_in_water(monkeypatch, tmp_path):
    _install_prolif(monkeypatch)

    class WaterUniverse(FakeUniverse):
        def __init__(self, *args):
            super().__init__(*args)
            self.selections["resname SOL"] = FakeAtomGroup([object()])

    monkeypatch.setitem(sys.modules, "MDAnalysis", SimpleNamespace(Universe=WaterUniverse))
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.xtc"
    topology.write_text("", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    config = interactions.InteractionConfig(stride=2, water_resname="SOL")
    contacts, times, warnings = interactions._extract_with_prolif(topology, trajectory, config)

    fingerprint = FakeFingerprint.instances[-1]
    assert "WaterBridge" in fingerprint.interactions
    # 水分子 AtomGroup 只能通过 parameters 传入；fp.run 不接收 water（替身会拒绝）
    water = fingerprint.parameters["WaterBridge"]["water"]
    assert isinstance(water, FakeAtomGroup) and water.n_atoms == 1
    assert fingerprint.run_args[0] == [0.0, 200.0]
    assert times == {0: 0.0, 2: 200.0}
    assert warnings == []
    assert contacts and all(contact.frame in (0, 2) for contact in contacts)


def test_prolif_empty_water_selection_disables_waterbridge(monkeypatch, tmp_path):
    _install_prolif(monkeypatch)
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.xtc"
    topology.write_text("", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    config = interactions.InteractionConfig(water_resname="SOL")
    _contacts, _times, warnings = interactions._extract_with_prolif(topology, trajectory, config)
    assert "WaterBridge" not in FakeFingerprint.instances[-1].interactions
    assert "WaterBridge" not in FakeFingerprint.instances[-1].parameters
    assert any("WaterBridge disabled" in item for item in warnings)


def test_prolif_ifp_residue_pair_keys_accept_residueid_objects(monkeypatch, tmp_path):
    class ResidueIdFingerprint(FakeFingerprint):
        def __init__(self, interactions_list, parameters=None):
            super().__init__(interactions_list, parameters)
            self.ifp = {0: {(FakeResidueId("LIG", 1), FakeResidueId("ALA", 10, "A")): {
                "HBDonor": ({"distance": 3.0}, {"distance": 2.4}),
                "Hydrophobic": ({"distance": [4.0, 1.8]},)}}}

        def to_dataframe(self):
            columns = [("LIG1", "ALA10.A", "HBDonor"), ("LIG1", "ALA10.A", "Hydrophobic")]
            return _FakeDataFrame([[True, True]], index=[0], columns=columns)

    _install_prolif(monkeypatch)
    monkeypatch.setitem(sys.modules, "prolif", SimpleNamespace(Fingerprint=ResidueIdFingerprint))
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.xtc"
    topology.write_text("", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    contacts, _times, _warnings = interactions._extract_with_prolif(
        topology, trajectory, interactions.InteractionConfig())
    by_type = {contact.interaction_type: contact.distance_nm for contact in contacts}
    assert by_type == {"hbond_donor": 0.24, "hydrophobic": 0.18}  # Å 列表取最小，再 /10


def test_prolif_keeps_contacts_on_an_empty_chain(monkeypatch, tmp_path):
    class EmptyChainFingerprint(FakeFingerprint):
        def __init__(self, interactions_list, parameters=None):
            super().__init__(interactions_list, parameters)
            self.ifp = {0: {("LIG1", "ALA42"): {"HBDonor": ({"distance": 3.0}, )}}}

        def to_dataframe(self):
            columns = [("LIG1", "ALA42", "HBDonor")]  # 空链没有点号
            return _FakeDataFrame([[True]], index=[0], columns=columns)

    _install_prolif(monkeypatch)
    monkeypatch.setitem(sys.modules, "prolif", SimpleNamespace(Fingerprint=EmptyChainFingerprint))
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.xtc"
    topology.write_text("\n".join([_pdb_line(1, "CA", "ALA", " ", 42)]) + "\n", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    contacts, _times, _warnings = interactions._extract_with_prolif(
        topology, trajectory, interactions.InteractionConfig())
    assert [(contact.residue_chain, contact.residue_seq, contact.residue_name) for contact in contacts] == \
        [("", 42, "ALA")]


def test_prolif_metadata_atom_indices_separate_insertion_codes(monkeypatch, tmp_path):
    class InsertionCodeFingerprint(FakeFingerprint):
        def __init__(self, interactions_list, parameters=None):
            super().__init__(interactions_list, parameters)
            # ProLIF 把 42 与 42A 合并成一个 ResidueId；metadata 的原子下标仍能区分它们
            self.ifp = {0: {("LIG1", "ALA42.A"): {
                "HBDonor": ({"distance": 3.0, "protein": [1]},),
                "Hydrophobic": ({"distance": 3.6, "protein": [2]},)}}}

        def to_dataframe(self):
            columns = [("LIG1", "ALA42.A", "HBDonor"), ("LIG1", "ALA42.A", "Hydrophobic")]
            return _FakeDataFrame([[True, True]], index=[0], columns=columns)

    _install_prolif(monkeypatch)
    monkeypatch.setitem(sys.modules, "prolif", SimpleNamespace(Fingerprint=InsertionCodeFingerprint))
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.xtc"
    topology.write_text("\n".join([_pdb_line(1, "C1", "LIG", "A", 901), _pdb_line(2, "CA", "ALA", "A", 42),
                                   _pdb_line(3, "CA", "ALA", "A", 42, "A")]) + "\n", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    contacts, _times, _warnings = interactions._extract_with_prolif(
        topology, trajectory, interactions.InteractionConfig())
    icodes = {(contact.interaction_type, contact.residue_icode) for contact in contacts}
    assert icodes == {("hbond_donor", ""), ("hydrophobic", "A")}


def _prolif21_fingerprint(*, protein_key, columns, entries):
    """Strict ProLIF 2.1 metadata: atom indices only under parent_indices, local to the protein selection."""

    class Prolif21Fingerprint(FakeFingerprint):
        def __init__(self, interactions_list, parameters=None):
            super().__init__(interactions_list, parameters)
            self.ifp = {0: {("LIG1", protein_key): entries}}
            self.protein_resids = None

        def run(self, frames, ligand, protein, **kwargs):
            # ProLIF groups protein residues by resid; they must already be unique before the run.
            self.protein_resids = [residue.resid for residue in protein.residues]
            super().run(frames, ligand, protein, **kwargs)

        def to_dataframe(self):
            return _FakeDataFrame([[True] * len(columns)], index=[0], columns=columns)

    return Prolif21Fingerprint


def test_prolif21_parent_indices_are_local_to_the_protein_selection(monkeypatch, tmp_path):
    fingerprint_cls = _prolif21_fingerprint(
        protein_key="ALA10.A",
        columns=[("LIG1", "ALA10.A", "HBDonor")],
        entries={"HBDonor": ({"distance": 3.0,
                              "parent_indices": {"ligand": [0], "protein": [1]}},)})
    _install_prolif(monkeypatch)
    monkeypatch.setitem(sys.modules, "prolif", SimpleNamespace(Fingerprint=fingerprint_cls))

    class LocalIndexUniverse(FakeUniverse):
        ligand_global = (0,)
        protein_residues = ((10, (1,)), (20, (2,)))

    monkeypatch.setitem(sys.modules, "MDAnalysis", SimpleNamespace(Universe=LocalIndexUniverse))
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.xtc"
    # 体系全局顺序：0=配体，1=ALA10（蛋白 selection 的局部下标 0），2=GLY20（局部下标 1）
    topology.write_text("\n".join([_pdb_line(1, "C1", "LIG", "A", 901),
                                   _pdb_line(2, "CA", "ALA", "A", 10),
                                   _pdb_line(3, "CA", "GLY", "A", 20)]) + "\n", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    contacts, _times, warnings = interactions._extract_with_prolif(
        topology, trajectory, interactions.InteractionConfig())
    # parent_indices["protein"] = [1] 是 protein AtomGroup 的局部下标，必须映射成全局下标 2 → GLY20
    assert [(contact.residue_seq, contact.residue_name) for contact in contacts] == [(20, "GLY")]
    assert warnings == []


def test_prolif21_renumbers_protein_residues_before_the_fingerprint_runs(monkeypatch, tmp_path):
    fingerprint_cls = _prolif21_fingerprint(
        protein_key="ALA1.A",
        columns=[("LIG1", "ALA1.A", "HBDonor"), ("LIG1", "ALA1.A", "Hydrophobic")],
        entries={"HBDonor": ({"distance": 3.0, "parent_indices": {"protein": [0]}},),
                 "Hydrophobic": ({"distance": 3.6, "parent_indices": {"protein": [1]}},)})
    _install_prolif(monkeypatch)
    monkeypatch.setitem(sys.modules, "prolif", SimpleNamespace(Fingerprint=fingerprint_cls))

    class SameChainInsertionUniverse(FakeUniverse):
        # 同链同号、不同插入码：ProLIF 的 ResidueId 不含 icode，必须靠唯一临时 resid 拆开
        ligand_global = (0,)
        protein_residues = ((42, (1,)), (42, (2,)))

        def __init__(self, *args):
            super().__init__(*args)
            # 重编前两条残基的 resid 确实相同，证明碰撞风险真实存在
            assert [residue.resid for residue in self.residues] == [42, 42]

    monkeypatch.setitem(sys.modules, "MDAnalysis", SimpleNamespace(Universe=SameChainInsertionUniverse))
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.xtc"
    topology.write_text("\n".join([_pdb_line(1, "C1", "LIG", "A", 901),
                                   _pdb_line(2, "CA", "ALA", "A", 42),
                                   _pdb_line(3, "CA", "ALA", "A", 42, "A")]) + "\n", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    contacts, _times, warnings = interactions._extract_with_prolif(
        topology, trajectory, interactions.InteractionConfig())

    fingerprint = FakeFingerprint.instances[-1]
    assert fingerprint.protein_resids == [1, 2]  # 进入 ProLIF 前已唯一化
    assert warnings == []
    assert sorted((contact.residue_seq, contact.residue_icode) for contact in contacts) == [(42, ""), (42, "A")]


def test_prolif21_parent_indices_separate_empty_chain_from_named_chain(monkeypatch, tmp_path):
    fingerprint_cls = _prolif21_fingerprint(
        protein_key="ALA1",
        columns=[("LIG1", "ALA1", "HBDonor"), ("LIG1", "ALA2.A", "Hydrophobic")],
        entries={"HBDonor": ({"distance": 3.0, "parent_indices": {"protein": [0]}},),
                 "Hydrophobic": ({"distance": 3.6, "parent_indices": {"protein": [1]}},)})
    _install_prolif(monkeypatch)
    monkeypatch.setitem(sys.modules, "prolif", SimpleNamespace(Fingerprint=fingerprint_cls))

    class EmptyAndNamedChainUniverse(FakeUniverse):
        ligand_global = (0,)
        protein_residues = ((42, (1,)), (42, (2,)))

    monkeypatch.setitem(sys.modules, "MDAnalysis", SimpleNamespace(Universe=EmptyAndNamedChainUniverse))
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.xtc"
    topology.write_text("\n".join([_pdb_line(1, "C1", "LIG", "A", 901),
                                   _pdb_line(2, "CA", "ALA", " ", 42),
                                   _pdb_line(3, "CA", "ALA", "A", 42)]) + "\n", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    contacts, _times, _warnings = interactions._extract_with_prolif(
        topology, trajectory, interactions.InteractionConfig())
    assert sorted(contact.residue_chain for contact in contacts) == ["", "A"]
    assert {contact.residue_seq for contact in contacts} == {42}


def test_prolif_accepts_a_numpy_indices_array(monkeypatch, tmp_path):
    import numpy as np

    class NumpyIndicesAtomGroup(FakeAtomGroup):
        @property
        def indices(self):
            # 真实 MDAnalysis 2.10 的 prot_ag.indices 就是 ndarray：多原子时 `array or ()` 直接 ValueError
            return np.asarray([atom.index for atom in self._atoms], dtype=int)

    class NumpyIndicesUniverse(FakeUniverse):
        def __init__(self, *args):
            super().__init__(*args)
            self.selections["protein"] = NumpyIndicesAtomGroup(list(self.selections["protein"]))

    _install_prolif(monkeypatch)
    monkeypatch.setitem(sys.modules, "MDAnalysis", SimpleNamespace(Universe=NumpyIndicesUniverse))
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.xtc"
    topology.write_text("", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    contacts, _times, warnings = interactions._extract_with_prolif(
        topology, trajectory, interactions.InteractionConfig())
    assert sorted({contact.residue_name for contact in contacts}) == ["ALA", "GLY"]
    assert warnings == []


def test_prolif_frame_times_follow_frame_dt_for_dcd(monkeypatch, tmp_path):
    _install_prolif(monkeypatch)
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.dcd"
    topology.write_text("", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    _c, times, warnings = interactions._extract_with_prolif(
        topology, trajectory, interactions.InteractionConfig(frame_dt_ps=5.0))
    assert times == {0: 0.0, 1: 5.0, 2: 10.0} and warnings == []
    _c, times, warnings = interactions._extract_with_prolif(topology, trajectory, interactions.InteractionConfig())
    assert times == {0: 0.0, 1: 1.0, 2: 2.0}
    assert any("DCD" in item and "frame_dt_ps" in item for item in warnings)


def test_prolif_skips_columns_that_are_not_three_tuples(monkeypatch, tmp_path):
    class LegacyFingerprint(FakeFingerprint):
        def to_dataframe(self):
            return _FakeDataFrame([[True]], index=[0], columns=["LIG1.ALA10.A.HBDonor"])

    FakeFingerprint.instances.clear()
    monkeypatch.setitem(sys.modules, "MDAnalysis", SimpleNamespace(Universe=FakeUniverse))
    monkeypatch.setitem(sys.modules, "prolif", SimpleNamespace(Fingerprint=LegacyFingerprint))
    topology, trajectory = tmp_path / "t.pdb", tmp_path / "t.xtc"
    topology.write_text("", encoding="utf-8")
    trajectory.write_text("", encoding="utf-8")
    contacts, _times, _warnings = interactions._extract_with_prolif(
        topology, trajectory, interactions.InteractionConfig())
    assert contacts == []


def test_analyze_default_prolif_splits_ter_reused_residue_before_universe(monkeypatch, tmp_path):
    # 默认入口（不注入 frame_extractor）走 ProLIF+MDAnalysis：TER 前后各一个 A:ALA10，若原样交给
    # MDAnalysis 2.10 会在建 Universe 时合并成一个 Residue，ProLIF 最终漏掉第二个 TER 段的接触。
    captured = {}

    class TerFingerprint(FakeFingerprint):
        def to_dataframe(self):
            columns = [("LIG1", "ALA1.A", "HBDonor"), ("LIG1", "ALA2.A", "HBDonor")]
            return _FakeDataFrame([[True, True]], index=[0], columns=columns)

    class TerUniverse(FakeUniverse):
        ligand_global = (0,)
        protein_residues = ((10, (1, 2)), (10, (3, 4)))  # 两个 ALA10 残基，分属 TER 前后两段

        def __init__(self, topology=None, trajectory=None):
            captured["topology"] = Path(topology).read_text(encoding="utf-8")
            super().__init__(topology, trajectory)

    _install_prolif(monkeypatch)
    monkeypatch.setitem(sys.modules, "MDAnalysis", SimpleNamespace(Universe=TerUniverse))
    monkeypatch.setitem(sys.modules, "prolif", SimpleNamespace(Fingerprint=TerFingerprint))

    topology = tmp_path / "topology.pdb"
    topology.write_text("\n".join([_pdb_line(1, "C1", "LIG", "A", 901),
                                   _pdb_line(2, "CA", "ALA", "A", 10), _pdb_line(3, "CB", "ALA", "A", 10),
                                   "TER",
                                   _pdb_line(4, "CA", "ALA", "A", 10), _pdb_line(5, "CB", "ALA", "A", 10)])
                        + "\n", encoding="utf-8")
    trajectory = tmp_path / "traj.xtc"
    trajectory.write_bytes(b"")

    payload = interactions.analyze_trajectory(topology, trajectory, output_contacts_csv=tmp_path / "c.csv",
                                              output_summary_json=tmp_path / "i.json")
    # 传给 mda.Universe 的拓扑已把两个 A:ALA10 重编成不同 resSeq/segid，MDAnalysis 不会再合并
    ala = [line for line in captured["topology"].splitlines() if line[17:20].strip() == "ALA"]
    assert len({(line[22:26].strip(), line[72:76].strip()) for line in ala}) == 2
    assert payload["engine"] == "prolif"
    assert payload["summary"]["total_interactions"] == 2
    residue_nodes = [node["id"] for node in payload["network"]["nodes"] if node["kind"] == "residue"]
    assert residue_nodes == ["A#0:ALA10", "A#1:ALA10"]
    assert payload["timeline"][0]["total_contacts"] == 2


class FakeLigandAtoms:
    def __init__(self, elements, bonds=None, indices=None, universe=None):
        indices = list(range(len(elements))) if indices is None else list(indices)
        self._atoms = [SimpleNamespace(element=element, name=f"{element}1", index=index)
                       for element, index in zip(elements, indices)]
        self.n_atoms, self.bonds, self.universe = len(self._atoms), bonds, universe

    def __iter__(self):
        return iter(self._atoms)


class FakeBond:
    def __init__(self, indices, order=None):
        self.indices, self.order = indices, order


class FakeBondUniverse:
    """MDAnalysis 2.10-like: add_TopologyAttr has no `orders=` keyword; orders are the separate attribute."""

    def __init__(self, *, accept_orders: bool = False):
        self.accept_orders, self.topology_attrs = accept_orders, {}

    def add_TopologyAttr(self, name, values=None, orders=None):
        if orders is not None and not self.accept_orders:
            raise TypeError("add_TopologyAttr() got an unexpected keyword argument 'orders'")
        if name != "bonds":
            self.topology_attrs[name] = values
            return
        pairs = list(values or ())
        order_values = list(orders) if orders is not None else [None] * len(pairs)
        self.topology_attrs["bonds"] = [FakeBond(tuple(pair), order) for pair, order in zip(pairs, order_values)]

    @property
    def bonds(self):
        # Real MDAnalysis exposes bond.order from the "bondorders" topology attribute.
        bonds = self.topology_attrs.get("bonds")
        if bonds is None:
            return None
        orders = self.topology_attrs.get("bondorders")
        order_values = list(orders) if orders is not None else []
        views = []
        for position, bond in enumerate(bonds):
            order = bond.order
            if order is None and position < len(order_values):
                order = order_values[position]
            views.append(FakeBond(tuple(bond.indices), order))
        return views


class FakeMdaBonds:
    """`MDAnalysis.core.topologyattrs.Bonds` stand-in: graph and orders travel as one attribute."""

    def __init__(self, values, order=None, types=None, guessed=False):
        self.values = [tuple(pair) for pair in values]
        self.order = [None if value is None else float(value) for value in (order or [None] * len(self.values))]
        self.types, self.guessed = types, guessed


class StrictBondsUniverse:
    """MDAnalysis 2.10.0 surface: no "bondorders" attribute, no `orders=` keyword, only a Bonds object."""

    def __init__(self, bonds=None):
        self._bonds = list(bonds or [])

    def add_TopologyAttr(self, *args, **kwargs):
        # 真实 2.10.0 拒绝 add_TopologyAttr("bondorders", ...) 与 orders= 关键字；替身必须同样拒绝
        if len(args) != 1 or kwargs or not isinstance(args[0], FakeMdaBonds):
            raise TypeError("add_TopologyAttr() only accepts a Bonds topology attribute here")
        self._bonds = [FakeBond(pair, order) for pair, order in zip(args[0].values, args[0].order)]

    @property
    def bonds(self):
        return self._bonds


def _install_topologyattrs(monkeypatch):
    # `from MDAnalysis.core.topologyattrs import Bonds` needs every package level in sys.modules.
    attrs = types.ModuleType("MDAnalysis.core.topologyattrs")
    attrs.Bonds = FakeMdaBonds
    core, package = types.ModuleType("MDAnalysis.core"), types.ModuleType("MDAnalysis")
    package.core, package.__path__ = core, []
    core.topologyattrs = attrs
    for name, module in (("MDAnalysis", package), ("MDAnalysis.core", core),
                         ("MDAnalysis.core.topologyattrs", attrs)):
        monkeypatch.setitem(sys.modules, name, module)


def _template_mol(tmp_path: Path, smiles: str = "CCC") -> Path:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    molecule = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(molecule)
    template = tmp_path / f"ligand-{smiles}.mol"
    Chem.MolToMolFile(molecule, str(template))
    return template


def test_template_bond_orders_are_persisted_in_the_topology(tmp_path):
    bonds = [FakeBond((10, 11)), FakeBond((11, 12))]
    universe = FakeBondUniverse()
    ligand_atoms = FakeLigandAtoms(["C", "C", "C"], bonds, indices=[10, 11, 12], universe=universe)
    assert interactions._apply_template_bond_orders(ligand_atoms, _template_mol(tmp_path)) is True
    # Bond 包装对象只是临时视图；键级必须落到拓扑属性里，读 universe.bonds 能拿回来
    assert [bond.order for bond in bonds] == [None, None]
    assert [(tuple(bond.indices), bond.order) for bond in universe.bonds] == \
        [((10, 11), 1.0), ((11, 12), 1.0)]


def test_template_bond_orders_require_system_wide_indices(tmp_path):
    # 模板是配体局部 0..N-1；拓扑里的键必须用全体系下标写入，局部下标不能误命中
    universe = FakeBondUniverse()
    ligand_atoms = FakeLigandAtoms(["C", "C", "C"], [FakeBond((0, 1))], indices=[10, 11, 12], universe=universe)
    assert interactions._apply_template_bond_orders(ligand_atoms, _template_mol(tmp_path)) is True
    assert [tuple(bond.indices) for bond in universe.bonds] == [(10, 11), (11, 12)]
    assert all(bond.order == 1.0 for bond in universe.bonds)


def test_template_bond_orders_reject_a_topology_that_drops_them(tmp_path):
    class SilentDropUniverse(FakeBondUniverse):
        def add_TopologyAttr(self, name, values=None, orders=None):
            super().add_TopologyAttr(name, values, None)
            if name == "bondorders":
                del self.topology_attrs["bondorders"]  # 静默丢掉键级，不能被当成成功

    universe = SilentDropUniverse()
    ligand_atoms = FakeLigandAtoms(["C", "C", "C"], [FakeBond((0, 1))], universe=universe)
    assert interactions._apply_template_bond_orders(ligand_atoms, _template_mol(tmp_path)) is False
    assert all(bond.order is None for bond in universe.bonds)


def test_template_bond_orders_use_the_legacy_bondorders_attribute(tmp_path):
    universe = FakeBondUniverse()  # 真实 2.10 的 add_TopologyAttr 不接受 orders= 关键字
    ligand_atoms = FakeLigandAtoms(["C", "C", "C"], [FakeBond((0, 1))], indices=[4, 5, 6], universe=universe)
    assert interactions._apply_template_bond_orders(ligand_atoms, _template_mol(tmp_path)) is True
    assert [(tuple(bond.indices)) for bond in universe.bonds] == [(4, 5), (5, 6)]
    assert universe.topology_attrs["bondorders"] == [1.0, 1.0]  # 键级写进了独立属性


def test_template_bond_orders_preserve_existing_protein_bonds(tmp_path):
    class StrictBondUniverse(FakeBondUniverse):
        def add_TopologyAttr(self, name, values=None, orders=None):
            if orders is not None:
                raise TypeError("add_TopologyAttr() got an unexpected keyword argument 'orders'")
            super().add_TopologyAttr(name, values, None)

    universe = StrictBondUniverse()
    # 蛋白侧已经连好的键（PDB CONECT / 力场）：写 "bonds" 是整体替换，不能把它们写丢
    universe.topology_attrs["bonds"] = [FakeBond((0, 1), 1.0), FakeBond((1, 2), 1.0)]
    ligand_atoms = FakeLigandAtoms(["C", "C", "C"], [FakeBond((10, 11))], indices=[10, 11, 12], universe=universe)

    assert interactions._apply_template_bond_orders(ligand_atoms, _template_mol(tmp_path)) is True
    orders = {tuple(bond.indices): bond.order for bond in universe.bonds}
    assert orders[(0, 1)] == 1.0 and orders[(1, 2)] == 1.0  # 原有蛋白键保留
    assert orders[(10, 11)] == 1.0 and orders[(11, 12)] == 1.0  # 新配体键级持久化


def test_template_bond_orders_use_a_bonds_attribute_on_mdanalysis_2_10(tmp_path, monkeypatch):
    # 2.10.0 的 add_TopologyAttr 只接受一个 Bonds 拓扑属性：蛋白原有的 1.5 键与新配体的 2.0 双键
    # 都要随 Bonds(order=...) 一次写入，并从 universe.bonds 精确读回（旧实现把键级丢成 None）。
    _install_topologyattrs(monkeypatch)
    universe = StrictBondsUniverse([FakeBond((0, 1), 1.5)])
    ligand_atoms = FakeLigandAtoms(["C", "C"], [FakeBond((0, 1))], indices=[10, 11], universe=universe)
    assert interactions._apply_template_bond_orders(ligand_atoms, _template_mol(tmp_path, "C=C")) is True
    assert {tuple(bond.indices): bond.order for bond in universe.bonds} == {(0, 1): 1.5, (10, 11): 2.0}


def test_template_bond_orders_guess_bonds_when_the_topology_has_none(tmp_path):
    # 无 CONECT 的 PDB 初始 bonds 为空：写模板键前必须先 guess_bonds()。否则只写入配体键会让 ProLIF 认为
    # 拓扑已带键而跳过自动推断，蛋白键数变成 0。替身记录调用次数，并验证猜出的蛋白键与模板键都被保留。
    class GuessingUniverse(FakeBondUniverse):
        def __init__(self):
            super().__init__()
            self.topology_attrs["bonds"] = []
            self.guessed = 0
            self.atoms = types.SimpleNamespace(guess_bonds=self._guess)

        def _guess(self):
            self.guessed += 1
            self.topology_attrs["bonds"] = [FakeBond((0, 1), 1.0), FakeBond((1, 2), 1.0)]

    universe = GuessingUniverse()
    ligand_atoms = FakeLigandAtoms(["C", "C", "C"], [FakeBond((0, 1))], indices=[10, 11, 12], universe=universe)
    assert interactions._apply_template_bond_orders(ligand_atoms, _template_mol(tmp_path)) is True
    assert universe.guessed == 1  # 空图时补猜一次
    assert {tuple(bond.indices): bond.order for bond in universe.bonds} == \
        {(0, 1): 1.0, (1, 2): 1.0, (10, 11): 1.0, (11, 12): 1.0}


def test_template_bond_orders_guess_protein_bonds_when_only_ligand_conect_exists(tmp_path):
    # PDB 只给配体写了 CONECT：全宇宙已有 1 条配体键 (3, 4)，但蛋白原子 (0, 1, 2) 一个键都没有。
    # 只看「全宇宙是否为空」会跳过 guess_bonds()，ProLIF 收到的蛋白键数为 0；必须按「是否存在非配体键」判定。
    class LigandOnlyUniverse(FakeBondUniverse):
        def __init__(self):
            super().__init__()
            self.topology_attrs["bonds"] = [FakeBond((3, 4), 1.0)]  # 只来自配体 CONECT
            self.guessed = 0
            self.atoms = types.SimpleNamespace(guess_bonds=self._guess)

        def _guess(self):
            self.guessed += 1
            self.topology_attrs["bonds"] = [*self.topology_attrs["bonds"],
                                            FakeBond((0, 1), 1.0), FakeBond((1, 2), 1.0)]

    universe = LigandOnlyUniverse()
    ligand_atoms = FakeLigandAtoms(["C", "C", "C"], [FakeBond((3, 4))], indices=[3, 4, 5], universe=universe)
    assert interactions._apply_template_bond_orders(ligand_atoms, _template_mol(tmp_path)) is True
    assert universe.guessed == 1  # 蛋白原子无键时补猜一次
    assert {tuple(bond.indices): bond.order for bond in universe.bonds} == \
        {(0, 1): 1.0, (1, 2): 1.0, (3, 4): 1.0, (4, 5): 1.0}  # 猜出的蛋白键与配体模板键一并保留


def test_template_bond_orders_guess_protein_bonds_when_only_water_conect_exists(tmp_path):
    # PDB 只给水分子写了 CONECT：已有键 (6, 7) 既不在配体也不在蛋白选择里。若按「是否有非配体键」判定就要跳过
    # guess_bonds()，蛋白键数仍是 0；必须只认蛋白选择内部的键，并在蛋白 AtomGroup 上补猜。
    class WaterOnlyUniverse(FakeBondUniverse):
        def __init__(self):
            super().__init__()
            self.topology_attrs["bonds"] = [FakeBond((6, 7), 1.0)]  # 只来自水分子 CONECT
            self.guessed = 0

        def guess(self):
            self.guessed += 1
            self.topology_attrs["bonds"] = [*self.topology_attrs["bonds"],
                                            FakeBond((0, 1), 1.0), FakeBond((1, 2), 1.0)]

    universe = WaterOnlyUniverse()
    protein_atoms = types.SimpleNamespace(guess_bonds=universe.guess)
    ligand_atoms = FakeLigandAtoms(["C", "C", "C"], [FakeBond((3, 4))], indices=[3, 4, 5], universe=universe)
    assert interactions._apply_template_bond_orders(ligand_atoms, _template_mol(tmp_path), universe, protein_atoms,
                                                    (0, 1, 2)) is True
    assert universe.guessed == 1  # 水分子键不算蛋白键：仍要补猜一次
    assert {tuple(bond.indices): bond.order for bond in universe.bonds} == \
        {(0, 1): 1.0, (1, 2): 1.0, (3, 4): 1.0, (4, 5): 1.0, (6, 7): 1.0}  # 水键也不丢


def test_template_bond_orders_compare_full_element_symbols(tmp_path):
    template = _template_mol(tmp_path, "ClC")
    with pytest.raises(ValueError, match="atom order"):
        interactions._apply_template_bond_orders(FakeLigandAtoms(["C", "C"]), template)  # 不能把 Cl 截成 C
    assert interactions._apply_template_bond_orders(FakeLigandAtoms(["CL", "C"]), template) is False


def test_template_bond_orders_reject_mismatched_template(tmp_path):
    template = _template_mol(tmp_path)
    with pytest.raises(ValueError, match="atoms"):
        interactions._apply_template_bond_orders(FakeLigandAtoms(["C", "C"]), template)
    with pytest.raises(ValueError, match="atom order"):
        interactions._apply_template_bond_orders(FakeLigandAtoms(["O", "C", "C"]), template)


# ---------------------------------------------------------------------------
# 假 mdtraj
# ---------------------------------------------------------------------------


class FakeElement:
    def __init__(self, symbol):
        self.symbol = symbol


class FakeChain:
    def __init__(self, chain_id):
        self.chain_id = chain_id


class FakeResidue:
    def __init__(self, name, *, is_protein, resseq, chain):
        # mdtraj 1.10.3 has no insertionCode attribute at all; residue identity must come from the PDB.
        self.name, self.is_protein, self.resSeq = name, is_protein, resseq
        self.chain, self.atoms = chain, []


class FakeAtom:
    def __init__(self, index, symbol, name, residue):
        self.index, self.element, self.name, self.residue = index, FakeElement(symbol), name, residue
        residue.atoms.append(self)


class FakeTopology:
    def __init__(self, atoms):
        self.atoms = atoms
        self.residues = []
        for atom in atoms:
            if atom.residue not in self.residues:
                self.residues.append(atom.residue)

    def atom(self, index):
        return self.atoms[index]

    def select_pairs(self, selection1, selection2):
        return [[left, right] for left in selection1 for right in selection2]


class FakeFrame:
    def __init__(self, distances, unitcell=True):
        import numpy as np

        self._distances, self.unitcell_vectors = np.asarray([distances], dtype=float), (object() if unitcell else None)

    def __getitem__(self, index):
        return SimpleNamespace(time=float(index) * 10.0)


class FakeMdtrajTrajectory:
    def __init__(self, topology, n_frames, distances, unitcell=True):
        self.topology, self.n_frames = topology, n_frames
        self._distances, self._unitcell = distances, unitcell

    def __getitem__(self, index):
        frame = FakeFrame(self._distances, self._unitcell)
        frame.time = float(index) * 10.0
        return frame


def _four_atom_topology():
    chain_a = FakeChain("A")
    ligand_res = FakeResidue("LIG", is_protein=False, resseq=901, chain=chain_a)
    ala42a = FakeResidue("ALA", is_protein=True, resseq=42, chain=chain_a)
    atoms = [FakeAtom(0, "C", "C1", ligand_res), FakeAtom(1, "H", "H1", ligand_res),
             FakeAtom(2, "C", "CA", ala42a), FakeAtom(3, "H", "HA", ala42a)]
    return FakeTopology(atoms)


def _mdtraj_pdb(tmp_path: Path) -> Path:
    # 原子顺序与假 mdtraj 拓扑一一对应；第 3 个原子属于 42A，且 42A 没有对应的 FakeResidue 属性
    path = tmp_path / "t.pdb"
    path.write_text("\n".join([_pdb_line(1, "C1", "LIG", "A", 901), _pdb_line(2, "H1", "LIG", "A", 901),
                               _pdb_line(3, "CA", "ALA", "A", 42, "A"), _pdb_line(4, "HA", "ALA", "A", 42)]) + "\n",
                    encoding="utf-8")
    return path


def test_mdtraj_uses_heavy_atoms_periodic_and_real_frame_numbers(monkeypatch, tmp_path):
    calls = {}

    def fake_load(path, top=None, stride=1):
        calls["load"] = (path, top, stride)
        return FakeMdtrajTrajectory(_four_atom_topology(), 3, [0.40])

    def fake_distances(frame, pairs, periodic=False):
        import numpy as np

        calls.setdefault("pairs", []).append([tuple(pair) for pair in pairs])
        calls.setdefault("periodic", []).append(periodic)
        return np.asarray([[0.40]])

    monkeypatch.setitem(sys.modules, "mdtraj", SimpleNamespace(load=fake_load, compute_distances=fake_distances))
    topology, trajectory = _mdtraj_pdb(tmp_path), tmp_path / "t.xtc"
    trajectory.write_text("", encoding="utf-8")
    config = interactions.InteractionConfig(stride=2, contact_cutoff_nm=0.45)
    contacts, times, warnings = interactions._extract_with_mdtraj_fallback(topology, trajectory, config)

    # 重原子过滤：H 不进入 selection；配置步长传给 md.load；原始帧号 = sample * stride
    assert calls["pairs"][0] == [(0, 2)]
    assert calls["load"][2] == 2
    assert calls["periodic"] == [True] * 3
    assert [contact.frame for contact in contacts] == [0, 2, 4]
    assert times == {0: 0.0, 2: 10.0, 4: 20.0}
    assert contacts[0].residue_icode == "A" and contacts[0].residue_seq == 42
    assert contacts[0].interaction_type == "vdw_contact" and contacts[0].distance_nm == 0.4
    assert warnings == []


def test_mdtraj_distinguishes_insertion_codes_from_real_pdb(monkeypatch, tmp_path):
    chain_a = FakeChain("A")
    ligand_res = FakeResidue("LIG", is_protein=False, resseq=901, chain=chain_a)
    residue_42, residue_42a = (FakeResidue("ALA", is_protein=True, resseq=42, chain=chain_a) for _ in range(2))
    atoms = [FakeAtom(0, "C", "C1", ligand_res), FakeAtom(1, "C", "CA", residue_42),
             FakeAtom(2, "C", "CA", residue_42a)]
    topology_file = tmp_path / "t.pdb"
    topology_file.write_text("\n".join([_pdb_line(1, "C1", "LIG", "A", 901), _pdb_line(2, "CA", "ALA", "A", 42),
                                        _pdb_line(3, "CA", "ALA", "A", 42, "A")]) + "\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "mdtraj", SimpleNamespace(
        load=lambda *a, **k: FakeMdtrajTrajectory(FakeTopology(atoms), 1, [0.40, 0.44]),
        compute_distances=lambda *a, **k: __import__("numpy").asarray([[0.40, 0.44]])))
    contacts, _times, _warnings = interactions._extract_with_mdtraj_fallback(
        topology_file, tmp_path / "t.xtc", interactions.InteractionConfig())
    assert sorted((contact.residue_seq, contact.residue_icode) for contact in contacts) == [(42, ""), (42, "A")]


def test_mdtraj_non_periodic_when_box_absent(monkeypatch, tmp_path):
    seen = []

    def fake_load(path, top=None, stride=1):
        return FakeMdtrajTrajectory(_four_atom_topology(), 1, [0.50], unitcell=False)

    def fake_distances(frame, pairs, periodic=False):
        import numpy as np

        seen.append(periodic)
        return np.asarray([[0.50]])

    monkeypatch.setitem(sys.modules, "mdtraj", SimpleNamespace(load=fake_load, compute_distances=fake_distances))
    topology, trajectory = _mdtraj_pdb(tmp_path), tmp_path / "t.xtc"
    trajectory.write_text("", encoding="utf-8")
    contacts, _times, _warnings = interactions._extract_with_mdtraj_fallback(
        topology, trajectory, interactions.InteractionConfig())
    assert seen == [False]
    assert contacts == []  # 0.50 nm 超过默认 0.45 nm 截断


def test_mdtraj_dcd_times_are_explicitly_approximate(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "mdtraj", SimpleNamespace(
        load=lambda *a, **k: FakeMdtrajTrajectory(_four_atom_topology(), 2, [0.40]),
        compute_distances=lambda *a, **k: __import__("numpy").asarray([[0.40]])))
    topology, trajectory = _mdtraj_pdb(tmp_path), tmp_path / "t.dcd"
    trajectory.write_text("", encoding="utf-8")
    contacts, times, warnings = interactions._extract_with_mdtraj_fallback(
        topology, trajectory, interactions.InteractionConfig())
    assert times == {0: 0.0, 1: 1.0} and contacts[1].time_ps == 1.0
    assert any("DCD" in item and "frame_dt_ps" in item for item in warnings)

    configured = interactions.InteractionConfig(frame_dt_ps=5.0)
    _c, times, warnings = interactions._extract_with_mdtraj_fallback(topology, trajectory, configured)
    assert times == {0: 0.0, 1: 5.0} and warnings == []


def test_mdtraj_unwraps_a_one_element_time_array(monkeypatch, tmp_path):
    import numpy as np

    class ArrayTimeFrame(FakeFrame):
        def __init__(self, distances, unitcell=True):
            super().__init__(distances, unitcell)
            self.time = np.asarray([2.5])  # NumPy 2.x 上 float(1 元素数组) 会直接 TypeError

    class ArrayTimeTrajectory(FakeMdtrajTrajectory):
        def __getitem__(self, index):
            return ArrayTimeFrame(self._distances, self._unitcell)

    monkeypatch.setitem(sys.modules, "mdtraj", SimpleNamespace(
        load=lambda *a, **k: ArrayTimeTrajectory(_four_atom_topology(), 1, [0.40]),
        compute_distances=lambda *a, **k: np.asarray([[0.40]])))
    topology, trajectory = _mdtraj_pdb(tmp_path), tmp_path / "t.xtc"
    trajectory.write_text("", encoding="utf-8")
    contacts, times, warnings = interactions._extract_with_mdtraj_fallback(
        topology, trajectory, interactions.InteractionConfig())
    assert times == {0: 2.5} and contacts[0].time_ps == 2.5
    assert warnings == []
    assert interactions._scalar_time(np.asarray([2.5])) == 2.5
    assert interactions._scalar_time(np.asarray(3.5)) == 3.5
    assert interactions._scalar_time([4.5]) == 4.5


def test_mdtraj_interface_requires_two_protein_chains(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "mdtraj", SimpleNamespace(
        load=lambda *a, **k: FakeMdtrajTrajectory(_four_atom_topology(), 1, [0.40]),
        compute_distances=lambda *a, **k: __import__("numpy").asarray([[0.40]])))
    topology, trajectory = _mdtraj_pdb(tmp_path), tmp_path / "t.xtc"
    trajectory.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="two protein chains"):
        interactions._extract_with_mdtraj_fallback(
            topology, trajectory, interactions.InteractionConfig(), mode="protein_interface")


# ---------------------------------------------------------------------------
# 模式识别 / 残基身份
# ---------------------------------------------------------------------------


def test_detect_mode_distinguishes_ligand_interface_and_single_chain(tmp_path):
    assert interactions._detect_mode(_write_topology(tmp_path / "l.pdb", with_ligand=True), "LIG") == "protein_ligand"
    assert interactions._detect_mode(
        _write_topology(tmp_path / "i.pdb", with_ligand=False, two_chains=True), "LIG") == "protein_interface"
    assert interactions._detect_mode(
        _write_topology(tmp_path / "s.pdb", with_ligand=False), "LIG") == "single_chain"


def test_detect_mode_keeps_empty_chain_distinct_from_a(tmp_path):
    path = tmp_path / "chains.pdb"
    path.write_text("\n".join([_pdb_line(1, "CA", "ALA", " ", 10), _pdb_line(2, "CA", "GLY", "A", 20)]) + "\n",
                    encoding="utf-8")
    assert interactions._detect_mode(path, "LIG") == "protein_interface"


def test_detect_mode_missing_topology_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        interactions._detect_mode(tmp_path / "missing.pdb", "LIG")


def test_read_pdb_residues_keeps_first_altloc_and_aligns_atom_indices(tmp_path):
    path = tmp_path / "alt.pdb"
    path.write_text("\n".join([
        _pdb_line(1, "CA", "ALA", "A", 10),
        _pdb_line(2, "CB", "ALA", "A", 10, altloc="A"),
        _pdb_line(3, "CB", "ALA", "A", 10, altloc="B"),  # 同一原子的第二构象，不得让后续下标整体偏移
        _pdb_line(4, "CA", "GLY", "A", 20),
    ]) + "\n", encoding="utf-8")
    atoms, residues = interactions._read_pdb_residues(path, dedupe_altloc=True)
    assert [(residue.seq, residue.name) for residue in atoms] == [(10, "ALA"), (10, "ALA"), (20, "GLY")]
    assert [residue.name for residue in residues] == ["ALA", "GLY"]
    # 与 mdtraj 1.10.3 同口径：第 3 个原子（下标 2）仍是 GLY20，插入码/残基回查都不偏移
    assert interactions._residue_from_atom_index(atoms, 2) == interactions.PdbResidue("A", 20, "", "GLY")


def test_read_pdb_residues_dedupes_altloc_atoms_with_different_residue_names(tmp_path):
    # mdtraj 1.10.3 按 (chain, res_seq, icode, atom_name) 合并 altLoc，不含 res_name：同位点的
    # A=ALA / B=GLY 也只留首条，否则这里多留一条会让后续所有原子下标整体偏移。
    path = tmp_path / "alt.pdb"
    path.write_text("\n".join([
        _pdb_line(1, "CA", "ALA", "A", 10),
        _pdb_line(2, "CB", "ALA", "A", 10, altloc="A"),
        _pdb_line(3, "CB", "GLY", "A", 10, altloc="B"),
        _pdb_line(4, "CA", "GLY", "A", 20),
    ]) + "\n", encoding="utf-8")
    atoms, residues = interactions._read_pdb_residues(path, dedupe_altloc=True)
    assert [(residue.seq, residue.name) for residue in atoms] == [(10, "ALA"), (10, "ALA"), (20, "GLY")]
    assert [residue.name for residue in residues] == ["ALA", "GLY"]
    assert interactions._residue_from_atom_index(atoms, 2) == interactions.PdbResidue("A", 20, "", "GLY")


def test_read_pdb_residues_keeps_every_altloc_for_the_mdanalysis_path(tmp_path):
    path = tmp_path / "alt.pdb"
    path.write_text("\n".join([
        _pdb_line(1, "CA", "ALA", "A", 10),
        _pdb_line(2, "CB", "ALA", "A", 10, altloc="A"),
        _pdb_line(3, "CB", "ALA", "A", 10, altloc="B"),
        _pdb_line(4, "CA", "GLY", "A", 20),
    ]) + "\n", encoding="utf-8")
    atoms, residues = interactions._read_pdb_residues(path, dedupe_altloc=False)
    # MDAnalysis/ProLIF 保留 A/B 两条 altLoc 原子记录：原子表必须 1:1 对齐，不能像 mdtraj 那样去重
    assert [(residue.seq, residue.name) for residue in atoms] == [(10, "ALA"), (10, "ALA"), (10, "ALA"), (20, "GLY")]
    assert [residue.name for residue in residues] == ["ALA", "GLY"]
    assert interactions._residue_from_atom_index(atoms, 3) == interactions.PdbResidue("A", 20, "", "GLY")


def test_read_pdb_residues_altloc_locks_first_residue_name_and_keeps_unique_atoms(tmp_path):
    # 真实 mdtraj 1.10.3：同 (TER 段, 链, 残基号, 插入码) 锁定首个 resName（A=ALA10 -> ALA），
    # 原子按名字去重但保留后续构象的独有重原子；B=SER10 的骨架原子被跳过、独有 OG 保留并归入 A:ALA10，
    # 总原子数因此严格等于真实 mdtraj 的 6 个。TER 后复用链号 "A" 必须独立分段。
    path = tmp_path / "alt.pdb"
    path.write_text("\n".join([
        _pdb_line(1, "N", "ALA", "A", 10, altloc="A"),
        _pdb_line(2, "CA", "ALA", "A", 10, altloc="A"),
        _pdb_line(3, "C", "ALA", "A", 10, altloc="A"),
        _pdb_line(4, "O", "ALA", "A", 10, altloc="A"),
        _pdb_line(5, "CB", "ALA", "A", 10, altloc="A"),
        _pdb_line(6, "N", "SER", "A", 10, altloc="B"),   # 同键重复骨架原子：跳过
        _pdb_line(7, "CA", "SER", "A", 10, altloc="B"),
        _pdb_line(8, "C", "SER", "A", 10, altloc="B"),
        _pdb_line(9, "O", "SER", "A", 10, altloc="B"),
        _pdb_line(10, "CB", "SER", "A", 10, altloc="B"),
        _pdb_line(11, "OG", "SER", "A", 10, altloc="B"),  # 唯一重原子：保留，残基名仍为锁定的 ALA
        "TER",
        _pdb_line(12, "CA", "GLY", "A", 10, altloc="A"),  # 复用链号 "A"，但 TER 开了新段
    ]) + "\n", encoding="utf-8")
    atoms, residues = interactions._read_pdb_residues(path, dedupe_altloc=True)
    assert [(residue.seq, residue.name) for residue in atoms] == [(10, "ALA")] * 6 + [(10, "GLY")]
    assert [residue.name for residue in residues] == ["ALA", "GLY"]
    assert interactions._residue_from_atom_index(atoms, 5) == interactions.PdbResidue("A", 10, "", "ALA", 0)
    assert interactions._residue_from_atom_index(atoms, 6) == interactions.PdbResidue("A", 10, "", "GLY", 1)


def test_read_pdb_residues_ter_opens_a_segment_for_a_reused_chain_id(tmp_path):
    # 真实 mdtraj 在 TER 处开新链段：TER 后复用 "A" 的 GLY10 不与前一段同号残基合并，其 altLoc 也单独锁定。
    # 若不按 TER 分段，GLY10 的 "A" 构象会撞上第一段已锁定的 "B" 而被整段丢弃。
    path = tmp_path / "ter.pdb"
    path.write_text("\n".join([
        _pdb_line(1, "CB", "ALA", "A", 10, altloc="B"),
        "TER",
        _pdb_line(2, "CA", "GLY", "A", 10, altloc="A"),
        _pdb_line(3, "CB", "GLY", "A", 10, altloc="A"),
    ]) + "\n", encoding="utf-8")
    atoms, residues = interactions._read_pdb_residues(path, dedupe_altloc=True)
    assert [(residue.seq, residue.name) for residue in atoms] == [(10, "ALA"), (10, "GLY"), (10, "GLY")]
    assert [residue.name for residue in residues] == ["ALA", "GLY"]
    assert interactions._residue_from_atom_index(atoms, 1) == interactions.PdbResidue("A", 10, "", "GLY", 1)


def test_contacts_from_different_ter_segments_stay_independent(tmp_path):
    # TER 后复用 A:ALA10：聚合必须是两条记录，网络两个残基节点，同一帧的时间线算 2 个接触，不能合并成 1。
    path = tmp_path / "segments.pdb"
    path.write_text("\n".join([
        _pdb_line(1, "CA", "ALA", "A", 10),
        _pdb_line(2, "CB", "ALA", "A", 10),
        "TER",
        _pdb_line(3, "CA", "ALA", "A", 10),
        _pdb_line(4, "CB", "ALA", "A", 10),
    ]) + "\n", encoding="utf-8")
    atoms, _residues = interactions._read_pdb_residues(path, dedupe_altloc=False)
    first, second = (interactions._residue_from_atom_index(atoms, index) for index in (0, 2))
    assert (first.segment, second.segment) == (0, 1)
    contacts = [_contact(1, segment=first.segment), _contact(1, distance=0.25, segment=second.segment)]
    rows = interactions.aggregate_contacts(contacts, total_frames=2)
    assert len(rows) == 2 and {row["residue_segment"] for row in rows} == {0, 1}
    timeline = interactions.build_timeline(contacts, frame_times_ps={1: 0.0})
    assert timeline[0]["total_contacts"] == 2
    network = interactions.build_interaction_network(rows)
    assert [node["id"] for node in network["nodes"] if node["kind"] == "residue"] == ["A#0:ALA10", "A#1:ALA10"]
    out = interactions.write_contacts_csv(rows, tmp_path / "contacts.csv")
    assert len(out.read_text(encoding="utf-8").splitlines()) == 3  # 表头 + 两条 TER 段记录


def test_parse_residue_id_preserves_insertion_code_and_chain():
    assert interactions._parse_residue_id("ALA42A.B") == ("B", 42, "ALA", "A")
    assert interactions._parse_residue_id("ALA42.B") == ("B", 42, "ALA", "")
    assert interactions._parse_residue_id("A:10:ALA:X") == ("A", 10, "ALA", "X")
    assert interactions._parse_residue_id(":7") == ("", 7, "", "")
    with pytest.raises(ValueError):
        interactions._parse_residue_id("not-a-residue")


def test_insertion_codes_produce_distinct_aggregate_rows():
    contacts = [_contact(1, seq=42, icode=""), _contact(1, seq=42, icode="A")]
    rows = interactions.aggregate_contacts(contacts, total_frames=1)
    assert sorted(row["residue_icode"] for row in rows) == ["", "A"]


# ---------------------------------------------------------------------------
# 聚合 / 时间线 / 网络 / 产物
# ---------------------------------------------------------------------------


def test_constants_and_mapping():
    assert interactions.CONTACTS_CSV_COLUMNS[:4] == ("residue_chain", "residue_seq", "residue_icode", "residue_name")
    assert "WaterBridge" not in interactions.DEFAULT_PROLIF_INTERACTIONS
    assert set(interactions.PROLIF_TO_CANONICAL_TYPE.values()) <= set(interactions.SUPPORTED_INTERACTION_TYPES)


def test_normalize_interaction_type_accepts_both_vocabularies():
    assert interactions.normalize_interaction_type("HBDonor") == "hbond_donor"
    assert interactions.normalize_interaction_type("CationPi") == "cation_pi"
    assert interactions.normalize_interaction_type("Anionic") == "salt_bridge"
    assert interactions.normalize_interaction_type("MetalCoordination") is None
    assert interactions.normalize_interaction_type(None) is None


def test_aggregate_does_not_let_a_later_none_erase_a_frame_distance():
    # 同一帧里引擎可能先给距离、再从另一列给 None：后到的 None 不得把已记录的有效距离抹掉
    contacts = [_contact(1, distance=0.31), _contact(1, distance=None), _contact(1, distance=0.28)]
    rows = interactions.aggregate_contacts(contacts, total_frames=1)
    assert (rows[0]["min_distance_nm"], rows[0]["mean_distance_nm"]) == (0.28, 0.28)


def test_aggregate_counts_once_per_frame_clamps_and_keeps_min_distance():
    contacts = [_contact(1, distance=0.30), _contact(1, distance=0.20), _contact(2, distance=None)]
    rows = interactions.aggregate_contacts(contacts, total_frames=2)
    assert len(rows) == 1
    assert (rows[0]["contact_frames"], rows[0]["occupancy"], rows[0]["min_distance_nm"]) == (2, 1.0, 0.2)
    assert rows[0]["mean_distance_nm"] == 0.2
    clamped = interactions.aggregate_contacts([_contact(i) for i in range(1, 6)], total_frames=3)
    assert clamped[0]["contact_frames"] == 3 and clamped[0]["occupancy"] == 1.0
    assert interactions.aggregate_contacts([_contact(1)], total_frames=0) == []


def test_aggregate_none_distance_stays_none_and_filters_threshold():
    rows = interactions.aggregate_contacts([_contact(1, distance=None)], total_frames=1)
    assert rows[0]["min_distance_nm"] is None and rows[0]["mean_distance_nm"] is None
    two = [_contact(1, seq=10), _contact(1, seq=20), _contact(2, seq=20)]
    assert [row["residue_seq"] for row in interactions.aggregate_contacts(two, total_frames=4, min_occupancy=0.5)] == [20]


def test_timeline_zero_fills_and_dedupes_pairs():
    contacts = [_contact(1), _contact(1), _contact(1, "hydrophobic"), _contact(3, "vdw_contact")]
    timeline = interactions.build_timeline(contacts, frame_times_ps={1: 0.0, 2: 10.0, 3: 20.0})
    assert [row["frame"] for row in timeline] == [1, 2, 3]
    first, empty, last = timeline
    assert (first["total_contacts"], first["hbond_count"], first["hydrophobic_count"], first["other_count"]) == (2, 1, 1, 0)
    assert empty["total_contacts"] == 0 and empty["time_ps"] == 10.0
    assert last["other_count"] == 1


def test_connected_components_falls_back_without_networkx(monkeypatch):
    monkeypatch.setitem(sys.modules, "networkx", None)  # 令 import networkx 抛 ImportError
    assert interactions._connected_components({"LIG": {"A"}, "A": {"LIG"}, "B": set()}) == 2
    assert interactions._connected_components({}) == 0


def test_network_keeps_one_edge_per_type_with_bounded_occupancy():
    rows = [
        {"residue_chain": "A", "residue_seq": 10, "residue_name": "ALA", "interaction_type": "hbond_donor",
         "occupancy": 0.9, "mean_distance_nm": 0.28},
        {"residue_chain": "A", "residue_seq": 10, "residue_name": "ALA", "interaction_type": "hydrophobic",
         "occupancy": 1.4, "mean_distance_nm": 0.40},
    ]
    network = interactions.build_interaction_network(rows)
    assert len(network["edges"]) == 2
    assert all(0.0 <= edge["occupancy"] <= 1.0 for edge in network["edges"])
    ala = next(node for node in network["nodes"] if node["id"] == "A:10:ALA")
    assert ala["degree"] == 1 and ala["weighted_degree"] == 1.9
    assert network["stats"]["hub_residues"][0]["id"] == "A:10:ALA"
    assert network["stats"]["connected_components"] == 1


def test_network_empty_and_filtered_matches():
    empty = interactions.build_interaction_network([])
    assert empty["nodes"][0]["id"] == "LIG" and empty["edges"] == []
    rows = [{"residue_chain": "A", "residue_seq": 10, "residue_name": "ALA", "interaction_type": "vdw_contact",
             "occupancy": 0.1}]
    filtered = interactions.build_interaction_network(rows, min_edge_occupancy=0.5)
    assert filtered["edges"] == [] and filtered["stats"]["node_count"] == 1


def test_csv_has_icode_column_and_blanks_none(tmp_path):
    rows = [{"residue_chain": "A", "residue_seq": 10, "residue_icode": "B", "residue_name": "ALA",
             "interaction_type": "hbond_donor", "occupancy": 0.5, "contact_frames": 1, "total_frames": 2,
             "min_distance_nm": None, "mean_distance_nm": 0.123456}]
    out = interactions.write_contacts_csv(rows, tmp_path / "contacts.csv")
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(interactions.CONTACTS_CSV_COLUMNS)
    assert lines[1] == "A,10,B,ALA,hbond_donor,0.5000,1,2,,0.1235"


def test_summary_payload_and_json_round_trip(tmp_path):
    rows = [{"residue_chain": "A", "residue_seq": 10, "residue_name": "ALA", "interaction_type": "hbond_donor",
             "occupancy": 0.75}]
    payload = interactions.build_summary_payload(mode="protein_ligand", engine="injected", ligand_resname="LIG",
                                                 stride=1, total_frames=4, cutoffs_nm={"contact": 0.45},
                                                 rows=rows, warnings=["demo"])
    assert payload["schema_version"] == "1.0" and payload["cutoffs_angstrom"] == {"contact": 4.5}
    assert payload["summary"]["by_type"] == {"hbond_donor": 1} and payload["summary"]["max_occupancy"] == 0.75
    out = interactions.write_interactions_summary(payload, tmp_path / "nested" / "interactions.json")
    assert json.loads(out.read_text(encoding="utf-8"))["warnings"] == ["demo"]


# ---------------------------------------------------------------------------
# 编排
# ---------------------------------------------------------------------------


def test_analyze_with_injected_extractor_writes_both_artifacts(tmp_path):
    topology = _write_topology(tmp_path / "topology.pdb", with_ligand=True)
    (tmp_path / "traj.xtc").write_bytes(b"")

    def extractor(_topology, _trajectory, _config, _sdf):
        return [_contact(1, distance=0.28), _contact(2, distance=0.30)], {1: 0.0, 2: 10.0}, ["injected-note"]

    payload = interactions.analyze_trajectory(
        topology, tmp_path / "traj.xtc", output_contacts_csv=tmp_path / "contacts.csv",
        output_summary_json=tmp_path / "interactions.json", frame_extractor=extractor)
    assert payload["mode"] == "protein_ligand" and payload["engine"] == "injected"
    assert payload["total_frames"] == 2 and payload["warnings"] == ["injected-note"]
    assert payload["summary"]["max_occupancy"] == 1.0 and payload["network"]["anchor_id"] == "LIG"
    assert "0.2800" in (tmp_path / "contacts.csv").read_text(encoding="utf-8")
    assert payload["timeline"][0]["time_ps"] == 0.0


def test_analyze_rejects_missing_inputs(tmp_path):
    with pytest.raises(FileNotFoundError, match="topology"):
        interactions.analyze_trajectory(tmp_path / "missing.pdb", tmp_path / "t.xtc",
                                        output_contacts_csv=tmp_path / "c.csv",
                                        output_summary_json=tmp_path / "i.json")
    topology = _write_topology(tmp_path / "topology.pdb", with_ligand=True)
    (tmp_path / "traj.xtc").write_bytes(b"")
    with pytest.raises(FileNotFoundError, match="trajectory"):
        interactions.analyze_trajectory(topology, tmp_path / "missing.xtc", output_contacts_csv=tmp_path / "c.csv",
                                        output_summary_json=tmp_path / "i.json")


def test_explicit_interface_mode_is_not_hijacked_by_ligand(tmp_path):
    topology = _write_topology(tmp_path / "topology.pdb", with_ligand=True)
    (tmp_path / "traj.xtc").write_bytes(b"")

    def extractor(*_args):
        return [], {1: 0.0}

    payload = interactions.analyze_trajectory(
        topology, tmp_path / "traj.xtc", output_contacts_csv=tmp_path / "c.csv",
        output_summary_json=tmp_path / "i.json", config=interactions.InteractionConfig(mode="protein_interface"),
        frame_extractor=extractor)
    assert payload["mode"] == "protein_interface" and payload["network"]["anchor_id"] == "INTERFACE"


def test_prepare_mda_topology_pdb_keeps_fixed_width_past_segment_100(tmp_path):
    # segment >= 100 时 segid（73-76 列）不得溢出挤占元素列（77-78）和电荷列（79-80）
    path = tmp_path / "many_ter.pdb"
    lines = []
    for seg in range(105):
        lines.append(_pdb_line(seg + 1, "CA", "ALA", "A", 10, element="C"))
        lines.append("TER")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    atom_table, _residues = interactions._read_pdb_residues(path, dedupe_altloc=False)
    rewritten = interactions._prepare_mda_topology_pdb(path, atom_table, tmp_path)
    last_atom = [line for line in rewritten.read_text(encoding="utf-8").splitlines() if line.startswith("ATOM")][-1]
    assert len(last_atom[72:76]) == 4 and last_atom[76:78].strip() == "C"


def test_prolif_without_template_or_conect_guesses_bonds_for_both_selections(tmp_path, monkeypatch):
    # 无 SDF 模板且无 CONECT 时，默认 ProLIF 入口必须对蛋白和配体选区都触发 guess_bonds()
    import numpy as np

    path = tmp_path / "no_conect.pdb"
    path.write_text("\n".join([
        _pdb_line(1, "N", "ALA", "A", 10, element="N"),
        _pdb_line(2, "CA", "ALA", "A", 10, element="C"),
        _pdb_line(3, "C1", "LIG", "B", 1, record="HETATM", element="C"),
        _pdb_line(4, "O1", "LIG", "B", 1, record="HETATM", element="O"),
    ]) + "\n", encoding="utf-8")
    (tmp_path / "traj.xtc").write_bytes(b"")
    guessed = []

    class FakeSelection(FakeAtomGroup):
        def __init__(self, name, indices, atoms, bonds):
            super().__init__(atoms)
            self._name, self._indices, self._bonds = name, indices, bonds

        @property
        def indices(self):
            return self._indices

        def guess_bonds(self):
            guessed.append(self._name)
            pair = (0, 1) if self._name == "protein" else (2, 3)
            self._bonds.append(FakeBond(pair, 1.0))

    class LocalUniverse:
        def __init__(self, *_args):
            self.trajectory = FakeTrajectory([0.0])
            self.bonds = []
            p_atoms = [FakeMdaAtom(0, "N"), FakeMdaAtom(1, "CA")]
            FakeMdaResidue(10, p_atoms)
            l_atoms = [FakeMdaAtom(2, "C1"), FakeMdaAtom(3, "O1")]
            self._p, self._l = p_atoms, l_atoms
            self.atoms = types.SimpleNamespace(guess_bonds=lambda: guessed.append("all"))

        def select_atoms(self, query):
            if query == "protein":
                return FakeSelection("protein", np.array([0, 1]), self._p, self.bonds)
            return FakeSelection("ligand", np.array([2, 3]), self._l, self.bonds)

    class LocalFp:
        def __init__(self, *_args, **_kwargs):
            self.ifp = {0: {("LIG1.B", "ALA10.A"): {"HBDonor": ({"parent_indices": {"protein": [0]},
                                                                   "distance": 2.9},)}}}

        def run(self, *_args, **_kwargs):
            assert sorted(guessed) == ["ligand", "protein"]

        def to_dataframe(self):
            cols = [("LIG1.B", "ALA10.A", "HBDonor")]
            return _FakeDataFrame([[True]], index=[0], columns=cols)

    monkeypatch.setitem(sys.modules, "MDAnalysis", types.SimpleNamespace(Universe=LocalUniverse))
    monkeypatch.setitem(sys.modules, "prolif", types.SimpleNamespace(Fingerprint=LocalFp))
    payload = interactions.analyze_trajectory(
        path, tmp_path / "traj.xtc", output_contacts_csv=tmp_path / "c.csv",
        output_summary_json=tmp_path / "i.json")
    assert payload["engine"] == "prolif" and payload["summary"]["total_interactions"] == 1


def test_prolif_with_partial_protein_conect_still_guesses_missing_protein_bonds(tmp_path, monkeypatch):
    # PDB 仅有一条蛋白内部 CONECT (0, 1) 而原子 2 缺少键时，不能因已有 1 条键就跳过整组蛋白补猜
    import numpy as np

    path = tmp_path / "partial_conect.pdb"
    path.write_text("\n".join([
        _pdb_line(1, "N", "ALA", "A", 10, element="N"),
        _pdb_line(2, "CA", "ALA", "A", 10, element="C"),
        _pdb_line(3, "C", "ALA", "A", 10, element="C"),
        _pdb_line(4, "C1", "LIG", "B", 1, record="HETATM", element="C"),
        _pdb_line(5, "O1", "LIG", "B", 1, record="HETATM", element="O"),
        "CONECT    1    2",
    ]) + "\n", encoding="utf-8")
    (tmp_path / "traj.xtc").write_bytes(b"")
    guessed = []

    class FakeSelection(FakeAtomGroup):
        def __init__(self, name, indices, atoms, bonds):
            super().__init__(atoms)
            self._name, self._indices, self._bonds = name, indices, bonds

        @property
        def indices(self):
            return self._indices

        def guess_bonds(self):
            guessed.append(self._name)
            extra = FakeBond((1, 2), 1.0) if self._name == "protein" else FakeBond((3, 4), 1.0)
            self._bonds.append(extra)

    class LocalUniverse:
        def __init__(self, *_args):
            self.trajectory = FakeTrajectory([0.0])
            self.bonds = [FakeBond((0, 1), 1.0)]  # 仅有 1 条蛋白内部 CONECT；原子 2 无键、配体无键
            p_atoms = [FakeMdaAtom(0, "N"), FakeMdaAtom(1, "CA"), FakeMdaAtom(2, "C")]
            FakeMdaResidue(10, p_atoms)
            l_atoms = [FakeMdaAtom(3, "C1"), FakeMdaAtom(4, "O1")]
            self._p, self._l = p_atoms, l_atoms
            self.atoms = types.SimpleNamespace(guess_bonds=lambda: guessed.append("all"))

        def select_atoms(self, query):
            if query == "protein":
                return FakeSelection("protein", np.array([0, 1, 2]), self._p, self.bonds)
            return FakeSelection("ligand", np.array([3, 4]), self._l, self.bonds)

    class LocalFp:
        def __init__(self, *_args, **_kwargs):
            self.ifp = {0: {("LIG1.B", "ALA10.A"): {"HBDonor": ({"parent_indices": {"protein": [0]},
                                                                   "distance": 2.9},)}}}

        def run(self, *_args, **_kwargs):
            assert sorted(guessed) == ["ligand", "protein"]

        def to_dataframe(self):
            cols = [("LIG1.B", "ALA10.A", "HBDonor")]
            return _FakeDataFrame([[True]], index=[0], columns=cols)

    monkeypatch.setitem(sys.modules, "MDAnalysis", types.SimpleNamespace(Universe=LocalUniverse))
    monkeypatch.setitem(sys.modules, "prolif", types.SimpleNamespace(Fingerprint=LocalFp))
    payload = interactions.analyze_trajectory(
        path, tmp_path / "traj.xtc", output_contacts_csv=tmp_path / "c.csv",
        output_summary_json=tmp_path / "i.json")
    assert payload["engine"] == "prolif" and payload["summary"]["total_interactions"] == 1


def test_prolif_waterbridge_guesses_water_bonds_when_conect_absent(tmp_path, monkeypatch):
    # 启用 WaterBridge 且水分子缺 CONECT 时，构造 Fingerprint 前必须对水选区补猜 O-H 共价键
    import numpy as np

    path = tmp_path / "water_no_conect.pdb"
    path.write_text("\n".join([
        _pdb_line(1, "CA", "ALA", "A", 10, element="C"),
        _pdb_line(2, "C1", "LIG", "B", 1, record="HETATM", element="C"),
        _pdb_line(3, "OW", "SOL", "W", 1, record="HETATM", element="O"),
        _pdb_line(4, "HW1", "SOL", "W", 1, record="HETATM", element="H"),
        "CONECT    2    2",
    ]) + "\n", encoding="utf-8")
    (tmp_path / "traj.xtc").write_bytes(b"")
    guessed = []

    class FakeSelection(FakeAtomGroup):
        def __init__(self, name, indices, atoms, bonds):
            super().__init__(atoms)
            self._name, self._indices, self._bonds = name, indices, bonds

        @property
        def indices(self):
            return self._indices

        def guess_bonds(self):
            guessed.append(self._name)
            if self._name == "water":
                self._bonds.append(FakeBond((2, 3), 1.0))

    class LocalUniverse:
        def __init__(self, *_args):
            self.trajectory = FakeTrajectory([0.0])
            self.bonds = [FakeBond((0, 0), 1.0), FakeBond((1, 1), 1.0)]
            p_atoms = [FakeMdaAtom(0, "CA")]
            FakeMdaResidue(10, p_atoms)
            l_atoms = [FakeMdaAtom(1, "C1")]
            w_atoms = [FakeMdaAtom(2, "OW"), FakeMdaAtom(3, "HW1")]
            self._p, self._l, self._w = p_atoms, l_atoms, w_atoms
            self.atoms = types.SimpleNamespace(guess_bonds=lambda: guessed.append("all"))

        def select_atoms(self, query):
            if query == "protein":
                return FakeSelection("protein", np.array([0]), self._p, self.bonds)
            if query == "resname LIG":
                return FakeSelection("ligand", np.array([1]), self._l, self.bonds)
            return FakeSelection("water", np.array([2, 3]), self._w, self.bonds)

    class LocalFp:
        def __init__(self, interactions_arg, parameters=None):
            assert "WaterBridge" in interactions_arg and parameters["WaterBridge"]["water"].n_atoms == 2
            assert "water" in guessed  # 构造 Fingerprint 前已完成水分子 O-H 键补猜
            self.ifp = {0: {("LIG1.B", "ALA10.A"): {"WaterBridge": ({"parent_indices": {"protein": [0]},
                                                                       "distance": 2.8},)}}}

        def run(self, *_args, **_kwargs):
            return None

        def to_dataframe(self):
            cols = [("LIG1.B", "ALA10.A", "WaterBridge")]
            return _FakeDataFrame([[True]], index=[0], columns=cols)

    monkeypatch.setitem(sys.modules, "MDAnalysis", types.SimpleNamespace(Universe=LocalUniverse))
    monkeypatch.setitem(sys.modules, "prolif", types.SimpleNamespace(Fingerprint=LocalFp))
    payload = interactions.analyze_trajectory(
        path, tmp_path / "traj.xtc", output_contacts_csv=tmp_path / "c.csv",
        output_summary_json=tmp_path / "i.json", config=interactions.InteractionConfig(water_resname="SOL"))
    assert payload["engine"] == "prolif" and payload["summary"]["by_type"] == {"water_bridge": 1}


def test_single_chain_is_skipped_without_calling_extractor(tmp_path):
    topology = _write_topology(tmp_path / "topology.pdb", with_ligand=False)
    (tmp_path / "traj.xtc").write_bytes(b"")
    payload = interactions.analyze_trajectory(
        topology, tmp_path / "traj.xtc", output_contacts_csv=tmp_path / "c.csv",
        output_summary_json=tmp_path / "i.json",
        frame_extractor=lambda *_a: (_ for _ in ()).throw(AssertionError("must not be called")))
    assert payload["mode"] == "single_chain" and payload["engine"] == "skipped" and payload["warnings"]
    assert (tmp_path / "c.csv").read_text(encoding="utf-8").splitlines() == [
        ",".join(interactions.CONTACTS_CSV_COLUMNS)]


def test_prolif_failure_falls_back_to_mdtraj(tmp_path, monkeypatch):
    topology = _write_topology(tmp_path / "topology.pdb", with_ligand=True)
    (tmp_path / "traj.xtc").write_bytes(b"")
    monkeypatch.setattr(interactions, "_extract_with_prolif",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("prolif missing")))
    monkeypatch.setattr(interactions, "_extract_with_mdtraj_fallback",
                        lambda *_a, **_k: ([_contact(1, "vdw_contact", distance=0.42)], {1: 0.0}, []))
    payload = interactions.analyze_trajectory(
        topology, tmp_path / "traj.xtc", output_contacts_csv=tmp_path / "c.csv",
        output_summary_json=tmp_path / "i.json")
    assert payload["engine"] == "mdtraj"
    assert any("prolif extraction unavailable" in item for item in payload["warnings"])
    assert payload["summary"]["by_type"] == {"vdw_contact": 1}
    # mdtraj 兜底只应用距离截断：不得把 hbond/hydrophobic/salt_bridge 等未生效阈值写进 cutoffs_nm
    assert payload["cutoffs_nm"] == {"contact": 0.45}
    assert payload["cutoffs_angstrom"] == {"contact": 4.5}


def test_both_backends_failing_raises_runtime_error(tmp_path, monkeypatch):
    topology = _write_topology(tmp_path / "topology.pdb", with_ligand=True)
    (tmp_path / "traj.xtc").write_bytes(b"")
    boom = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("broken"))  # noqa: E731
    monkeypatch.setattr(interactions, "_extract_with_prolif", boom)
    monkeypatch.setattr(interactions, "_extract_with_mdtraj_fallback", boom)
    with pytest.raises(RuntimeError, match="interaction extraction failed"):
        interactions.analyze_trajectory(topology, tmp_path / "traj.xtc", output_contacts_csv=tmp_path / "c.csv",
                                        output_summary_json=tmp_path / "i.json")


def test_analyze_trajectory_mdtraj_fallback_matches_raw_pdb_resname_when_mdtraj_renames_it(tmp_path, monkeypatch):
    # MDTraj 1.10.3 默认会将 ADE/CYT/DAD/DGU/GUA/THY/URA 标准化为 A/C/DA/DG/G/DT/U；
    # 经 analyze_trajectory() 降级进入 mdtraj 时，必须仍能按 PDB 原始残基名 ADE 选中配体并报出接触。
    import numpy as np

    topology = tmp_path / "ade.pdb"
    topology.write_text("\n".join([
        _pdb_line(1, "C1", "ADE", "A", 901, record="HETATM", element="C"),
        _pdb_line(2, "CA", "ALA", "A", 10, element="C"),
    ]) + "\n", encoding="utf-8")
    (tmp_path / "traj.xtc").write_bytes(b"")

    chain_a = FakeChain("A")
    renamed_lig = FakeResidue("A", is_protein=False, resseq=901, chain=chain_a)
    protein_ala = FakeResidue("ALA", is_protein=True, resseq=10, chain=chain_a)
    fake_top = FakeTopology([FakeAtom(0, "C", "C1", renamed_lig), FakeAtom(1, "C", "CA", protein_ala)])

    monkeypatch.setitem(sys.modules, "prolif", None)
    monkeypatch.setitem(sys.modules, "mdtraj", SimpleNamespace(
        load=lambda *a, **k: FakeMdtrajTrajectory(fake_top, 1, [0.30]),
        compute_distances=lambda *a, **k: np.asarray([[0.30]])))

    payload = interactions.analyze_trajectory(
        topology, tmp_path / "traj.xtc", output_contacts_csv=tmp_path / "c.csv",
        output_summary_json=tmp_path / "i.json", config=interactions.InteractionConfig(ligand_resname="ADE"))
    assert payload["mode"] == "protein_ligand" and payload["engine"] == "mdtraj"
    assert payload["summary"]["by_type"] == {"vdw_contact": 1}
    assert "0.3000" in (tmp_path / "c.csv").read_text(encoding="utf-8")


def test_analyze_trajectory_mdtraj_fallback_keeps_alignment_past_extended_resseq_a000(tmp_path, monkeypatch):
    # PDB 扩展残基号 A000（MDTraj 读作 10000）不得导致 _read_pdb_residues 跳过原子而与 MDTraj 原子表错位，
    # 否则会把后续蛋白 GLY 误选成配体 LIG、在 0.50 nm（超过 0.45 nm 阈值）时生成虚假接触。
    import numpy as np

    a000_line = f"{'ATOM':<6s}{1:5d} {'CA':4s} {'ALA':3s} A{'A000'}    {10.0:8.3f}{10.0:8.3f}{10.0:8.3f}  1.00 20.00           C"
    topology = tmp_path / "a000.pdb"
    topology.write_text("\n".join([
        a000_line,
        _pdb_line(2, "CA", "GLY", "A", 1001, element="C"),
        _pdb_line(3, "C1", "LIG", "B", 1, record="HETATM", element="C"),
    ]) + "\n", encoding="utf-8")
    (tmp_path / "traj.xtc").write_bytes(b"")

    atoms_table, _ = interactions._read_pdb_residues(topology, dedupe_altloc=True)
    assert [(r.name, r.seq) for r in atoms_table] == [("ALA", 10000), ("GLY", 1001), ("LIG", 1)]

    chain_a, chain_b = FakeChain("A"), FakeChain("B")
    ala = FakeResidue("ALA", is_protein=True, resseq=10000, chain=chain_a)
    gly = FakeResidue("GLY", is_protein=True, resseq=1001, chain=chain_a)
    lig = FakeResidue("LIG", is_protein=False, resseq=1, chain=chain_b)
    fake_top = FakeTopology([FakeAtom(0, "C", "CA", ala), FakeAtom(1, "C", "CA", gly), FakeAtom(2, "C", "C1", lig)])
    seen_pairs = []

    def fake_distances(_frame, pairs, periodic=False):
        seen_pairs.append([tuple(p) for p in pairs])
        # 若误选了 GLY(1) 与 ALA(0)，返回 0.30 nm 假接触；正确只选 LIG(2) 与 (ALA(0), GLY(1))，均 0.50 nm
        return np.asarray([[0.30 if tuple(p) in ((1, 0), (0, 1)) else 0.50 for p in pairs]])

    monkeypatch.setitem(sys.modules, "prolif", None)
    monkeypatch.setitem(sys.modules, "mdtraj", SimpleNamespace(
        load=lambda *a, **k: FakeMdtrajTrajectory(fake_top, 1, [0.50, 0.50]),
        compute_distances=fake_distances))

    payload = interactions.analyze_trajectory(
        topology, tmp_path / "traj.xtc", output_contacts_csv=tmp_path / "c.csv",
        output_summary_json=tmp_path / "i.json")
    assert payload["engine"] == "mdtraj"
    assert seen_pairs == [[(2, 0), (2, 1)]]
    assert payload["summary"]["total_interactions"] == 0


def test_analyze_trajectory_mdtraj_fallback_hex_2710_after_9999_avoids_decimal_collision(tmp_path, monkeypatch):
    # 9999 之后出现的 2710 属于 VMD 十六进制（10000），不得与前面十进制 2710 碰撞并删原子错位
    import csv
    import numpy as np

    topology = tmp_path / "vmd_hex.pdb"
    topology.write_text("\n".join([
        _pdb_line(1, "CA", "VAL", "A", 2710, element="C"),
        _pdb_line(2, "CA", "VAL", "A", 2711, element="C"),
        _pdb_line(3, "CA", "VAL", "A", 9999, element="C"),
        _pdb_line(4, "CA", "GLY", "A", 2710, element="C"),
        _pdb_line(5, "C1", "LIG", "B", 1, record="HETATM", element="C"),
    ]) + "\n", encoding="utf-8")
    (tmp_path / "traj.xtc").write_bytes(b"")

    chain_a, chain_b = FakeChain("A"), FakeChain("B")
    atoms = [
        FakeAtom(0, "C", "CA", FakeResidue("VAL", is_protein=True, resseq=2710, chain=chain_a)),
        FakeAtom(1, "C", "CA", FakeResidue("VAL", is_protein=True, resseq=2711, chain=chain_a)),
        FakeAtom(2, "C", "CA", FakeResidue("VAL", is_protein=True, resseq=9999, chain=chain_a)),
        FakeAtom(3, "C", "CA", FakeResidue("GLY", is_protein=True, resseq=10000, chain=chain_a)),
        FakeAtom(4, "C", "C1", FakeResidue("LIG", is_protein=False, resseq=1, chain=chain_b)),
    ]
    fake_top = FakeTopology(atoms)
    monkeypatch.setitem(sys.modules, "prolif", None)
    monkeypatch.setitem(sys.modules, "mdtraj", SimpleNamespace(
        load=lambda *a, **k: FakeMdtrajTrajectory(fake_top, 1, [0.50, 0.50, 0.50, 0.30]),
        compute_distances=lambda _f, pairs, periodic=False: np.asarray(
            [[0.30 if tuple(p) == (4, 3) else 0.50 for p in pairs]])))

    csv_path, json_path = tmp_path / "c.csv", tmp_path / "i.json"
    payload = interactions.analyze_trajectory(
        topology, tmp_path / "traj.xtc", output_contacts_csv=csv_path, output_summary_json=json_path)
    with csv_path.open("r", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert [(r["residue_chain"], r["residue_seq"], r["residue_name"], r["mean_distance_nm"]) for r in csv_rows] == [
        ("A", "10000", "GLY", "0.3000")]
    res_nodes = [n for n in payload["network"]["nodes"] if n["kind"] == "residue"]
    assert [(n["id"], n["residue_seq"], n["residue_name"]) for n in res_nodes] == [("A:10000:GLY", 10000, "GLY")]


def test_analyze_trajectory_mdtraj_fallback_overflow_stars_separates_residues(tmp_path, monkeypatch):
    # 9999 之后连续出现多个 **** 残基（包括相同残基名重复），每个新残基必须递增编号而非合并错位
    import csv
    import numpy as np

    star_ala = f"{'ATOM':<6s}{2:5d} {'CA':4s} {'ALA':3s} A****    {10.0:8.3f}{10.0:8.3f}{10.0:8.3f}  1.00 20.00           C"
    star_gly1 = f"{'ATOM':<6s}{3:5d} {'CA':4s} {'GLY':3s} A****    {10.0:8.3f}{10.0:8.3f}{10.0:8.3f}  1.00 20.00           C"
    star_gly2 = f"{'ATOM':<6s}{4:5d} {'CA':4s} {'GLY':3s} A****    {10.0:8.3f}{10.0:8.3f}{10.0:8.3f}  1.00 20.00           C"
    topology = tmp_path / "stars.pdb"
    topology.write_text("\n".join([
        _pdb_line(1, "CA", "VAL", "A", 9999, element="C"),
        star_ala,
        star_gly1,
        star_gly2,
        _pdb_line(5, "C1", "LIG", "B", 1, record="HETATM", element="C"),
    ]) + "\n", encoding="utf-8")
    (tmp_path / "traj.xtc").write_bytes(b"")

    chain_a, chain_b = FakeChain("A"), FakeChain("B")
    atoms = [
        FakeAtom(0, "C", "CA", FakeResidue("VAL", is_protein=True, resseq=9999, chain=chain_a)),
        FakeAtom(1, "C", "CA", FakeResidue("ALA", is_protein=True, resseq=10000, chain=chain_a)),
        FakeAtom(2, "C", "CA", FakeResidue("GLY", is_protein=True, resseq=10001, chain=chain_a)),
        FakeAtom(3, "C", "CA", FakeResidue("GLY", is_protein=True, resseq=10002, chain=chain_a)),
        FakeAtom(4, "C", "C1", FakeResidue("LIG", is_protein=False, resseq=1, chain=chain_b)),
    ]
    fake_top = FakeTopology(atoms)
    monkeypatch.setitem(sys.modules, "prolif", None)
    monkeypatch.setitem(sys.modules, "mdtraj", SimpleNamespace(
        load=lambda *a, **k: FakeMdtrajTrajectory(fake_top, 1, [0.50, 0.50, 0.30, 0.50]),
        compute_distances=lambda _f, pairs, periodic=False: np.asarray(
            [[0.30 if tuple(p) == (4, 2) else 0.50 for p in pairs]])))

    csv_path, json_path = tmp_path / "c.csv", tmp_path / "i.json"
    payload = interactions.analyze_trajectory(
        topology, tmp_path / "traj.xtc", output_contacts_csv=csv_path, output_summary_json=json_path)
    with csv_path.open("r", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert [(r["residue_chain"], r["residue_seq"], r["residue_name"], r["mean_distance_nm"]) for r in csv_rows] == [
        ("A", "10001", "GLY", "0.3000")]
    res_nodes = [n for n in payload["network"]["nodes"] if n["kind"] == "residue"]
    assert [(n["id"], n["residue_seq"], n["residue_name"]) for n in res_nodes] == [("A:10001:GLY", 10001, "GLY")]


def test_read_pdb_residues_overflow_stars_from_decimal_and_hex_keeps_every_residue(tmp_path):
    # B1 回归：9999 同名 HOH/ALA 以及十六进制转 **** 时，首个 **** 残基不得并入前一残基而被吞掉
    def raw_line(serial: int, atom: str, res: str, seq_text: str) -> str:
        return f"ATOM  {serial:5d} {atom:4s} {res:3s} A{seq_text:>4s}    {10.0:8.3f}{10.0:8.3f}{10.0:8.3f}  1.00 20.00           O"

    hoh_pdb = tmp_path / "hoh_stars.pdb"
    lines = [raw_line(1, "O", "HOH", "9999"), raw_line(2, "H1", "HOH", "9999"), raw_line(3, "H2", "HOH", "9999")]
    serial = 4
    for _ in range(3):
        for atom_name in ("O", "H1", "H2"):
            lines.append(raw_line(serial, atom_name, "HOH", "****"))
            serial += 1
    hoh_pdb.write_text("\n".join(lines) + "\n", encoding="utf-8")
    atoms, _ = interactions._read_pdb_residues(hoh_pdb, dedupe_altloc=True)
    assert [(a.name, a.seq) for a in atoms] == (
        [("HOH", 9999)] * 3 + [("HOH", 10000)] * 3 + [("HOH", 10001)] * 3 + [("HOH", 10002)] * 3)

    ala_pdb = tmp_path / "ala_stars.pdb"
    ala_pdb.write_text("\n".join([
        raw_line(1, "N", "ALA", "9999"), raw_line(2, "CA", "ALA", "9999"),
        raw_line(3, "N", "ALA", "****"), raw_line(4, "CA", "ALA", "****"),
    ]) + "\n", encoding="utf-8")
    ala_atoms, _ = interactions._read_pdb_residues(ala_pdb, dedupe_altloc=True)
    assert [(a.name, a.seq) for a in ala_atoms] == [("ALA", 9999), ("ALA", 9999), ("ALA", 10000), ("ALA", 10000)]

    hex_pdb = tmp_path / "hex_stars.pdb"
    hex_pdb.write_text("\n".join([
        raw_line(1, "CA", "HOH", "9999"),
        raw_line(2, "CA", "HOH", "2710"),
        raw_line(3, "CA", "HOH", "FFFF"),
        raw_line(4, "CA", "HOH", "****"),
        raw_line(5, "CA", "HOH", "****"),
    ]) + "\n", encoding="utf-8")
    hex_atoms, _ = interactions._read_pdb_residues(hex_pdb, dedupe_altloc=True)
    assert [a.seq for a in hex_atoms] == [9999, 10000, 65535, 65536, 65537]


def test_read_pdb_residues_chimera_openmm_formula_and_gromacs_wrap(tmp_path):
    # B2/B3 回归：OpenMM A010/A100/B088 单射无碰撞；GROMACS %10000 回绕保留全量原子；10300 水 1:1 保持（不依赖本机 OpenMM）
    def raw_line(serial: int, res: str, seq_text: str) -> str:
        return f"ATOM  {serial:5d}  CA  {res:3s} A{seq_text:>4s}    {10.0:8.3f}{10.0:8.3f}{10.0:8.3f}  1.00 20.00           C"

    chimera_pdb = tmp_path / "chimera.pdb"
    chimera_pdb.write_text("\n".join([
        raw_line(1, "ALA", "A000"), raw_line(2, "ALA", "A010"),
        raw_line(3, "ALA", "A100"), raw_line(4, "ALA", "B088"),
    ]) + "\n", encoding="utf-8")
    ch_atoms, _ = interactions._read_pdb_residues(chimera_pdb, dedupe_altloc=True)
    assert [a.seq for a in ch_atoms] == [10000, 10016, 10256, 14232]

    wrap_pdb = tmp_path / "gmx_wrap.pdb"
    wrap_pdb.write_text("\n".join(raw_line(i, "SOL", str(i % 10000)) for i in range(1, 10006)) + "\n", encoding="utf-8")
    wrap_atoms, _ = interactions._read_pdb_residues(wrap_pdb, dedupe_altloc=True)
    assert len(wrap_atoms) == 10005 and [a.seq for a in wrap_atoms[-7:]] == [9999, 0, 1, 2, 3, 4, 5]

    omm_lines = [
        raw_line(i, "HOH", str(i) if i < 10000 else f"{0xA000 + i - 10000:04X}")
        for i in range(1, 10301)
    ]
    omm_pdb = tmp_path / "openmm_10300.pdb"
    omm_pdb.write_text("\n".join(omm_lines) + "\n", encoding="utf-8")
    kernel_atoms, _ = interactions._read_pdb_residues(omm_pdb, dedupe_altloc=True)
    assert len(kernel_atoms) == 10300 and [a.seq for a in kernel_atoms] == list(range(1, 10301))


def test_read_pdb_residues_keeps_duplicate_atom_name_with_same_altloc(tmp_path):
    # OpenMM/MDTraj Residue._add_atom：同名且同 altLoc（如未区分命名的配体重复 "C" 原子）必须保留，只有不同 altLoc 才合并
    path = tmp_path / "dup_same_altloc.pdb"
    path.write_text("\n".join([
        _pdb_line(1, "C", "LIG", "B", 1, altloc=" ", record="HETATM"),
        _pdb_line(2, "C", "LIG", "B", 1, altloc=" ", record="HETATM"),
        _pdb_line(3, "CB", "ALA", "A", 10, altloc="A"),
        _pdb_line(4, "CB", "ALA", "A", 10, altloc="B"),
    ]) + "\n", encoding="utf-8")
    atoms, _ = interactions._read_pdb_residues(path, dedupe_altloc=True)
    assert [(a.name, a.seq) for a in atoms] == [("LIG", 1), ("LIG", 1), ("ALA", 10)]
