from __future__ import annotations

import hashlib
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.exceptions import ValidationException  # noqa: E402
from app.common.time import utcnow  # noqa: E402
from app.models.files import File as FileModel  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.services.standard_input_upload_plans import (  # noqa: E402
    build_standard_input_upload_plans,
)


class FakeDb:
    def __init__(self, files: dict[str, FileModel]) -> None:
        self.files = files

    async def get(
        self,
        model: type[FileModel],
        file_id: str,
    ) -> FileModel | None:
        assert model is FileModel
        return self.files.get(file_id)


def _tool_and_version(*, input_type: str = "protein_structure@1") -> tuple:
    manifest = {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": "protein-tool",
            "name": "Protein Tool",
            "version": "1.0.0",
        },
        "artifacts": {
            "inputs": [
                {"name": "protein", "type": input_type, "required": True},
            ],
            "outputs": [],
        },
    }
    tool_version = SimpleNamespace(config={"tool_package_manifest": manifest})
    tool = SimpleNamespace(
        id="tool-1",
        slug="protein-tool",
        name="Protein Tool",
        description=None,
        status="published",
        is_public=True,
        current_version=tool_version,
    )
    return tool, tool_version


def _uploaded_file(
    tmp_path: Path,
    *,
    filename: str,
    content: bytes,
) -> FileModel:
    path = tmp_path / filename
    path.write_bytes(content)
    return FileModel(
        id=f"file-{filename}",
        owner_id="user-1",
        filename=filename,
        content_type="chemical/x-pdb",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_path=str(path),
        source_type=FileSourceType.UPLOAD.value,
    )


@pytest.mark.asyncio
async def test_build_standard_input_upload_plan_from_tool_package_manifest(
    tmp_path: Path,
) -> None:
    uploaded_file = _uploaded_file(
        tmp_path,
        filename="protein.pdb",
        content=b"ATOM\n",
    )
    tool, tool_version = _tool_and_version()

    plans = await build_standard_input_upload_plans(
        FakeDb({uploaded_file.id: uploaded_file}),
        tool=tool,
        tool_version=tool_version,
        project_id="project-1",
        standard_input_uploads={" protein ": f" {uploaded_file.id} "},
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.slot_name == "protein"
    assert plan.standard_ref.ref == "protein_structure@1"
    assert plan.primary_role.role == "structure_file"
    assert [role.role for role in plan.required_roles] == [
        "structure_file",
        "metadata_json",
    ]
    assert plan.uploaded_file is uploaded_file
    assert plan.metadata["source"] == "direct_upload"
    assert plan.metadata["input_name"] == "protein"
    assert plan.metadata["standard_type"] == "protein_structure@1"
    assert plan.metadata["atom_count"] == 1


@pytest.mark.asyncio
async def test_build_standard_input_upload_plan_rejects_wrong_primary_format(
    tmp_path: Path,
) -> None:
    uploaded_file = _uploaded_file(
        tmp_path,
        filename="protein.txt",
        content=b"not a pdb\n",
    )
    tool, tool_version = _tool_and_version()

    with pytest.raises(
        ValidationException,
        match="标准 Artifact 上传文件格式不匹配",
    ):
        await build_standard_input_upload_plans(
            FakeDb({uploaded_file.id: uploaded_file}),
            tool=tool,
            tool_version=tool_version,
            project_id="project-1",
            standard_input_uploads={"protein": uploaded_file.id},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        {"expires_at": utcnow() - timedelta(seconds=1)},
        {"deleted_at": utcnow()},
        {"is_corrupted": True},
    ],
)
async def test_build_standard_input_upload_plan_rejects_unusable_file(
    tmp_path: Path,
    state: dict[str, object],
) -> None:
    uploaded_file = _uploaded_file(
        tmp_path,
        filename="protein.pdb",
        content=b"ATOM\n",
    )
    for field, value in state.items():
        setattr(uploaded_file, field, value)
    tool, tool_version = _tool_and_version()

    with pytest.raises(ValidationException) as exc_info:
        await build_standard_input_upload_plans(
            FakeDb({uploaded_file.id: uploaded_file}),
            tool=tool,
            tool_version=tool_version,
            project_id="project-1",
            standard_input_uploads={"protein": uploaded_file.id},
        )

    assert exc_info.value.detail == {"unusable_file_ids": [uploaded_file.id]}
