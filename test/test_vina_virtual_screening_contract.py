"""Contract tests for the vina-virtual-screening mock tool package (no container needed)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG = REPO_ROOT / "example" / "mock-models" / "vina-virtual-screening"
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

import importlib.util  # noqa: E402

from app.artifact_standards.registry import get_standard_artifact_spec  # noqa: E402
from app.execution.result_parser import parse_standard_result  # noqa: E402
from app.execution.standard_contracts import DeclaredArtifactOutput  # noqa: E402
from app.tool_packages.loader import load_tool_package  # noqa: E402
from app.tool_packages.validator import validate_tool_package  # noqa: E402

_spec = importlib.util.spec_from_file_location("mock_runner_vina-virtual-screening", PKG / "runner" / "mock_runner.py")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
run_mock = _module.run

EXPECTED_COLUMNS = ["smiles", "inchi_key", "mol_weight", "logp", "qed", "stage_pharmacophore", "stage_docking", "stage_rescore", "docking_score", "rank", "passes"]
EXPECTED_INPUTS = {"receptor": "protein_structure@1", "ligands": "molecule_table@1", "pocket": "binding_pocket@1"}
EXPECTED_OUTPUTS = {"ranked": "molecule_table@1", "poses": "ligand_structure@1", "report": "run_report@1"}


def _manifest():
    return load_tool_package(PKG)


def test_manifest_contract():
    manifest = _manifest()
    result = validate_tool_package(manifest)
    assert result.is_valid, result.errors
    assert manifest.metadata.slug == "vina-virtual-screening"
    assert manifest.metadata.version == "0.1.0"
    assert manifest.metadata.mock is True
    assert {item.name: item.type for item in manifest.artifacts.inputs} == EXPECTED_INPUTS
    assert {item.name: item.type for item in manifest.artifacts.outputs} == EXPECTED_OUTPUTS
    for item in [*manifest.artifacts.inputs, *manifest.artifacts.outputs]:
        get_standard_artifact_spec(item.type)  # raises if unregistered
    assert manifest.exposure.agent and manifest.exposure.workflow and manifest.exposure.direct_run

    variants = {variant.name: variant for variant in manifest.variants}
    local = variants["mock-local"]
    assert local.executor_types == ["cli"]
    assert local.entrypoint == ["python", "runner/mock_runner.py"]
    dcu = variants["haiguang-dcu"]
    assert dcu.executor_types == ["container"]
    assert dcu.image == "harbor.drp.local/drp/compute-vina-virtual-screening:0.1.0-dtk26.04-py3.10"
    assert dcu.validation_status.value == "adapted_pending_hardware_validation"
    assert dcu.hardware_validated is False


def test_runner_outputs_follow_contract(tmp_path):
    manifest = _manifest()
    request = json.loads((PKG / "examples" / "request.json").read_text(encoding="utf-8"))
    request["execution"]["work_dir"] = str(PKG / "examples")
    result = run_mock(request, tmp_path)
    assert result["result_version"] == "aidd.sciminer/result"

    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    declared = [
        DeclaredArtifactOutput(
            name=item.name, type=item.type, cardinality=item.cardinality, required=item.required
        )
        for item in manifest.artifacts.outputs
    ]
    parsed = parse_standard_result(result_path=result_path, output_dir=tmp_path, declared_outputs=declared)
    parsed_by_name = {artifact.output_name: artifact for artifact in parsed.artifacts}

    # every required output is present and its file roles match the standard
    for item in manifest.artifacts.outputs:
        if item.required:
            assert item.name in parsed_by_name
    for artifact in parsed.artifacts:
        spec = get_standard_artifact_spec(artifact.type)
        role_names = {role.role: role for role in spec.file_roles}
        for role, parsed_file in artifact.files.items():
            assert role in role_names, f"unknown file role {role} for {artifact.type}"
            assert parsed_file.path.is_file()

    # mock disclaimer is mandatory on run_report artifacts
    for artifact in parsed.artifacts:
        if artifact.type == "run_report@1":
            report_json = artifact.files["report_json"].path
            payload = json.loads(report_json.read_text(encoding="utf-8"))
            assert payload.get("mock_disclaimer")
            assert payload.get("mock") is True

    # main table columns follow the frozen contract (when a molecule_table is produced)
    table_artifacts = [a for a in parsed.artifacts if a.type == "molecule_table@1"]
    if EXPECTED_COLUMNS and table_artifacts:
        table_artifact = table_artifacts[0]
        table_path = table_artifact.files["table_file"].path
        with open(table_path, newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        for column in EXPECTED_COLUMNS:
            assert column in header, f"missing column {column}"
