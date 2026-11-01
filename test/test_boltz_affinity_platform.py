"""Contract tests for the Boltz-2 affinity entry script (no container needed)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "deploy" / "model-images" / "k8s" / "boltz2" / "boltz_affinity_platform.py"

_spec = importlib.util.spec_from_file_location("boltz_affinity_platform", SCRIPT)
assert _spec is not None and _spec.loader is not None
module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(module)


def test_clean_sequence_strips_fasta_header_and_normalises() -> None:
    assert module.clean_sequence(">sp|P1|demo\nac def--gh\n") == "ACDEFGH"


def test_clean_sequence_rejects_invalid_residues() -> None:
    with pytest.raises(SystemExit, match="invalid residues"):
        module.clean_sequence("ACDE1FGH")


def test_read_ligands_accepts_smiles_and_id_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "ligands.csv"
    csv_path.write_text(
        "id,SMILES\nGEN-001,CCO\nGEN-002,CCN\nGEN-003,\n",
        encoding="utf-8",
    )
    rows = module.read_ligands(csv_path)
    assert rows == [
        {"molecule_id": "GEN-001", "smiles": "CCO"},
        {"molecule_id": "GEN-002", "smiles": "CCN"},
    ]


def test_read_ligands_requires_smiles_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("name,value\nA,1\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="smiles"):
        module.read_ligands(csv_path)
