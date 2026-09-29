"""Drug-discovery tool template loading and validation tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.tool_contracts import collect_tool_contract_config_validation_errors  # noqa: E402
from app.services.tool_contracts import build_tool_contract  # noqa: E402
from app.services.tool_import_config import validate_tool_import_config  # noqa: E402
from app.tool_templates.loader import (  # noqa: E402
    ToolTemplateLoadError,
    build_tool_import_config_from_template,
    load_tool_template,
    load_tool_templates,
)
from app.tool_templates.schemas import DrugDiscoveryToolTemplate  # noqa: E402


EXPECTED_TEMPLATE_KEYS = {
    "rdkit-properties",
    "rdkit-sa-score",
    "rdkit-conformer",
    "openbabel-converter",
    "ligand-preparation",
    "vina-docking",
    "smina-docking",
    "docking-rescore",
    "interaction-summary",
    "admet-api",
    "toxicity-api",
    "md-gromacs-ssh",
}


def test_bundled_drug_discovery_templates_are_valid_and_smoke_testable():
    templates = load_tool_templates("drug_discovery")

    assert {template.metadata.template_key for template in templates} == EXPECTED_TEMPLATE_KEYS
    for template in templates:
        assert template.metadata.family == "drug_discovery"
        assert template.agent_capability.enabled is True
        assert template.agent_capability.inputs
        assert template.agent_capability.outputs
        assert template.resource_profile.timeout_minutes >= template.resource_profile.expected_minutes
        assert template.smoke_test.expected_result_version == "aidd.sciminer/result.v2"
        assert template.smoke_test.expected_outputs


def test_templates_declare_one_recommended_implementation():
    template = load_tool_template("vina-docking")

    assert template.implementation.source == "open_source"
    assert template.implementation.provider == "AutoDock Vina"
    assert template.implementation.runtime == "autodock_vina"
    assert template.implementation.recommended_executor == "docker_image"
    assert template.implementation.project_url.startswith("https://")


def test_template_generates_existing_tool_import_config_for_docker_executor():
    template = load_tool_template("vina-docking")

    config = build_tool_import_config_from_template(
        template,
        executor_type="docker_image",
        executor_config={"image": "ghcr.io/sciminer/vina:latest", "command": ["/app/run"]},
    )

    validated = validate_tool_import_config(config)
    tool_config = validated["tool_config"]

    assert validated["slug"] == "vina-docking"
    assert tool_config["type"] == "docker_image"
    assert tool_config["template_key"] == "vina-docking"
    assert tool_config["tool_family"] == "drug_discovery"
    assert tool_config["agent_capability"]["capability"] == "molecular_docking"
    assert tool_config["implementation"]["runtime"] == "autodock_vina"
    assert tool_config["resource_profile"]["tier"] == "medium"
    assert tool_config["output_schema"]["properties"]["result_version"]["const"] == (
        "aidd.sciminer/result.v2"
    )
    assert collect_tool_contract_config_validation_errors(
        tool_slug=validated["slug"],
        config=tool_config,
    ) == []


def test_docking_template_exports_role_aware_artifact_inputs():
    template = load_tool_template("vina-docking")

    config = build_tool_import_config_from_template(
        template,
        executor_type="docker_image",
        executor_config={"image": "ghcr.io/sciminer/vina:latest", "command": ["/app/run"]},
    )
    inputs = config["tool_config"]["artifacts"]["inputs"]

    assert inputs == [
        {
            "name": "protein",
            "type": "protein_structure@1",
            "required": True,
            "role_preferences": ["receptor_pdbqt", "prepared_pdb"],
            "required_roles": ["receptor_pdbqt"],
            "readiness_policy": "require_receptor",
            "suggested_preparation_tool": "builtin-protein-preparation",
        },
        {
            "name": "ligand",
            "type": "ligand_structure@1",
            "required": True,
            "role_preferences": ["structure_3d_sdf", "structure_file"],
            "readiness_policy": "prefer_3d_ligand",
            "suggested_preparation_tool": "builtin-rdkit-conformer",
        },
    ]


def test_ligand_preparation_template_exports_3d_ligand_input_policy():
    template = load_tool_template("ligand-preparation")

    config = build_tool_import_config_from_template(
        template,
        executor_type="docker_image",
        executor_config={"image": "ghcr.io/sciminer/ligand-prep:latest", "command": ["/app/run"]},
    )

    assert config["tool_config"]["artifacts"]["inputs"] == [
        {
            "name": "ligand",
            "type": "ligand_structure@1",
            "required": True,
            "role_preferences": ["structure_3d_sdf", "structure_file", "structure_2d_sdf"],
            "readiness_policy": "allow_raw",
        }
    ]
    assert config["tool_config"]["artifacts"]["outputs"][0] == {
        "name": "ligand",
        "type": "ligand_structure@1",
        "cardinality": "one",
        "required": True,
        "provided_roles": ["structure_3d_sdf", "structure_file"],
    }


def test_template_rejects_output_roles_from_another_artifact_type():
    raw = load_tool_template("ligand-preparation").model_dump(mode="json")
    raw["artifacts"]["outputs"][0]["provided_roles"] = ["receptor_pdbqt"]

    with pytest.raises(ValidationError, match="Unknown file role"):
        DrugDiscoveryToolTemplate.model_validate(raw)


def test_heavy_template_projects_resource_profile_to_existing_tool_fields():
    template = load_tool_template("md-gromacs-ssh")

    config = build_tool_import_config_from_template(
        template,
        executor_type="ssh_job",
        executor_config={
            "host": "gpu-node-01",
            "username": "runner",
            "auth_ref": "secret/md-key",
            "remote_base_dir": "/srv/sciminer/jobs",
            "entrypoint": "/opt/sciminer/run-md.sh",
        },
    )

    assert config["gpu_required"] is True
    assert config["gpu_memory_mb"] == 16384
    assert config["timeout_sec"] == 86400


def test_resource_profile_is_exposed_on_tool_contract():
    template = load_tool_template("vina-docking")
    config = build_tool_import_config_from_template(
        template,
        executor_type="docker_image",
        executor_config={"image": "ghcr.io/sciminer/vina:latest", "command": ["/app/run"]},
    )
    tool_config = config["tool_config"]
    tool = SimpleNamespace(
        id="tool-vina",
        slug=config["slug"],
        name=config["name"],
        description=config["description"],
        status="draft",
        is_public=False,
        current_version=SimpleNamespace(
            id="version-vina",
            version=config["version"],
            is_active=True,
            deprecated=False,
            config=tool_config,
        ),
    )

    contract = build_tool_contract(tool)

    assert contract["resource_profile"] == {
        "tier": "medium",
        "cpu": 8.0,
        "memory_gb": 16.0,
        "gpu_required": False,
        "gpu_memory_gb": 0.0,
        "expected_minutes": 30,
        "timeout_minutes": 180,
        "parallelism": 1,
        "scheduler_hint": "ssh",
    }


def test_template_rejects_non_standard_smoke_test_result_version():
    raw = load_tool_template("rdkit-properties").model_dump(mode="json")
    raw["smoke_test"]["expected_result_version"] = "legacy-result.v1"

    with pytest.raises(ValidationError, match="aidd.sciminer/result.v2"):
        DrugDiscoveryToolTemplate.model_validate(raw)


def test_template_import_config_rejects_unsupported_executor():
    template = load_tool_template("rdkit-properties")

    with pytest.raises(ToolTemplateLoadError, match="executor"):
        build_tool_import_config_from_template(
            template,
            executor_type="slurm",
            executor_config={"partition": "gpu"},
        )


def test_template_generates_k8s_job_config_with_approved_profile_id():
    template = load_tool_template("vina-docking")

    config = build_tool_import_config_from_template(
        template,
        executor_type="k8s_job",
        executor_config={
            "runtime": {"image": f"registry.example/vina@sha256:{'a' * 64}"},
            "resource_profile": "gpu-large",
        },
    )

    validated = validate_tool_import_config(config)
    assert validated["tool_config"]["type"] == "k8s_job"
    assert validated["tool_config"]["runtime"]["image"].endswith("a" * 64)
    assert validated["tool_config"]["resource_profile"] == "gpu-large"
