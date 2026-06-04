"""AIDD agent tool capability registry tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.capabilities import (  # noqa: E402
    get_capabilities_by_output,
    get_capability,
)


def test_first_wave_capabilities_are_registered() -> None:
    assert get_capability("lvpocket-pocket-prediction").capability == "pocket_prediction"
    assert get_capability("gcdm-pocket-generation").capability == "molecule_generation"
    assert get_capability("molp-pc-property-prediction").capability == "property_prediction"
    assert get_capability("msign-affinity-prediction").capability == "affinity_prediction"


def test_capabilities_advertise_semantic_inputs_and_outputs() -> None:
    lvpocket = get_capability("lvpocket-pocket-prediction")
    assert [item.semantic_type for item in lvpocket.inputs] == ["protein_pdb"]
    assert [item.semantic_type for item in lvpocket.outputs] == ["pocket_pdb"]

    generation = get_capability("gcdm-pocket-generation")
    assert [item.semantic_type for item in generation.inputs] == ["pocket_pdb"]
    assert [item.semantic_type for item in generation.outputs] == ["generated_ligand"]


def test_capability_lookup_by_output() -> None:
    capabilities = get_capabilities_by_output("generated_ligand")
    assert [item.tool_slug for item in capabilities] == ["gcdm-pocket-generation"]
