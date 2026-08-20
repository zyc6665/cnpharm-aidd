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
    source: Literal["output_files", "output_data"]
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
                OutputMatch(extension=".csv"),
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
    "msign-affinity-prediction": ToolCapability(
        tool_slug="msign-affinity-prediction",
        capability="affinity_prediction",
        stage="affinity_prediction",
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
                "affinity_report",
                "output_data",
                path="result.outputs.prediction",
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
    # 化学数据库查询（virtual tools，结果统一输出 database_query_result）
    # ------------------------------------------------------------------
    "builtin-query-chembl": ToolCapability(
        tool_slug="builtin-query-chembl",
        capability="database_query",
        stage="database_query",
        inputs=(
            CapabilityInput(
                "smiles_csv",
                "smiles_csv",
                accepted_extensions=(".csv",),
                required=False,
            ),
        ),
        outputs=(
            CapabilityOutput(
                "database_query_result",
                "output_data",
                path="result.database_query_result",
            ),
        ),
        virtual=True,
    ),
    "builtin-query-pubchem": ToolCapability(
        tool_slug="builtin-query-pubchem",
        capability="database_query",
        stage="database_query",
        inputs=(
            CapabilityInput(
                "smiles_csv",
                "smiles_csv",
                accepted_extensions=(".csv",),
                required=False,
            ),
        ),
        outputs=(
            CapabilityOutput(
                "database_query_result",
                "output_data",
                path="result.database_query_result",
            ),
        ),
        virtual=True,
    ),
    "builtin-query-pdbbind": ToolCapability(
        tool_slug="builtin-query-pdbbind",
        capability="database_query",
        stage="database_query",
        inputs=(
            CapabilityInput(
                "protein_pdb",
                "protein_pdb",
                accepted_extensions=(".pdb",),
                required=False,
            ),
            CapabilityInput(
                "ligand_pdb",
                "ligand_pdb",
                accepted_extensions=(".pdb",),
                required=False,
            ),
        ),
        outputs=(
            CapabilityOutput(
                "database_query_result",
                "output_data",
                path="result.database_query_result",
            ),
        ),
        virtual=True,
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
