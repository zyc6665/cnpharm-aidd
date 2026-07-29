"""Deterministic AIDD plan builder — dynamic tool slug resolution via registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.agents.aidd.capabilities import AIDD_TOOL_CAPABILITIES


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Capability → tool_slug resolution
# ---------------------------------------------------------------------------

# Priority-ordered tool slugs for each capability.  The first available
# (static or config-based) tool wins.
_CAPABILITY_FALLBACK_SLUG: dict[str, str] = {
    "pocket_prediction": "lvpocket-pocket-prediction",
    "molecule_generation": "gcdm-pocket-generation",
    "affinity_prediction": "msign-affinity-prediction",
    "property_prediction": "molp-pc-property-prediction",
    "docking_scoring": "builtin-vina-docking",
    "admet_prediction": "builtin-admet-prediction",
    "toxicity_prediction": "builtin-toxicity-prediction",
    "synthetic_accessibility": "builtin-synthetic-accessibility",
    "molecular_dynamics": "builtin-molecular-dynamics",
    "interaction_analysis": "builtin-interaction-analysis",
    "format_conversion_sdf_to_smiles": "builtin-sdf-to-smiles-csv",
    "format_conversion_sdf_to_pdb": "builtin-sdf-to-pdb",
    "database_query": "builtin-query-chembl",
}

# Alternative docking tools tried in order when user / config requests a
# specific engine.
_ALTERNATIVE_DOCKING_SLUGS: dict[str, list[str]] = {
    "diffdock": ["builtin-vina-docking"],
    "gnina": ["builtin-vina-docking"],
    "smina": ["builtin-vina-docking"],
    "vina": ["builtin-vina-docking"],
}


def _resolve_tool_slug(capability: str, *, available_slugs: frozenset[str] | None = None) -> str:
    """Return the best available tool slug for a capability.

    Checks (in order):
    1. Static registry for a matching virtual tool
    2. Fallback table
    3. If *available_slugs* is provided, check each fallback against it
    """
    # Check static registry first (virtual tools are always available)
    for slug, cap in AIDD_TOOL_CAPABILITIES.items():
        if cap.capability == capability:
            if available_slugs is None or slug in available_slugs:
                return slug

    # Use fallback table
    fallback = _CAPABILITY_FALLBACK_SLUG.get(capability, "")
    if fallback and (available_slugs is None or fallback in available_slugs):
        return fallback

    # If not found in static and available_slugs provided, try to match any
    # available slug whose static capability matches
    if available_slugs:
        for slug in available_slugs:
            cap = AIDD_TOOL_CAPABILITIES.get(slug)
            if cap and cap.capability == capability:
                return slug

    # Last resort: return the fallback even if not confirmed available
    return fallback or ""


def _resolve_docking_slug(docking_engine: str | None = None) -> str:
    """Return the best docking tool slug based on user preference."""
    engine = (docking_engine or "vina").lower()
    candidates = _ALTERNATIVE_DOCKING_SLUGS.get(engine, _ALTERNATIVE_DOCKING_SLUGS["vina"])
    # First candidate is the preferred one
    return candidates[0]


# ---------------------------------------------------------------------------
# Step builders (DRY helpers)
# ---------------------------------------------------------------------------


def _mk_step(
    step_key: str,
    capability: str,
    depends_on: list[str],
    inputs: dict[str, str],
    params: dict[str, Any] | None = None,
    available_slugs: frozenset[str] | None = None,
) -> AIDDPlanStep:
    return AIDDPlanStep(
        step_key=step_key,
        tool_slug=_resolve_tool_slug(capability, available_slugs=available_slugs),
        depends_on=depends_on,
        inputs=inputs,
        params=params or {},
    )


def _mk_sdf_to_smiles_step(
    depends_on: list[str],
    generated_ligand_source: str = "step:molecule_generation:generated_ligand",
    available_slugs: frozenset[str] | None = None,
) -> AIDDPlanStep:
    return _mk_step(
        "sdf_to_smiles",
        "format_conversion_sdf_to_smiles",
        depends_on=depends_on,
        inputs={"generated_ligand": generated_ligand_source},
        available_slugs=available_slugs,
    )


def _mk_sdf_to_pdb_step(
    depends_on: list[str],
    generated_ligand_source: str = "step:molecule_generation:generated_ligand",
    available_slugs: frozenset[str] | None = None,
) -> AIDDPlanStep:
    return _mk_step(
        "sdf_to_ligand_pdb",
        "format_conversion_sdf_to_pdb",
        depends_on=depends_on,
        inputs={"generated_ligand": generated_ligand_source},
        available_slugs=available_slugs,
    )


def _mk_property_step(
    depends_on: list[str],
    smiles_source: str = "step:sdf_to_smiles:smiles_csv",
    device: str = "cpu",
    available_slugs: frozenset[str] | None = None,
) -> AIDDPlanStep:
    return _mk_step(
        "property_prediction",
        "property_prediction",
        depends_on=depends_on,
        inputs={"smiles_csv": smiles_source},
        params={"device": device},
        available_slugs=available_slugs,
    )


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


def _detect_intents(message: str, normalized_outputs: list[str]) -> dict[str, bool]:
    """Return a dict of detected intents from user message and requested outputs."""
    msg_lower = message.lower()
    return {
        "affinity": (
            "affinity_report" in normalized_outputs
            or "亲和力" in message
            or "affinity" in msg_lower
        ),
        "docking": (
            "docking_pose" in str(normalized_outputs)
            or "docking_report" in normalized_outputs
            or "ranking_csv" in normalized_outputs
            or "vina" in msg_lower
            or "docking" in msg_lower
            or "对接" in message
            or "排序" in message
        ),
        "property": (
            "property_report" in normalized_outputs
            or "性质" in message
            or "property" in msg_lower
        ),
        "admet": (
            "admet_report" in normalized_outputs
            or "admet" in msg_lower
        ),
        "toxicity": (
            "toxicity_report" in normalized_outputs
            or "毒性" in message
            or "toxicity" in msg_lower
        ),
        "sa": (
            "synthetic_accessibility" in normalized_outputs
            or "合成可及性" in message
            or "synthetic accessibility" in msg_lower
            or "sa score" in msg_lower
        ),
        "md": (
            "molecular_dynamics_trajectory" in normalized_outputs
            or "分子动力学" in message
            or "molecular dynamics" in msg_lower
            or "md simulation" in msg_lower
        ),
        "interaction": (
            "interaction_report" in normalized_outputs
            or "相互作用" in message
            or "interaction" in msg_lower
            or "蛋白配体相互作用" in message
        ),
        "database": (
            "database_query_result" in normalized_outputs
            or "数据库" in message
            or "chembl" in msg_lower
            or "pubchem" in msg_lower
            or "pdbbind" in msg_lower
        ),
    }


def _detect_docking_engine(message: str) -> str | None:
    """Detect preferred docking engine from message."""
    msg_lower = message.lower()
    for engine in ("diffdock", "gnina", "smina", "vina"):
        if engine in msg_lower:
            return engine
    return None


def _detect_db_target(message: str, normalized_outputs: list[str]) -> str:
    """Return chembl / pubchem / pdbbind based on message or outputs."""
    msg_lower = message.lower()
    combined = msg_lower + " " + " ".join(normalized_outputs).lower()
    if "pubchem" in combined:
        return "pubchem"
    if "pdbbind" in combined:
        return "pdbbind"
    return "chembl"


# ---------------------------------------------------------------------------
# Input type inference
# ---------------------------------------------------------------------------


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
        "上传蛋白", "蛋白质", "蛋白", "受体",
        "uploaded protein", "protein file", "protein pdb", "receptor",
    )
    pocket_message_markers = (
        "上传口袋", "口袋结构", "口袋文件", "输入口袋",
        "uploaded pocket", "pocket file", "pocket pdb", "pocket structure",
    )
    if any(marker in normalized_message for marker in protein_message_markers):
        return "protein_pdb"
    if any(marker in normalized_message for marker in pocket_message_markers):
        return "pocket_pdb"

    return "protein_pdb"


# ---------------------------------------------------------------------------
# Main plan builder
# ---------------------------------------------------------------------------


def build_aidd_plan(
    *,
    message: str,
    input_type: str | None,
    requested_outputs: list[str],
    params: dict[str, Any],
) -> AIDDPlan:
    """Build a deterministic AIDD execution plan from user intent and inputs."""

    trace: list[str] = []

    if not input_type:
        input_type = infer_aidd_input_type(message=message, filename="")
    trace.append(f"输入类型: {input_type}")

    normalized_outputs = requested_outputs or ["generated_ligand"]
    trace.append(f"请求输出: {normalized_outputs}")

    intents = _detect_intents(message, normalized_outputs)
    trace.append(f"检测意图: {[k for k, v in intents.items() if v]}")

    docking_engine = _detect_docking_engine(message)
    if docking_engine:
        trace.append(f"对接引擎偏好: {docking_engine}")

    generation_count = params.get("generation_count")
    available_inputs = set(params.get("available_inputs") or [])
    if input_type:
        available_inputs.add(input_type)

    # ------------------------------------------------------------------
    # 路径 1: 上传完整复合物 (protein_pdb + ligand_pdb) → 直接对接
    # ------------------------------------------------------------------
    if intents["docking"] and {"protein_pdb", "ligand_pdb"}.issubset(available_inputs):
        trace.append("路径: 上传复合物直接对接")
        docking_slug = _resolve_docking_slug(docking_engine)
        steps = [
            AIDDPlanStep(
                step_key="docking",
                tool_slug=docking_slug,
                depends_on=[],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "agent_input:ligand_pdb",
                },
                params={},
            )
        ]
        if intents["affinity"]:
            steps.append(
                _mk_step(
                    "affinity_prediction",
                    "affinity_prediction",
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
            analysis_trace=trace,
        )

    # ------------------------------------------------------------------
    # 路径 2: 上传复合物 → 仅亲和力
    # ------------------------------------------------------------------
    if intents["affinity"] and {"protein_pdb", "ligand_pdb"}.issubset(available_inputs):
        trace.append("路径: 上传复合物仅亲和力预测")
        return AIDDPlan(
            intent="predict_affinity_from_uploaded_complex",
            requested_outputs=normalized_outputs,
            steps=[
                _mk_step(
                    "affinity_prediction",
                    "affinity_prediction",
                    depends_on=[],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "agent_input:ligand_pdb",
                    },
                    params={"device": params.get("affinity_device", "cpu")},
                )
            ],
            analysis_trace=trace,
        )

    # ------------------------------------------------------------------
    # 路径 3: 对接 + 已有 SDF 配体
    # ------------------------------------------------------------------
    if intents["docking"] and {"protein_pdb", "generated_ligand"}.issubset(available_inputs):
        trace.append("路径: 上传蛋白+SDF配体对接")
        docking_slug = _resolve_docking_slug(docking_engine)
        steps = [
            _mk_sdf_to_pdb_step(depends_on=[]),
            AIDDPlanStep(
                step_key="docking",
                tool_slug=docking_slug,
                depends_on=["sdf_to_ligand_pdb"],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
                params={},
            ),
        ]
        if intents["affinity"]:
            steps.append(
                _mk_step(
                    "affinity_prediction",
                    "affinity_prediction",
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
            analysis_trace=trace,
        )

    # ------------------------------------------------------------------
    # 路径 4: 仅亲和力 + 已有 SDF 配体
    # ------------------------------------------------------------------
    if intents["affinity"] and {"protein_pdb", "generated_ligand"}.issubset(available_inputs):
        trace.append("路径: 上传蛋白+SDF配体仅亲和力")
        return AIDDPlan(
            intent="predict_affinity_from_uploaded_sdf_ligand",
            requested_outputs=normalized_outputs,
            steps=[
                _mk_sdf_to_pdb_step(depends_on=[]),
                _mk_step(
                    "affinity_prediction",
                    "affinity_prediction",
                    depends_on=["sdf_to_ligand_pdb"],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                    },
                    params={"device": params.get("affinity_device", "cpu")},
                ),
            ],
            analysis_trace=trace,
        )

    # ------------------------------------------------------------------
    # 路径 5: 数据库查询独立路径
    # ------------------------------------------------------------------
    molecule_level_intents = (
        intents["docking"] or intents["affinity"] or intents["property"]
        or intents["admet"] or intents["toxicity"] or intents["sa"]
        or intents["md"] or intents["interaction"]
    )
    if intents["database"] and not molecule_level_intents:
        db_target = _detect_db_target(message, normalized_outputs)
        trace.append(f"路径: 独立数据库查询 ({db_target})")

        db_slug_map = {
            "pubchem": "builtin-query-pubchem",
            "pdbbind": "builtin-query-pdbbind",
            "chembl": "builtin-query-chembl",
        }
        db_tool_inputs: dict[str, str] = {}
        if input_type == "smiles_csv":
            db_tool_inputs["smiles_csv"] = "agent_input:smiles_csv"
        elif input_type in ("protein_pdb", "pocket_pdb"):
            db_tool_inputs["protein_pdb"] = f"agent_input:{input_type}"

        return AIDDPlan(
            intent=f"query_{db_target}",
            requested_outputs=normalized_outputs,
            steps=[
                AIDDPlanStep(
                    step_key=f"query_{db_target}",
                    tool_slug=db_slug_map[db_target],
                    depends_on=[],
                    inputs=db_tool_inputs,
                    params={},
                )
            ],
            reasoning_summary=f"独立数据库查询 ({db_target})",
            analysis_trace=trace,
        )

    # ------------------------------------------------------------------
    # 路径 6: smiles_csv → 分子级别分析 (property / ADMET / toxicity / SA)
    # ------------------------------------------------------------------
    wants_molecule_level = (
        intents["property"] or intents["admet"]
        or intents["toxicity"] or intents["sa"]
    )
    if wants_molecule_level and input_type == "smiles_csv":
        trace.append("路径: SMILES直接分子级别分析")
        steps: list[AIDDPlanStep] = []
        if intents["property"]:
            steps.append(_mk_property_step(
                depends_on=[],
                smiles_source="agent_input:smiles_csv",
                device=params.get("property_device", "cpu"),
            ))
        if intents["admet"]:
            steps.append(
                _mk_step("admet_prediction", "admet_prediction",
                         depends_on=[], inputs={"smiles_csv": "agent_input:smiles_csv"})
            )
        if intents["toxicity"]:
            steps.append(
                _mk_step("toxicity_prediction", "toxicity_prediction",
                         depends_on=[], inputs={"smiles_csv": "agent_input:smiles_csv"})
            )
        if intents["sa"]:
            steps.append(
                _mk_step("synthetic_accessibility", "synthetic_accessibility",
                         depends_on=[], inputs={"smiles_csv": "agent_input:smiles_csv"})
            )
        if not steps:
            steps.append(_mk_property_step(
                depends_on=[], smiles_source="agent_input:smiles_csv",
                device=params.get("property_device", "cpu"),
            ))
        return AIDDPlan(
            intent="predict_molecule_properties_from_smiles",
            requested_outputs=normalized_outputs,
            steps=steps,
            analysis_trace=trace,
        )

    # ------------------------------------------------------------------
    # 路径 7: generated_ligand (SDF) → 分子级别分析
    # ------------------------------------------------------------------
    if wants_molecule_level and input_type == "generated_ligand":
        trace.append("路径: SDF转SMILES后分子级别分析")
        steps = [
            _mk_sdf_to_smiles_step(depends_on=[],
                                   generated_ligand_source="agent_input:generated_ligand"),
        ]
        if intents["property"]:
            steps.append(_mk_property_step(
                depends_on=["sdf_to_smiles"],
                device=params.get("property_device", "cpu"),
            ))
        if intents["admet"]:
            steps.append(
                _mk_step("admet_prediction", "admet_prediction",
                         depends_on=["sdf_to_smiles"],
                         inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"})
            )
        if intents["toxicity"]:
            steps.append(
                _mk_step("toxicity_prediction", "toxicity_prediction",
                         depends_on=["sdf_to_smiles"],
                         inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"})
            )
        if intents["sa"]:
            steps.append(
                _mk_step("synthetic_accessibility", "synthetic_accessibility",
                         depends_on=["sdf_to_smiles"],
                         inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"})
            )
        if len(steps) == 1:
            steps.append(_mk_property_step(
                depends_on=["sdf_to_smiles"],
                device=params.get("property_device", "cpu"),
            ))
        return AIDDPlan(
            intent="predict_molecule_properties_from_sdf",
            requested_outputs=normalized_outputs,
            steps=steps,
            analysis_trace=trace,
        )

    # ------------------------------------------------------------------
    # 路径 8: protein_pdb / ligand_pdb → 复合物分析 (MD / interaction)
    # ------------------------------------------------------------------
    if intents["md"] and {"protein_pdb", "ligand_pdb"}.issubset(available_inputs):
        trace.append("路径: 复合物分子动力学模拟")
        return AIDDPlan(
            intent="run_molecular_dynamics",
            requested_outputs=normalized_outputs,
            steps=[
                _mk_step(
                    "molecular_dynamics",
                    "molecular_dynamics",
                    depends_on=[],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "agent_input:ligand_pdb",
                    },
                )
            ],
            analysis_trace=trace,
        )
    if intents["interaction"] and {"protein_pdb", "ligand_pdb"}.issubset(available_inputs):
        trace.append("路径: 复合物相互作用分析")
        return AIDDPlan(
            intent="analyze_interactions",
            requested_outputs=normalized_outputs,
            steps=[
                _mk_step(
                    "interaction_analysis",
                    "interaction_analysis",
                    depends_on=[],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "agent_input:ligand_pdb",
                    },
                )
            ],
            analysis_trace=trace,
        )

    # ------------------------------------------------------------------
    # 路径 9: 从蛋白/口袋出发的完整 generation 管线
    # ------------------------------------------------------------------
    trace.append("路径: 完整分子生成管线")

    steps: list[AIDDPlanStep] = []
    if input_type == "protein_pdb":
        intent = "generate_molecules_from_protein"
        steps.append(
            _mk_step(
                "pocket_prediction",
                "pocket_prediction",
                depends_on=[],
                inputs={"protein_pdb": "agent_input"},
                params={
                    "model_choice": "auto",
                    "device": params.get("device", "auto"),
                },
            )
        )
        generation_depends = ["pocket_prediction"]
        generation_input = "step:pocket_prediction:pocket_pdb"
    elif input_type == "pocket_pdb":
        intent = "generate_molecules_from_pocket"
        generation_depends = []
        generation_input = "agent_input"
    else:
        raise ValueError(f"Unsupported AIDD input_type: {input_type}")

    generation_params: dict[str, Any] = {
        "params.n_samples": generation_count if generation_count is not None else 8,
        "params.device": params.get("device", "cuda:0"),
    }
    steps.append(
        _mk_step(
            "molecule_generation",
            "molecule_generation",
            depends_on=generation_depends,
            inputs={"pocket_pdb": generation_input},
            params=generation_params,
        )
    )

    # --- 数据库查询 (在 generation 之后、对接之前) ---
    if intents["database"]:
        db_target = _detect_db_target(message, normalized_outputs)
        db_slug_map = {
            "pubchem": "builtin-query-pubchem",
            "pdbbind": "builtin-query-pdbbind",
            "chembl": "builtin-query-chembl",
        }
        # Need SMILES for ChEMBL/PubChem query
        if db_target in ("chembl", "pubchem"):
            if not any(s.step_key == "sdf_to_smiles" for s in steps):
                steps.append(
                    _mk_sdf_to_smiles_step(
                        depends_on=["molecule_generation"],
                        generated_ligand_source="step:molecule_generation:generated_ligand",
                    )
                )
            steps.append(
                AIDDPlanStep(
                    step_key=f"query_{db_target}",
                    tool_slug=db_slug_map[db_target],
                    depends_on=["sdf_to_smiles"],
                    inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"},
                    params={},
                )
            )
        elif db_target == "pdbbind":
            steps.append(
                AIDDPlanStep(
                    step_key="query_pdbbind",
                    tool_slug="builtin-query-pdbbind",
                    depends_on=["molecule_generation"],
                    inputs={
                        "protein_pdb": "agent_input:protein_pdb",
                        "ligand_pdb": "step:molecule_generation:generated_ligand",
                    },
                    params={},
                )
            )

    # --- 对接 / 亲和力 (需要 SDF → PDB 转换) ---
    needs_pdb_ligand = (intents["docking"] or intents["affinity"]) and input_type == "protein_pdb"
    if needs_pdb_ligand:
        steps.append(
            _mk_sdf_to_pdb_step(
                depends_on=["molecule_generation"],
                generated_ligand_source="step:molecule_generation:generated_ligand",
            )
        )

    if intents["docking"] and input_type == "protein_pdb":
        docking_slug = _resolve_docking_slug(docking_engine)
        steps.append(
            AIDDPlanStep(
                step_key="docking",
                tool_slug=docking_slug,
                depends_on=["sdf_to_ligand_pdb"],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
                params={},
            )
        )

    if intents["affinity"] and input_type == "protein_pdb":
        steps.append(
            _mk_step(
                "affinity_prediction",
                "affinity_prediction",
                depends_on=["sdf_to_ligand_pdb"],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
                params={"device": params.get("affinity_device", "cpu")},
            )
        )

    # --- 性质预测 ---
    if intents["property"]:
        steps.append(
            _mk_sdf_to_smiles_step(
                depends_on=["molecule_generation"],
                generated_ligand_source="step:molecule_generation:generated_ligand",
            )
        )
        steps.append(
            _mk_property_step(
                depends_on=["sdf_to_smiles"],
                device=params.get("property_device", "cpu"),
            )
        )

    # --- ADMET / toxicity / SA (需要 SMILES) ---
    needs_smiles = intents["admet"] or intents["toxicity"] or intents["sa"]
    if needs_smiles and not any(s.step_key == "sdf_to_smiles" for s in steps):
        steps.append(
            _mk_sdf_to_smiles_step(
                depends_on=["molecule_generation"],
                generated_ligand_source="step:molecule_generation:generated_ligand",
            )
        )
    smiles_source = (
        "step:sdf_to_smiles:smiles_csv"
        if any(s.step_key == "sdf_to_smiles" for s in steps)
        else "agent_input:smiles_csv"
    )
    sdf_to_smiles_depends = (
        ["sdf_to_smiles"]
        if any(s.step_key == "sdf_to_smiles" for s in steps)
        else []
    )

    if intents["admet"]:
        steps.append(
            _mk_step("admet_prediction", "admet_prediction",
                     depends_on=sdf_to_smiles_depends,
                     inputs={"smiles_csv": smiles_source})
        )
    if intents["toxicity"]:
        steps.append(
            _mk_step("toxicity_prediction", "toxicity_prediction",
                     depends_on=sdf_to_smiles_depends,
                     inputs={"smiles_csv": smiles_source})
        )
    if intents["sa"]:
        steps.append(
            _mk_step("synthetic_accessibility", "synthetic_accessibility",
                     depends_on=sdf_to_smiles_depends,
                     inputs={"smiles_csv": smiles_source})
        )

    # --- 相互作用 / MD ---
    if intents["interaction"] and input_type == "protein_pdb":
        if not any(s.step_key == "sdf_to_ligand_pdb" for s in steps):
            steps.append(
                _mk_sdf_to_pdb_step(
                    depends_on=["molecule_generation"],
                    generated_ligand_source="step:molecule_generation:generated_ligand",
                )
            )
        steps.append(
            _mk_step(
                "interaction_analysis",
                "interaction_analysis",
                depends_on=["sdf_to_ligand_pdb"],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
            )
        )

    if intents["md"] and input_type == "protein_pdb":
        if not any(s.step_key == "sdf_to_ligand_pdb" for s in steps):
            steps.append(
                _mk_sdf_to_pdb_step(
                    depends_on=["molecule_generation"],
                    generated_ligand_source="step:molecule_generation:generated_ligand",
                )
            )
        steps.append(
            _mk_step(
                "molecular_dynamics",
                "molecular_dynamics",
                depends_on=["sdf_to_ligand_pdb"],
                inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
            )
        )

    trace.append(f"生成 {len(steps)} 个计划步骤")

    return AIDDPlan(
        intent=intent,
        requested_outputs=normalized_outputs,
        steps=steps,
        reasoning_summary=_build_reasoning_summary(intents, input_type, trace),
        analysis_trace=trace,
    )


def _build_reasoning_summary(
    intents: dict[str, bool], input_type: str, trace: list[str]
) -> str:
    """Build a human-readable reasoning summary."""
    active = [k for k, v in intents.items() if v]
    if not active:
        return f"默认分子生成管线（输入类型: {input_type}）"
    intent_names = {
        "affinity": "亲和力预测",
        "docking": "分子对接",
        "property": "性质预测",
        "admet": "ADMET",
        "toxicity": "毒性预测",
        "sa": "合成可及性",
        "md": "分子动力学模拟",
        "interaction": "相互作用分析",
        "database": "数据库查询",
    }
    parts = [intent_names.get(k, k) for k in active]
    return f"检测到意图: {', '.join(parts)}；输入类型: {input_type}"
