"""Deterministic AIDD plan builder."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AIDDPlanStep:
    step_key: str
    tool_slug: str
    depends_on: list[str]
    inputs: dict[str, str]
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIDDPlan:
    intent: str
    requested_outputs: list[str]
    steps: list[AIDDPlanStep]
    reasoning_summary: str | None = None
    analysis_trace: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def infer_aidd_input_type(*, message: str, filename: str) -> str:
    """Infer the semantic input type from uploaded file context and user goal."""

    normalized_filename = filename.lower()
    normalized_message = message.lower()

    pocket_file_markers = ("pocket", "binding_site", "binding-site", "active_site", "active-site")
    protein_file_markers = ("protein", "receptor", "target", "complex")

    if any(marker in normalized_filename for marker in pocket_file_markers):
        return "pocket_pdb"
    if any(marker in normalized_filename for marker in protein_file_markers):
        return "protein_pdb"

    protein_message_markers = (
        "上传蛋白",
        "蛋白质",
        "蛋白",
        "受体",
        "uploaded protein",
        "protein file",
        "protein pdb",
        "receptor",
    )
    pocket_message_markers = (
        "上传口袋",
        "口袋结构",
        "口袋文件",
        "输入口袋",
        "uploaded pocket",
        "pocket file",
        "pocket pdb",
        "pocket structure",
    )

    if any(marker in normalized_message for marker in protein_message_markers):
        return "protein_pdb"
    if any(marker in normalized_message for marker in pocket_message_markers):
        return "pocket_pdb"

    return "protein_pdb"


def build_aidd_plan(
    *,
    message: str,
    input_type: str | None,
    requested_outputs: list[str],
    params: dict[str, Any],
) -> AIDDPlan:
    if not input_type:
        input_type = infer_aidd_input_type(message=message, filename="")

    normalized_outputs = requested_outputs or ["generated_ligand"]
    generation_count = params.get("generation_count")
    available_inputs = set(params.get("available_inputs") or [])
    if input_type:
        available_inputs.add(input_type)

    wants_affinity = (
        "affinity_report" in normalized_outputs
        or "亲和力" in message
        or "affinity" in message.lower()
    )
    wants_docking = (
        "docking_report" in normalized_outputs
        or "ranking_csv" in normalized_outputs
        or "vina" in message.lower()
        or "docking" in message.lower()
        or "对接" in message
        or "排序" in message
    )
    if wants_docking and {"protein_pdb", "ligand_pdb"}.issubset(available_inputs):
        steps = [
            AIDDPlanStep(
                step_key="vina_docking",
                tool_slug="builtin-vina-docking",
                depends_on=[],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "agent_input:ligand_pdb",
                },
                params={},
            )
        ]
        if wants_affinity:
            steps.append(
                AIDDPlanStep(
                    step_key="affinity_prediction",
                    tool_slug="msign-affinity-prediction",
                    depends_on=[],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "agent_input:ligand_pdb",
                    },
                    params={"device": params.get("affinity_device", "cpu")},
                )
            )
        return AIDDPlan(
            intent="dock_uploaded_complex",
            requested_outputs=normalized_outputs,
            steps=steps,
        )
    if wants_affinity and {"protein_pdb", "ligand_pdb"}.issubset(available_inputs):
        return AIDDPlan(
            intent="predict_affinity_from_uploaded_complex",
            requested_outputs=normalized_outputs,
            steps=[
                AIDDPlanStep(
                    step_key="affinity_prediction",
                    tool_slug="msign-affinity-prediction",
                    depends_on=[],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "agent_input:ligand_pdb",
                    },
                    params={"device": params.get("affinity_device", "cpu")},
                )
            ],
        )
    if wants_docking and {"protein_pdb", "generated_ligand"}.issubset(available_inputs):
        steps = [
            AIDDPlanStep(
                step_key="sdf_to_ligand_pdb",
                tool_slug="builtin-sdf-to-pdb",
                depends_on=[],
                inputs={"generated_ligand": "agent_input:generated_ligand"},
                params={},
            ),
            AIDDPlanStep(
                step_key="vina_docking",
                tool_slug="builtin-vina-docking",
                depends_on=["sdf_to_ligand_pdb"],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
                params={},
            ),
        ]
        if wants_affinity:
            steps.append(
                AIDDPlanStep(
                    step_key="affinity_prediction",
                    tool_slug="msign-affinity-prediction",
                    depends_on=["sdf_to_ligand_pdb"],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                    },
                    params={"device": params.get("affinity_device", "cpu")},
                )
            )
        return AIDDPlan(
            intent="dock_uploaded_sdf_ligand",
            requested_outputs=normalized_outputs,
            steps=steps,
        )
    if wants_affinity and {"protein_pdb", "generated_ligand"}.issubset(available_inputs):
        return AIDDPlan(
            intent="predict_affinity_from_uploaded_sdf_ligand",
            requested_outputs=normalized_outputs,
            steps=[
                AIDDPlanStep(
                    step_key="sdf_to_ligand_pdb",
                    tool_slug="builtin-sdf-to-pdb",
                    depends_on=[],
                    inputs={"generated_ligand": "agent_input:generated_ligand"},
                    params={},
                ),
                AIDDPlanStep(
                    step_key="affinity_prediction",
                    tool_slug="msign-affinity-prediction",
                    depends_on=["sdf_to_ligand_pdb"],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                    },
                    params={"device": params.get("affinity_device", "cpu")},
                ),
            ],
        )

    wants_property = (
        "property_report" in normalized_outputs
        or "性质" in message
        or "property" in message.lower()
    )
    if input_type == "smiles_csv":
        return AIDDPlan(
            intent="predict_properties_from_uploaded_smiles",
            requested_outputs=normalized_outputs,
            steps=[
                AIDDPlanStep(
                    step_key="property_prediction",
                    tool_slug="molp-pc-property-prediction",
                    depends_on=[],
                    inputs={"smiles_csv": "agent_input:smiles_csv"},
                    params={"device": params.get("property_device", "cpu")},
                )
            ],
        )
    if input_type == "generated_ligand" and wants_property:
        return AIDDPlan(
            intent="predict_properties_from_uploaded_sdf",
            requested_outputs=normalized_outputs,
            steps=[
                AIDDPlanStep(
                    step_key="sdf_to_smiles",
                    tool_slug="builtin-sdf-to-smiles-csv",
                    depends_on=[],
                    inputs={"generated_ligand": "agent_input:generated_ligand"},
                    params={},
                ),
                AIDDPlanStep(
                    step_key="property_prediction",
                    tool_slug="molp-pc-property-prediction",
                    depends_on=["sdf_to_smiles"],
                    inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"},
                    params={"device": params.get("property_device", "cpu")},
                ),
            ],
        )

    steps: list[AIDDPlanStep] = []
    if input_type == "protein_pdb":
        intent = "generate_molecules_from_protein"
        steps.append(
            AIDDPlanStep(
                step_key="pocket_prediction",
                tool_slug="lvpocket-pocket-prediction",
                depends_on=[],
                inputs={"protein_pdb": "agent_input"},
                params={
                    "model_choice": "auto",
                    "device": params.get("device", "auto"),
                },
            )
        )
        generation_input = "step:pocket_prediction:pocket_pdb"
        generation_depends = ["pocket_prediction"]
    elif input_type == "pocket_pdb":
        intent = "generate_molecules_from_pocket"
        generation_input = "agent_input"
        generation_depends = []
    else:
        raise ValueError(f"Unsupported AIDD input_type: {input_type}")

    generation_params: dict[str, Any] = {
        "params.n_samples": generation_count if generation_count is not None else 8,
        "params.device": params.get("device", "cuda:0"),
    }

    steps.append(
        AIDDPlanStep(
            step_key="molecule_generation",
            tool_slug="gcdm-pocket-generation",
            depends_on=generation_depends,
            inputs={"pocket_pdb": generation_input},
            params=generation_params,
        )
    )

    if (wants_affinity or wants_docking) and input_type == "protein_pdb":
        steps.append(
            AIDDPlanStep(
                step_key="sdf_to_ligand_pdb",
                tool_slug="builtin-sdf-to-pdb",
                depends_on=["molecule_generation"],
                inputs={"generated_ligand": "step:molecule_generation:generated_ligand"},
                params={},
            )
        )
    if wants_docking and input_type == "protein_pdb":
        steps.append(
            AIDDPlanStep(
                step_key="vina_docking",
                tool_slug="builtin-vina-docking",
                depends_on=["sdf_to_ligand_pdb"],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
                params={},
            )
        )

    if wants_affinity and input_type == "protein_pdb":
        steps.append(
            AIDDPlanStep(
                step_key="affinity_prediction",
                tool_slug="msign-affinity-prediction",
                depends_on=["sdf_to_ligand_pdb"],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
                params={"device": params.get("affinity_device", "cpu")},
            )
        )

    if wants_property:
        steps.append(
            AIDDPlanStep(
                step_key="sdf_to_smiles",
                tool_slug="builtin-sdf-to-smiles-csv",
                depends_on=["molecule_generation"],
                inputs={"generated_ligand": "step:molecule_generation:generated_ligand"},
                params={},
            )
        )
        steps.append(
            AIDDPlanStep(
                step_key="property_prediction",
                tool_slug="molp-pc-property-prediction",
                depends_on=["sdf_to_smiles"],
                inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"},
                params={"device": params.get("property_device", "cpu")},
            )
        )

    return AIDDPlan(
        intent=intent,
        requested_outputs=normalized_outputs,
        steps=steps,
    )
