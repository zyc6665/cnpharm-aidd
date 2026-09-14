import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.exceptions import ValidationException  # noqa: E402
from app.services.tool_example_paths import (  # noqa: E402
    guess_tool_example_content_type,
    is_previewable_tool_example_file,
    resolve_tool_example_base_dir,
    resolve_tool_example_file_path,
)


def test_resolve_tool_example_base_dir_uses_configured_relative_path(
    tmp_path: Path,
) -> None:
    tool = SimpleNamespace(slug="demo-tool")

    base_dir = resolve_tool_example_base_dir(
        tool,
        {"example_base_dir": "fixtures/examples"},
        project_root=tmp_path,
    )

    assert base_dir == (tmp_path / "fixtures/examples").resolve()


def test_resolve_tool_example_file_path_rejects_traversal(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationException):
        resolve_tool_example_file_path(tmp_path, "../secret.txt")


def test_guess_and_previewable_helpers_use_file_name() -> None:
    assert guess_tool_example_content_type(Path("sample.pdb")) == (
        "chemical/x-pdb"
    )
    assert is_previewable_tool_example_file(Path("sample.pdb")) is True
    assert is_previewable_tool_example_file(Path("weights.hdf5")) is False
