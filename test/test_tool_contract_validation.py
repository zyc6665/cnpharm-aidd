import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.tool_contract_validation import (  # noqa: E402
    collect_tool_contract_config_validation_errors,
)


def test_config_validation_accepts_parameter_only_capability() -> None:
    errors = collect_tool_contract_config_validation_errors(
        tool_slug="builtin-fetch-pdb",
        config={
            "type": "builtin",
            "input_schema": {
                "type": "object",
                "properties": {"pdb_id": {"type": "string"}},
            },
            "agent_capability": {
                "enabled": True,
                "stage": "data_acquisition",
                "capability": "protein_fetch",
                "inputs": [],
                "outputs": [
                    {
                        "semantic_type": "protein_structure@1",
                        "source": "artifact",
                    }
                ],
            },
        },
    )

    assert errors == []


def test_config_validation_deduplicates_role_errors() -> None:
    config = {
        "type": "builtin",
        "artifacts": {
            "inputs": [
                {
                    "name": "protein",
                    "type": "protein_structure@1",
                    "role_preferences": ["not-a-role", "not-a-role"],
                }
            ]
        },
    }

    errors = collect_tool_contract_config_validation_errors(
        tool_slug="bad-tool",
        config=config,
    )

    assert len(errors) == 1
    assert errors[0].startswith("artifacts.inputs[0].role_preferences:")
