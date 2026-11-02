"""Static AIDD tool capability registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.services.semantic_types import CanonicalSemanticType

SemanticType = CanonicalSemanticType


@dataclass(frozen=True)
class CapabilityInput:
    semantic_type: SemanticType
    field: str
    required: bool = True
    accepted_extensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutputMatch:
    extension: str | None = None
    filename_contains_any: tuple[str, ...] = ()
    content_type: str | None = None


@dataclass(frozen=True)
class CapabilityOutput:
    semantic_type: SemanticType
    source: Literal["output_files", "output_data", "artifact"]
    match: OutputMatch | None = None
    path: str | None = None
    required: bool = True


@dataclass(frozen=True)
class ToolCapability:
    tool_slug: str
    capability: str
    stage: str
    inputs: tuple[CapabilityInput, ...]
    outputs: tuple[CapabilityOutput, ...]
    defaults: dict[str, object] = field(default_factory=dict)
    virtual: bool = False


AIDD_TOOL_CAPABILITIES: dict[str, ToolCapability] = {
    "lvpocket-pocket-prediction": ToolCapability(
        tool_slug="lvpocket-pocket-prediction",
        capability="pocket_prediction",
        stage="pocket_exploration",
        inputs=(
            CapabilityInput(
                "protein_pdb",
                "protein_pdb",
                accepted_extensions=(".pdb",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "pocket_pdb",
                "output_files",
                OutputMatch(
                    extension=".pdb",
                    filename_contains_any=("protein_pocket_residues", "pocket"),
                ),
            ),
        ),
        defaults={"model_choice": "auto", "device": "auto"},
    ),
    "gcdm-pocket-generation": ToolCapability(
        tool_slug="gcdm-pocket-generation",
        capability="molecule_generation",
        stage="molecule_generation",
        inputs=(
            CapabilityInput(
                "pocket_pdb",
                "input_files.pocket_pdb",
                accepted_extensions=(".pdb",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "generated_ligand",
                "output_files",
                OutputMatch(extension=".sdf"),
            ),
            CapabilityOutput(
                "smiles_csv",
                "output_files",
                OutputMatch(
                    extension=".csv",
                    filename_contains_any=("smiles", "smile"),
                ),
                required=False,
            ),
        ),
        defaults={"params.n_samples": 8, "params.device": "cuda:0"},
    ),
    "builtin-sdf-to-smiles-csv": ToolCapability(
        tool_slug="builtin-sdf-to-smiles-csv",
        capability="format_conversion",
        stage="artifact_conversion",
        inputs=(
            CapabilityInput(
                "generated_ligand",
                "generated_ligand",
                accepted_extensions=(".sdf",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "smiles_csv",
                "output_files",
                OutputMatch(
                    extension=".csv",
                    filename_contains_any=("smiles",),
                    content_type="text/csv",
                ),
            ),
        ),
        virtual=True,
    ),
    "builtin-protein-preparation": ToolCapability(
        tool_slug="builtin-protein-preparation",
        capability="protein_preparation",
        stage="protein_preparation",
        inputs=(
            CapabilityInput(
                "protein_pdb",
                "protein_pdb",
                accepted_extensions=(".pdb", ".cif"),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "protein_pdb",
                "output_files",
                OutputMatch(
                    extension=".pdb",
                    filename_contains_any=("prepared", "protein"),
                    content_type="chemical/x-pdb",
                ),
            ),
        ),
        virtual=True,
    ),
    "builtin-sdf-to-pdb": ToolCapability(
        tool_slug="builtin-sdf-to-pdb",
        capability="format_conversion",
        stage="artifact_conversion",
        inputs=(
            CapabilityInput(
                "generated_ligand",
                "generated_ligand",
                accepted_extensions=(".sdf",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "ligand_pdb",
                "output_files",
                OutputMatch(
                    extension=".pdb",
                    filename_contains_any=("ligand",),
                    content_type="chemical/x-pdb",
                ),
            ),
        ),
        virtual=True,
    ),
    "builtin-vina-docking": ToolCapability(
        tool_slug="builtin-vina-docking",
        capability="docking_scoring",
        stage="docking_scoring",
        inputs=(
            CapabilityInput(
                "protein_pdb",
                "protein_pdb",
                accepted_extensions=(".pdb",),
            ),
            CapabilityInput(
                "ligand_pdb",
                "ligand_pdb",
                accepted_extensions=(".pdb",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "docking_report",
                "output_files",
                OutputMatch(
                    extension=".json",
                    filename_contains_any=("vina", "docking"),
                    content_type="application/json",
                ),
            ),
            CapabilityOutput(
                "ranking_csv",
                "output_files",
                OutputMatch(
                    extension=".csv",
                    filename_contains_any=("ranking", "vina"),
                    content_type="text/csv",
                ),
            ),
        ),
        virtual=True,
    ),
    "molp-pc-property-prediction": ToolCapability(
        tool_slug="molp-pc-property-prediction",
        capability="molp-pc-property-prediction",
        stage="molp-pc-property-prediction",
        inputs=(
            CapabilityInput("molecule_table@1", "smiles_csv"),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="properties",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        defaults={"device": "cpu"},
    ),
    "builtin-rdkit-properties": ToolCapability(
        tool_slug="builtin-rdkit-properties",
        capability="property_prediction",
        stage="property_prediction",
        inputs=(
            CapabilityInput(
                "smiles_csv",
                "smiles_csv",
                accepted_extensions=(".csv",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "property_report",
                "output_files",
                OutputMatch(
                    extension=".csv",
                    filename_contains_any=("rdkit", "properties"),
                    content_type="text/csv",
                ),
            ),
        ),
        defaults={"smiles_field": "SMILES", "device": "cpu"},
        virtual=True,
    ),
    "builtin-ligand-preparation": ToolCapability(
        tool_slug="builtin-ligand-preparation",
        capability="ligand_preparation",
        stage="ligand_preparation",
        inputs=(
            CapabilityInput(
                "molecule_table@1",
                "molecules",
                accepted_extensions=(".csv", ".json", ".smi", ".txt"),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "output_files",
                OutputMatch(extension=".csv", filename_contains_any=("normalized_molecules",)),
            ),
            CapabilityOutput(
                "ligand_structure@1",
                "output_files",
                OutputMatch(extension=".sdf", filename_contains_any=("prepared_ligands",)),
            ),
            CapabilityOutput(
                "run_report@1",
                "output_files",
                OutputMatch(extension=".json", filename_contains_any=("ligand_preparation_report",)),
            ),
        ),
        defaults={
            "smiles_column": "SMILES",
            "remove_explicit_hydrogens": True,
            "remove_disconnected_fragments": True,
            "normalize_structure": True,
            "reionize": True,
            "neutralize": True,
            "remove_pains": True,
            "remove_duplicates": True,
            "generate_3d": True,
        },
        virtual=True,
    ),
    "builtin-rdkit-conformer": ToolCapability(
        tool_slug="builtin-rdkit-conformer",
        capability="conformer_generation",
        stage="ligand_preparation",
        inputs=(
            CapabilityInput(
                "ligand_structure@1",
                "ligand",
                accepted_extensions=(".sdf", ".mol", ".sd", ".pdb"),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "ligand_structure@1",
                "output_files",
                OutputMatch(extension=".sdf", filename_contains_any=("conformer", "ligand")),
            ),
            CapabilityOutput(
                "run_report@1",
                "output_files",
                OutputMatch(extension=".json", filename_contains_any=("report",)),
                required=False,
            ),
        ),
        defaults={"generate_3d": True, "forcefield": "mmff"},
        virtual=True,
    ),
    "msign-affinity-prediction": ToolCapability(
        tool_slug="msign-affinity-prediction",
        capability="msign-affinity-prediction",
        stage="msign-affinity-prediction",
        inputs=(
            CapabilityInput("protein_structure@1", "protein_pdb"),
            CapabilityInput("ligand_structure@1", "ligand_sdf", required=False),
            CapabilityInput("molecule_table@1", "ligand_smiles", required=False),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="affinity",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        defaults={"device": "cpu"},
    ),
    # ------------------------------------------------------------------
    # ADMET / 毒性 / 合成可及性（基于 SMILES 列表）
    # ------------------------------------------------------------------
    "builtin-admet-prediction": ToolCapability(
        tool_slug="builtin-admet-prediction",
        capability="admet_prediction",
        stage="admet_prediction",
        inputs=(
            CapabilityInput(
                "smiles_csv",
                "smiles_csv",
                accepted_extensions=(".csv",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "admet_report",
                "output_files",
                OutputMatch(
                    extension=".csv",
                    filename_contains_any=("admet",),
                    content_type="text/csv",
                ),
            ),
        ),
        virtual=True,
    ),
    "builtin-toxicity-prediction": ToolCapability(
        tool_slug="builtin-toxicity-prediction",
        capability="toxicity_prediction",
        stage="toxicity_prediction",
        inputs=(
            CapabilityInput(
                "smiles_csv",
                "smiles_csv",
                accepted_extensions=(".csv",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "toxicity_report",
                "output_files",
                OutputMatch(
                    extension=".csv",
                    filename_contains_any=("toxicity", "tox"),
                    content_type="text/csv",
                ),
            ),
        ),
        virtual=True,
    ),
    "builtin-synthetic-accessibility": ToolCapability(
        tool_slug="builtin-synthetic-accessibility",
        capability="synthetic_accessibility",
        stage="synthetic_accessibility",
        inputs=(
            CapabilityInput(
                "smiles_csv",
                "smiles_csv",
                accepted_extensions=(".csv",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "synthetic_accessibility",
                "output_files",
                OutputMatch(
                    extension=".csv",
                    filename_contains_any=("sa", "synthetic_accessibility", "synthetic"),
                    content_type="text/csv",
                ),
            ),
        ),
        virtual=True,
    ),
    # ------------------------------------------------------------------
    # 分子动力学 / 相互作用分析
    # ------------------------------------------------------------------
    "builtin-molecular-dynamics": ToolCapability(
        tool_slug="builtin-molecular-dynamics",
        capability="molecular_dynamics",
        stage="molecular_dynamics",
        inputs=(
            CapabilityInput(
                "protein_pdb",
                "protein_pdb",
                accepted_extensions=(".pdb",),
            ),
            CapabilityInput(
                "ligand_pdb",
                "ligand_pdb",
                accepted_extensions=(".pdb",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "molecular_dynamics_trajectory",
                "output_files",
                OutputMatch(
                    extension=".xtc",
                    filename_contains_any=("trajectory", "traj"),
                ),
                required=False,
            ),
            CapabilityOutput(
                "molecular_dynamics_trajectory",
                "output_files",
                OutputMatch(
                    extension=".dcd",
                    filename_contains_any=("trajectory", "traj"),
                ),
                required=False,
            ),
        ),
        virtual=True,
    ),
    "builtin-interaction-analysis": ToolCapability(
        tool_slug="builtin-interaction-analysis",
        capability="interaction_analysis",
        stage="interaction_analysis",
        inputs=(
            CapabilityInput(
                "protein_pdb",
                "protein_pdb",
                accepted_extensions=(".pdb",),
            ),
            CapabilityInput(
                "ligand_pdb",
                "ligand_pdb",
                accepted_extensions=(".pdb",),
            ),
        ),
        outputs=(
            CapabilityOutput(
                "interaction_report",
                "output_files",
                OutputMatch(
                    extension=".json",
                    filename_contains_any=("interaction",),
                    content_type="application/json",
                ),
            ),
        ),
        virtual=True,
    ),
    # ------------------------------------------------------------------
    # Demo mock model packages (Tool Package v2, metadata.mock=true).
    # Appended for the remaining-pages demonstration flow; the persisted
    # tool_package_manifest remains the primary capability source.
    # ------------------------------------------------------------------
    "std-diff-molecule-generation": ToolCapability(
        tool_slug="std-diff-molecule-generation",
        capability="std-diff-molecule-generation",
        stage="std-diff-molecule-generation",
        inputs=(
            CapabilityInput("binding_pocket@1", "pocket"),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="molecules",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "therapainter-peptide-design": ToolCapability(
        tool_slug="therapainter-peptide-design",
        capability="therapainter-peptide-design",
        stage="therapainter-peptide-design",
        inputs=(
            CapabilityInput("binding_pocket@1", "pocket"),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="peptides",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "admet-prediction": ToolCapability(
        tool_slug="admet-prediction",
        capability="admet-prediction",
        stage="admet-prediction",
        inputs=(
            CapabilityInput("molecule_table@1", "molecules"),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="properties",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "vina-virtual-screening": ToolCapability(
        tool_slug="vina-virtual-screening",
        capability="vina-virtual-screening",
        stage="vina-virtual-screening",
        inputs=(
            CapabilityInput("protein_structure@1", "receptor"),
            CapabilityInput("molecule_table@1", "ligands"),
            CapabilityInput("binding_pocket@1", "pocket", required=False),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="ranked",
            ),
            CapabilityOutput(
                "ligand_structure@1",
                "artifact",
                OutputMatch(content_type="ligand_structure@1"),
                path="poses",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "gromacs-md-simulation": ToolCapability(
        tool_slug="gromacs-md-simulation",
        capability="gromacs-md-simulation",
        stage="gromacs-md-simulation",
        inputs=(
            CapabilityInput("protein_structure@1", "complex"),
        ),
        outputs=(
            CapabilityOutput(
                "md_trajectory@1",
                "artifact",
                OutputMatch(content_type="md_trajectory@1"),
                path="trajectory",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "gmx-mmpbsa-free-energy": ToolCapability(
        tool_slug="gmx-mmpbsa-free-energy",
        capability="gmx-mmpbsa-free-energy",
        stage="gmx-mmpbsa-free-energy",
        inputs=(
            CapabilityInput("md_trajectory@1", "trajectory"),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="energies",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
            ),
        ),
        virtual=False,
    ),
    # ------------------------------------------------------------------
    # 真实工具：依据各 ToolVersion.config 的 tool-package v2 manifest
    # （artifacts.inputs/outputs 标准 Artifact 类型）登记。
    # capability / stage 取 manifest.metadata.slug，与
    # capability_from_tool_package_config 的动态推导保持一致。
    # ------------------------------------------------------------------
    "autodock-vina-docking": ToolCapability(
        tool_slug="autodock-vina-docking",
        capability="autodock-vina-docking",
        stage="autodock-vina-docking",
        inputs=(
            CapabilityInput("protein_structure@1", "protein_pdb"),
            CapabilityInput("ligand_structure@1", "ligand_sdf"),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="docking_results",
            ),
            CapabilityOutput(
                "ligand_structure@1",
                "artifact",
                OutputMatch(content_type="ligand_structure@1"),
                path="docked_poses",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "boltz2-affinity-prediction": ToolCapability(
        tool_slug="boltz2-affinity-prediction",
        capability="boltz2-affinity-prediction",
        stage="boltz2-affinity-prediction",
        inputs=(
            CapabilityInput("molecule_table@1", "ligand_smiles"),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="affinity_table",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "boltz2-structure-prediction": ToolCapability(
        tool_slug="boltz2-structure-prediction",
        capability="boltz2-structure-prediction",
        stage="boltz2-structure-prediction",
        inputs=(),
        outputs=(
            CapabilityOutput(
                "protein_structure@1",
                "artifact",
                OutputMatch(content_type="protein_structure@1"),
                path="predicted_structure",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "gmx-mmpbsa": ToolCapability(
        tool_slug="gmx-mmpbsa",
        capability="gmx-mmpbsa",
        stage="gmx-mmpbsa",
        inputs=(
            CapabilityInput("protein_structure@1", "protein_pdb"),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="binding_energy",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "gromacs-md": ToolCapability(
        tool_slug="gromacs-md",
        capability="gromacs-md",
        stage="gromacs-md",
        inputs=(
            CapabilityInput("protein_structure@1", "protein_pdb"),
        ),
        outputs=(
            CapabilityOutput(
                "md_trajectory@1",
                "artifact",
                OutputMatch(content_type="md_trajectory@1"),
                path="trajectory",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "pocket2mol-pocket-ligand-generation": ToolCapability(
        tool_slug="pocket2mol-pocket-ligand-generation",
        capability="pocket2mol-pocket-ligand-generation",
        stage="pocket2mol-pocket-ligand-generation",
        inputs=(
            CapabilityInput("protein_structure@1", "protein_pdb"),
        ),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="molecules",
            ),
            CapabilityOutput(
                "ligand_structure@1",
                "artifact",
                OutputMatch(content_type="ligand_structure@1"),
                path="ligands",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
    "therapainter-peptide-prediction": ToolCapability(
        tool_slug="therapainter-peptide-prediction",
        capability="therapainter-peptide-prediction",
        stage="therapainter-peptide-prediction",
        inputs=(),
        outputs=(
            CapabilityOutput(
                "molecule_table@1",
                "artifact",
                OutputMatch(content_type="molecule_table@1"),
                path="peptides",
            ),
            CapabilityOutput(
                "run_report@1",
                "artifact",
                OutputMatch(content_type="run_report@1"),
                path="report",
                required=False,
            ),
        ),
        virtual=False,
    ),
}


PLACEHOLDER_AIDD_TOOL_SLUGS = frozenset(
    {
        "builtin-admet-prediction",
        "builtin-toxicity-prediction",
        "builtin-synthetic-accessibility",
        "builtin-molecular-dynamics",
        "builtin-interaction-analysis",
    }
)

for _placeholder_slug in PLACEHOLDER_AIDD_TOOL_SLUGS:
    AIDD_TOOL_CAPABILITIES.pop(_placeholder_slug, None)


def get_capability(tool_slug: str) -> ToolCapability:
    return AIDD_TOOL_CAPABILITIES[tool_slug]


def get_capabilities_by_output(semantic_type: SemanticType) -> list[ToolCapability]:
    return [
        capability
        for capability in AIDD_TOOL_CAPABILITIES.values()
        if any(output.semantic_type == semantic_type for output in capability.outputs)
    ]
