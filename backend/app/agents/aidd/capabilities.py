"""Static AIDD tool capability registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


SemanticType = Literal[
    "protein_pdb",
    "pocket_pdb",
    "generated_ligand",
    "ligand_pdb",
    "smiles_csv",
    "docking_pose",
    "affinity_report",
    "property_report",
    "optimized_lead",
]


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


@dataclass(frozen=True)
class ToolCapability:
    tool_slug: str
    capability: str
    stage: str
    inputs: tuple[CapabilityInput, ...]
    outputs: tuple[CapabilityOutput, ...]
    defaults: dict[str, object] = field(default_factory=dict)


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
        ),
        defaults={"params.n_samples": 8, "params.device": "cuda:0"},
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
}


def get_capability(tool_slug: str) -> ToolCapability:
    return AIDD_TOOL_CAPABILITIES[tool_slug]


def get_capabilities_by_output(semantic_type: SemanticType) -> list[ToolCapability]:
    return [
        capability
        for capability in AIDD_TOOL_CAPABILITIES.values()
        if any(output.semantic_type == semantic_type for output in capability.outputs)
    ]
