"""Task service standard Artifact detection tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tasks.service import _tool_config_emits_standard_artifacts  # noqa: E402


def test_tool_config_emits_known_standard_artifact_outputs() -> None:
    config = {"artifacts": {"outputs": [{"name": "pocket", "type": "binding_pocket@1"}]}}

    assert _tool_config_emits_standard_artifacts(config) is True


def test_tool_config_ignores_unknown_versioned_artifact_refs() -> None:
    config = {
        "artifacts": {"outputs": [{"name": "custom", "type": "unknown_output@1"}]},
        "agent_capability": {"outputs": [{"semantic_type": "unknown_output@1"}]},
    }

    assert _tool_config_emits_standard_artifacts(config) is False
