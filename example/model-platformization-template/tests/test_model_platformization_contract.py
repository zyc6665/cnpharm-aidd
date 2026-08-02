"""Package-local checks for copied model platformization templates."""

from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.execution.result_parser import parse_standard_result  # noqa: E402
from app.execution.standard_contracts import DeclaredArtifactOutput  # noqa: E402


def test_runner_delegates_to_model_side_entrypoint():
    entrypoint = (PACKAGE_ROOT / "runner" / "entrypoint.sh").read_text(encoding="utf-8")

    assert not (PACKAGE_ROOT / "runner" / "platform_adapter.py").exists()
    assert "MODEL_PACKAGE_ROOT" in entrypoint
    assert "platform_run.sh" in entrypoint
    assert "platform_adapter.py" not in entrypoint


def test_example_result_matches_standard_binding_pocket_contract():
    parsed = parse_standard_result(
        result_path=PACKAGE_ROOT / "schemas" / "result.v2.example.json",
        output_dir=PACKAGE_ROOT / "examples" / "output",
        declared_outputs=[
            DeclaredArtifactOutput(name="pocket", type="binding_pocket@1"),
            DeclaredArtifactOutput(name="report", type="run_report@1", required=False),
        ],
    )

    pocket = next(artifact for artifact in parsed.artifacts if artifact.output_name == "pocket")

    assert set(pocket.files) == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }
    assert pocket.metadata["source_protein_ref"] == "input:protein"
