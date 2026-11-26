"""LDDM Tool Package v2 contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tool_packages.kubernetes_binding import build_kubernetes_tool_config  # noqa: E402
from app.tool_packages.loader import load_tool_package  # noqa: E402
from app.tool_packages.schemas import ToolPackageManifest  # noqa: E402
from app.tool_packages.validator import validate_tool_package  # noqa: E402

PACKAGE_ROOT = PROJECT_ROOT / "example" / "lddm" / "tool-package"


def test_lddm_v2_package_validates_and_binds_to_k8s() -> None:
    manifest = load_tool_package(PACKAGE_ROOT)
    result = validate_tool_package(manifest)

    assert isinstance(manifest, ToolPackageManifest)
    assert result.is_valid is True, result.errors
    assert manifest.metadata.slug == "lddm-pocket-ligand-generation"
    assert [item.type for item in manifest.artifacts.inputs] == [
        "protein_structure@1",
        "binding_pocket@1",
        "ligand_structure@1",
        "ligand_structure@1",
    ]
    assert [item.type for item in manifest.artifacts.outputs] == [
        "molecule_table@1",
        "ligand_structure@1",
        "run_report@1",
    ]

    binding = build_kubernetes_tool_config(
        manifest,
        variant_name="nvidia-cuda",
        resource_profile="gpu-large",
    )
    assert binding["type"] == "k8s_job"
    assert binding["runtime"]["image"].endswith(
        "@sha256:9e3594e4c78705907d1db6815fced3541f050a453bf2f44d59ab425a70701c41"
    )
