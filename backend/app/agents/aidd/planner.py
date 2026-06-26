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
    wants_property = (
        "property_report" in normalized_outputs
        or "性质" in message
        or "property" in message.lower()
    )
    wants_admet = (
        "admet_report" in normalized_outputs
        or "admet" in message.lower()
        or "admet" in message.upper()
    )
    wants_toxicity = (
        "toxicity_report" in normalized_outputs
        or "毒性" in message
        or "toxicity" in message.lower()
    )
    wants_sa = (
        "synthetic_accessibility" in normalized_outputs
        or "合成可及性" in message
        or "synthetic accessibility" in message.lower()
        or "sa score" in message.lower()
    )
    wants_md = (
        "molecular_dynamics_trajectory" in normalized_outputs
        or "分子动力学" in message
        or "molecular dynamics" in message.lower()
        or "md simulation" in message.lower()
    )
    wants_interaction = (
        "interaction_report" in normalized_outputs
        or "相互作用" in message
        or "interaction" in message.lower()
        or "蛋白配体相互作用" in message
    )
    wants_database = (
        "database_query_result" in normalized_outputs
        or "数据库" in message
        or "chembl" in message.lower()
        or "pubchem" in message.lower()
        or "pdbbind" in message.lower()
    )
    wants_property = (
        "property_report" in normalized_outputs
        or "性质" in message
        or "property" in message.lower()
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

    # ------------------------------------------------------------------
    # 数据库查询优先路径：仅请求 database_query_result 时直接查询
    # ------------------------------------------------------------------
    if wants_database and not any([wants_docking, wants_affinity, wants_property, wants_admet, wants_toxicity, wants_sa, wants_md, wants_interaction]):
        if "pubchem" in message.lower() or (normalized_outputs and "pubchem" in str(normalized_outputs).lower()):
            return AIDDPlan(
                intent="query_pubchem",
                requested_outputs=normalized_outputs,
                steps=[
                    AIDDPlanStep(
                        step_key="query_pubchem",
                        tool_slug="builtin-query-pubchem",
                        depends_on=[],
                        inputs={"smiles_csv": "agent_input:smiles_csv"} if input_type == "smiles_csv" else {},
                        params={},
                    )
                ],
            )
        if "pdbbind" in message.lower() or (normalized_outputs and "pdbbind" in str(normalized_outputs).lower()):
            return AIDDPlan(
                intent="query_pdbbind",
                requested_outputs=normalized_outputs,
                steps=[
                    AIDDPlanStep(
                        step_key="query_pdbbind",
                        tool_slug="builtin-query-pdbbind",
                        depends_on=[],
                        inputs={"protein_pdb": "agent_input:protein_pdb"} if input_type == "protein_pdb" else {},
                        params={},
                    )
                ],
            )
        return AIDDPlan(
            intent="query_chembl",
            requested_outputs=normalized_outputs,
            steps=[
                AIDDPlanStep(
                    step_key="query_chembl",
                    tool_slug="builtin-query-chembl",
                    depends_on=[],
                    inputs={"smiles_csv": "agent_input:smiles_csv"} if input_type == "smiles_csv" else {},
                    params={},
                )
            ],
        )

    # ------------------------------------------------------------------
    # 分子级别预测：property / ADMET / toxicity / synthetic accessibility
    # ------------------------------------------------------------------
    wants_molecule_level = wants_property or wants_admet or wants_toxicity or wants_sa
    if wants_molecule_level and input_type == "smiles_csv":
        steps: list[AIDDPlanStep] = []
        if wants_property:
            steps.append(
                AIDDPlanStep(
                    step_key="property_prediction",
                    tool_slug="molp-pc-property-prediction",
                    depends_on=[],
                    inputs={"smiles_csv": "agent_input:smiles_csv"},
                    params={"device": params.get("property_device", "cpu")},
                )
            )
        if wants_admet:
            steps.append(
                AIDDPlanStep(
                    step_key="admet_prediction",
                    tool_slug="builtin-admet-prediction",
                    depends_on=[],
                    inputs={"smiles_csv": "agent_input:smiles_csv"},
                    params={},
                )
            )
        if wants_toxicity:
            steps.append(
                AIDDPlanStep(
                    step_key="toxicity_prediction",
                    tool_slug="builtin-toxicity-prediction",
                    depends_on=[],
                    inputs={"smiles_csv": "agent_input:smiles_csv"},
                    params={},
                )
            )
        if wants_sa:
            steps.append(
                AIDDPlanStep(
                    step_key="synthetic_accessibility",
                    tool_slug="builtin-synthetic-accessibility",
                    depends_on=[],
                    inputs={"smiles_csv": "agent_input:smiles_csv"},
                    params={},
                )
            )
        if not steps:
            steps.append(
                AIDDPlanStep(
                    step_key="property_prediction",
                    tool_slug="molp-pc-property-prediction",
                    depends_on=[],
                    inputs={"smiles_csv": "agent_input:smiles_csv"},
                    params={"device": params.get("property_device", "cpu")},
                )
            )
        return AIDDPlan(
            intent="predict_molecule_properties_from_smiles",
            requested_outputs=normalized_outputs,
            steps=steps,
        )
    if wants_molecule_level and input_type == "generated_ligand":
        steps = [
            AIDDPlanStep(
                step_key="sdf_to_smiles",
                tool_slug="builtin-sdf-to-smiles-csv",
                depends_on=[],
                inputs={"generated_ligand": "agent_input:generated_ligand"},
                params={},
            ),
        ]
        if wants_property:
            steps.append(
                AIDDPlanStep(
                    step_key="property_prediction",
                    tool_slug="molp-pc-property-prediction",
                    depends_on=["sdf_to_smiles"],
                    inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"},
                    params={"device": params.get("property_device", "cpu")},
                )
            )
        if wants_admet:
            steps.append(
                AIDDPlanStep(
                    step_key="admet_prediction",
                    tool_slug="builtin-admet-prediction",
                    depends_on=["sdf_to_smiles"],
                    inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"},
                    params={},
                )
            )
        if wants_toxicity:
            steps.append(
                AIDDPlanStep(
                    step_key="toxicity_prediction",
                    tool_slug="builtin-toxicity-prediction",
                    depends_on=["sdf_to_smiles"],
                    inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"},
                    params={},
                )
            )
        if wants_sa:
            steps.append(
                AIDDPlanStep(
                    step_key="synthetic_accessibility",
                    tool_slug="builtin-synthetic-accessibility",
                    depends_on=["sdf_to_smiles"],
                    inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"},
                    params={},
                )
            )
        if len(steps) == 1:
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
            intent="predict_molecule_properties_from_sdf",
            requested_outputs=normalized_outputs,
            steps=steps,
        )

    # ------------------------------------------------------------------
    # 蛋白/复合物级别：MD / interaction
    # ------------------------------------------------------------------
    if wants_md and {"protein_pdb", "ligand_pdb"}.issubset(available_inputs):
        return AIDDPlan(
            intent="run_molecular_dynamics",
            requested_outputs=normalized_outputs,
            steps=[
                AIDDPlanStep(
                    step_key="molecular_dynamics",
                    tool_slug="builtin-molecular-dynamics",
                    depends_on=[],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "agent_input:ligand_pdb",
                    },
                    params={},
                )
            ],
        )
    if wants_interaction and {"protein_pdb", "ligand_pdb"}.issubset(available_inputs):
        return AIDDPlan(
            intent="analyze_interactions",
            requested_outputs=normalized_outputs,
            steps=[
                AIDDPlanStep(
                    step_key="interaction_analysis",
                    tool_slug="builtin-interaction-analysis",
                    depends_on=[],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "agent_input:ligand_pdb",
                    },
                    params={},
                )
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

    # ------------------------------------------------------------------
    # 在 generation 路径末尾追加 ADMET / toxicity / SA / interaction / MD
    # ------------------------------------------------------------------
    needs_smiles_for_molecule_level = wants_admet or wants_toxicity or wants_sa
    if needs_smiles_for_molecule_level and not any(step.step_key == "sdf_to_smiles" for step in steps):
        steps.append(
            AIDDPlanStep(
                step_key="sdf_to_smiles",
                tool_slug="builtin-sdf-to-smiles-csv",
                depends_on=["molecule_generation"],
                inputs={"generated_ligand": "step:molecule_generation:generated_ligand"},
                params={},
            )
        )
    smiles_source = "step:sdf_to_smiles:smiles_csv" if any(step.step_key == "sdf_to_smiles" for step in steps) else "agent_input:smiles_csv"

    if wants_admet:
        steps.append(
            AIDDPlanStep(
                step_key="admet_prediction",
                tool_slug="builtin-admet-prediction",
                depends_on=["sdf_to_smiles"] if any(step.step_key == "sdf_to_smiles" for step in steps) else [],
                inputs={"smiles_csv": smiles_source},
                params={},
            )
        )
    if wants_toxicity:
        steps.append(
            AIDDPlanStep(
                step_key="toxicity_prediction",
                tool_slug="builtin-toxicity-prediction",
                depends_on=["sdf_to_smiles"] if any(step.step_key == "sdf_to_smiles" for step in steps) else [],
                inputs={"smiles_csv": smiles_source},
                params={},
            )
        )
    if wants_sa:
        steps.append(
            AIDDPlanStep(
                step_key="synthetic_accessibility",
                tool_slug="builtin-synthetic-accessibility",
                depends_on=["sdf_to_smiles"] if any(step.step_key == "sdf_to_smiles" for step in steps) else [],
                inputs={"smiles_csv": smiles_source},
                params={},
            )
        )

    if wants_interaction and input_type == "protein_pdb":
        if not any(step.step_key == "sdf_to_ligand_pdb" for step in steps):
            steps.append(
                AIDDPlanStep(
                    step_key="sdf_to_ligand_pdb",
                    tool_slug="builtin-sdf-to-pdb",
                    depends_on=["molecule_generation"],
                    inputs={"generated_ligand": "step:molecule_generation:generated_ligand"},
                    params={},
                )
            )
        steps.append(
            AIDDPlanStep(
                step_key="interaction_analysis",
                tool_slug="builtin-interaction-analysis",
                depends_on=["sdf_to_ligand_pdb"],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
                params={},
            )
        )

    if wants_md and input_type == "protein_pdb":
        if not any(step.step_key == "sdf_to_ligand_pdb" for step in steps):
            steps.append(
                AIDDPlanStep(
                    step_key="sdf_to_ligand_pdb",
                    tool_slug="builtin-sdf-to-pdb",
                    depends_on=["molecule_generation"],
                    inputs={"generated_ligand": "step:molecule_generation:generated_ligand"},
                    params={},
                )
            )
        steps.append(
            AIDDPlanStep(
                step_key="molecular_dynamics",
                tool_slug="builtin-molecular-dynamics",
                depends_on=["sdf_to_ligand_pdb"],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
                params={},
            )
        )

    return AIDDPlan(
        intent=intent,
        requested_outputs=normalized_outputs,
        steps=steps,
    )
