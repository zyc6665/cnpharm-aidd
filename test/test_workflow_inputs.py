from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.common.exceptions import ForbiddenException, NotFoundException  # noqa: E402
from app.models.files import File as FileModel  # noqa: E402
from app.services.workflow_inputs import validate_input_files  # noqa: E402


class FakeDb:
    def __init__(self, files: dict[str, object]) -> None:
        self.files = files
        self.calls: list[tuple[type[FileModel], str]] = []

    async def get(self, model: type[FileModel], file_id: str) -> object | None:
        self.calls.append((model, file_id))
        return self.files.get(file_id)


@pytest.mark.asyncio
async def test_validate_input_files_normalizes_aliases_and_filters_empty_ids() -> None:
    db = FakeDb({"file-1": SimpleNamespace(owner_id="user-1")})
    current_user = SimpleNamespace(id="user-1", role="user")

    normalized = await validate_input_files(
        db,  # type: ignore[arg-type]
        current_user=current_user,  # type: ignore[arg-type]
        input_files={"protein_structure": "file-1", "ligand_pdb": ""},
    )

    assert normalized == {"protein_pdb": "file-1"}
    assert db.calls == [(FileModel, "file-1")]


@pytest.mark.asyncio
async def test_validate_input_files_rejects_missing_files() -> None:
    db = FakeDb({})
    current_user = SimpleNamespace(id="user-1", role="user")

    with pytest.raises(NotFoundException, match="Workflow input file not found: protein_pdb"):
        await validate_input_files(
            db,  # type: ignore[arg-type]
            current_user=current_user,  # type: ignore[arg-type]
            input_files={"protein_pdb": "missing-file"},
        )


@pytest.mark.asyncio
async def test_validate_input_files_requires_owner_or_admin() -> None:
    db = FakeDb({"file-1": SimpleNamespace(owner_id="owner-2")})
    current_user = SimpleNamespace(id="user-1", role="user")

    with pytest.raises(ForbiddenException, match="No permission to use workflow input file"):
        await validate_input_files(
            db,  # type: ignore[arg-type]
            current_user=current_user,  # type: ignore[arg-type]
            input_files={"protein_pdb": "file-1"},
        )

    admin_user = SimpleNamespace(id="user-1", role="admin")
    assert await validate_input_files(
        db,  # type: ignore[arg-type]
        current_user=admin_user,  # type: ignore[arg-type]
        input_files={"protein_pdb": "file-1"},
    ) == {"protein_pdb": "file-1"}
