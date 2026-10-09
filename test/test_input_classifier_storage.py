"""Storage-agnostic AIDD input classification tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.aidd.input_classifier import classify_aidd_input_file


@pytest.mark.asyncio
async def test_classifies_minio_csv_from_content_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStorage:
        async def download(self, path: str) -> bytes:
            assert path == "inputs/files/file-1/compounds.csv"
            return b"canonical_smiles,name\nCCO,ethanol\n"

    monkeypatch.setattr(
        "app.files.content.get_storage_backend",
        lambda backend: FakeStorage(),
    )
    file_record = SimpleNamespace(
        id="file-1",
        filename="compounds.csv",
        content_type="text/csv",
        storage_backend="minio",
        storage_path="inputs/files/file-1/compounds.csv",
    )

    classified = await classify_aidd_input_file(
        file_record,
        message="Analyze these compounds",
    )

    assert classified.semantic_type == "smiles_csv"
    assert classified.confidence == 0.96
