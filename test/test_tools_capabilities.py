"""AIDD agent tool capability registry tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tools.capabilities import (  # noqa: E402
    get_capabilities_by_output,
    get_capability,
)


def test_first_wave_capabilities_are_registered() -> None:
    assert get_capability("lvpocket-pocket-prediction").capability == "pocket_prediction"
    assert get_capability("gcdm-pocket-generation").capability == "molecule_generation"
    assert get_capability("builtin-protein-preparation").capability == "protein_preparation"
    assert get_capability("builtin-sdf-to-smiles-csv").capability == "format_conversion"
    assert get_capability("builtin-sdf-to-pdb").capability == "format_conversion"
    assert get_capability("builtin-vina-docking").capability == "docking_scoring"
    assert get_capability("builtin-rdkit-properties").capability == "property_prediction"
    assert get_capability("molp-pc-property-prediction").capability == "property_prediction"
    assert get_capability("msign-affinity-prediction").capability == "affinity_prediction"


def test_capabilities_advertise_semantic_inputs_and_outputs() -> None:
    lvpocket = get_capability("lvpocket-pocket-prediction")
    assert [item.semantic_type for item in lvpocket.inputs] == ["protein_pdb"]
    assert [item.semantic_type for item in lvpocket.outputs] == ["pocket_pdb"]

    generation = get_capability("gcdm-pocket-generation")
    assert [item.semantic_type for item in generation.inputs] == ["pocket_pdb"]
    assert [item.semantic_type for item in generation.outputs] == ["generated_ligand", "smiles_csv"]
    assert generation.outputs[1].required is False

    preparation = get_capability("builtin-protein-preparation")
    assert preparation.virtual is True
    assert preparation.stage == "protein_preparation"
    assert [item.semantic_type for item in preparation.inputs] == ["protein_pdb"]
    assert [item.semantic_type for item in preparation.outputs] == ["protein_pdb"]

    conversion = get_capability("builtin-sdf-to-smiles-csv")
    assert conversion.virtual is True
    assert [item.semantic_type for item in conversion.inputs] == ["generated_ligand"]
    assert [item.semantic_type for item in conversion.outputs] == ["smiles_csv"]

    ligand_conversion = get_capability("builtin-sdf-to-pdb")
    assert ligand_conversion.virtual is True
    assert [item.semantic_type for item in ligand_conversion.inputs] == ["generated_ligand"]
    assert [item.semantic_type for item in ligand_conversion.outputs] == ["ligand_pdb"]

    vina = get_capability("builtin-vina-docking")
    assert vina.virtual is True
    assert [item.semantic_type for item in vina.inputs] == ["protein_pdb", "ligand_pdb"]
    assert [item.semantic_type for item in vina.outputs] == ["docking_report", "ranking_csv"]

    rdkit = get_capability("builtin-rdkit-properties")
    assert rdkit.virtual is True
    assert rdkit.stage == "property_prediction"
    assert [item.semantic_type for item in rdkit.inputs] == ["smiles_csv"]
    assert [item.semantic_type for item in rdkit.outputs] == ["property_report"]


def test_capability_lookup_by_output() -> None:
    capabilities = get_capabilities_by_output("generated_ligand")
    assert [item.tool_slug for item in capabilities] == ["gcdm-pocket-generation"]

    ligand_capabilities = get_capabilities_by_output("ligand_pdb")
    assert [item.tool_slug for item in ligand_capabilities] == ["builtin-sdf-to-pdb"]

    # 交付线移除了公网取数工具，protein_structure@1 只剩本地结构预测工具产出。
    assert [item.tool_slug for item in get_capabilities_by_output("protein_structure@1")] == [
        "boltz2-structure-prediction",
    ]

    ligand_artifact_capabilities = get_capabilities_by_output("ligand_structure@1")
    assert [item.tool_slug for item in ligand_artifact_capabilities] == [
        "builtin-ligand-preparation",
        "builtin-rdkit-conformer",
        "vina-virtual-screening",
        "autodock-vina-docking",
        "pocket2mol-pocket-ligand-generation",
    ]

    docking_capabilities = get_capabilities_by_output("docking_report")
    assert [item.tool_slug for item in docking_capabilities] == ["builtin-vina-docking"]

    ranking_capabilities = get_capabilities_by_output("ranking_csv")
    assert [item.tool_slug for item in ranking_capabilities] == ["builtin-vina-docking"]

    property_capabilities = get_capabilities_by_output("property_report")
    assert [item.tool_slug for item in property_capabilities] == [
        "molp-pc-property-prediction",
        "builtin-rdkit-properties",
    ]
