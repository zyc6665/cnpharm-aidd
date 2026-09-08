from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "backend/scripts/collect_at003_platform_evidence.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("collect_at003_platform_evidence", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_at003_evidence_record_is_rendered_from_platform_task_and_artifacts() -> None:
    module = _load_script_module()
    task = {
        "id": "task-molp-pc-1",
        "project_id": "project-1",
        "tool_slug": "molp-pc-property-prediction",
        "tool_version_id": "tool-version-1",
        "tool": {"current_version": {"version": "0.1.1"}},
        "status": "success",
        "dispatch": {"mode": "celery", "queue": "cpu"},
        "input_bindings": {"molecules": "artifact-version-rdkit"},
        "input_files": [
            {"filename": "rdkit_properties.csv", "sha256": "a" * 64},
        ],
        "output_files": [
            {"filename": "molp_pc_properties.csv", "sha256": "b" * 64},
        ],
    }
    artifacts = [
        {
            "name": "molp-pc-properties",
            "standard_type": "molecule_table@1",
            "latest_version": {
                "id": "artifact-version-properties",
                "sha256": "c" * 64,
                "files": [{"role": "table_file", "sha256": "d" * 64}],
                "manifest_json": {
                    "metadata": {
                        "model_name": "MolP-PC",
                        "model_version": "0.1.1",
                        "endpoint_ref": "local_runtime:molp-pc-property-prediction@0.1.1",
                        "runtime_ref": "runtime-env",
                        "weights_ref": "weights-manifest",
                        "evidence_level": "engineering_smoke_only",
                        "applicability_domain_status": "unknown",
                    }
                },
            },
        },
        {
            "name": "molp-pc-report",
            "standard_type": "run_report@1",
            "latest_version": {"id": "artifact-version-report", "files": []},
        },
    ]

    record = module.build_record_markdown(task, artifacts)

    assert "task-molp-pc-1" in record
    assert "molp-pc-property-prediction" in record
    assert "tool-version-1" in record
    assert "0.1.1" in record
    assert "input_sha256" in record
    assert "aaaaaaaa" in record
    assert "artifact-version-properties" in record
    assert "artifact-version-report" in record
    assert "molecule_table@1" in record
    assert "run_report@1" in record
    assert "engineering_smoke_only" in record
    assert "不得记录 `model/MolP-PC/platform_run.sh`" in record


def test_at003_evidence_rejects_non_platform_molp_pc_task() -> None:
    module = _load_script_module()
    with pytest.raises(ValueError, match="molp-pc-property-prediction"):
        module.build_record_markdown(
            {"id": "task-1", "tool_slug": "builtin-admet-prediction"},
            [],
        )
