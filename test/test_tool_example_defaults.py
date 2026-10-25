import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.tool_example_defaults import (  # noqa: E402
    get_default_tool_example_from_config,
    select_default_tool_example,
)


def test_default_example_moves_schema_file_params_to_input_files() -> None:
    example = get_default_tool_example_from_config(
        {
            "examples": [
                {
                    "name": "Sample",
                    "params": {
                        "threshold": 0.5,
                        "protein_pdb": "input/protein.pdb",
                    },
                }
            ],
            "input_schema": {
                "type": "object",
                "properties": {
                    "threshold": {"type": "number"},
                    "input_files": {
                        "type": "object",
                        "properties": {
                            "protein_pdb": {
                                "type": "string",
                                "format": "file",
                            },
                        },
                    },
                },
            },
        }
    )

    assert example == {
        "name": "Sample",
        "description": None,
        "params": {"threshold": 0.5},
        "input_files": {"protein_pdb": "input/protein.pdb"},
    }


def test_select_default_tool_example_falls_back_to_schema_value() -> None:
    """未声明 examples 时，应使用 schema 字段自带的 example 生成默认示例。"""
    example = select_default_tool_example(
        [
            {
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "structure_file": {
                            "type": "string",
                            "title": "结构文件",
                            "example": "protein.pdb",
                        },
                    },
                }
            }
        ],
        tool_slug="builtin-protein-preparation",
        base_dir=None,
    )

    assert example == {
        "name": "默认示例",
        "description": "根据工具参数自动生成的示例输入",
        "params": {"structure_file": "protein.pdb"},
        "input_files": {},
    }
