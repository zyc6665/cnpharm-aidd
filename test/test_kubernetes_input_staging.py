"""Kubernetes input staging contract tests."""

from __future__ import annotations

import hashlib
import re
from types import SimpleNamespace

import pytest


class FakeStorage:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.uploads: list[tuple[str, bytes, str | None]] = []

    async def download(self, path: str) -> bytes:
        return self.objects[path]

    async def upload(self, content: bytes, path: str, content_type: str | None = None):
        self.uploads.append((path, content, content_type))
        self.objects[path] = content
        return SimpleNamespace(path=path, size=len(content))


class FakeResult:
    def __init__(self, records):
        self.records = records

    def scalars(self):
        return self

    def all(self):
        return self.records


class FakeDb:
    def __init__(self, records, version_records=None):
        self.records = records
        self.version_records = version_records or []

    async def execute(self, query):
        if "artifact_versions" in str(query).lower():
            return FakeResult(self.version_records)
        return FakeResult(self.records)


@pytest.mark.asyncio
async def test_stage_kubernetes_inputs_uploads_verified_objects():
    from app.services.kubernetes_input_staging import stage_kubernetes_inputs

    content = b"ATOM\nEND\n"
    file_record = SimpleNamespace(
        id="file-1",
        filename="protein.pdb",
        storage_path="source/protein.pdb",
        sha256=hashlib.sha256(content).hexdigest(),
        content_type="chemical/x-pdb",
    )
    storage = FakeStorage({"source/protein.pdb": content})
    task = SimpleNamespace(
        id="task-1",
        inputs=SimpleNamespace(file_ids=["file-1"]),
        extra_data={
            "standard_input_uploads": {"protein": "file-1"},
            "materialized_standard_input_bindings": {
                "protein": "artifact-version-1"
            },
        },
    )

    inputs = await stage_kubernetes_inputs(
        FakeDb([file_record]),
        task=task,
        attempt_id="attempt-1",
        storage=storage,
    )

    assert [item.model_dump(exclude_none=True) for item in inputs] == [
        {
            "artifact_version_id": "artifact-version-1",
            "name": "protein",
            "uri": "inputs/task-1/attempt-1/protein/protein.pdb",
            "sha256": hashlib.sha256(content).hexdigest(),
            "content_type": "chemical/x-pdb",
        }
    ]
    assert storage.uploads == [
        ("inputs/task-1/attempt-1/protein/protein.pdb", content, "chemical/x-pdb")
    ]


@pytest.mark.asyncio
async def test_stage_kubernetes_inputs_reads_local_file_records_without_object_storage(
    tmp_path,
):
    from app.services.kubernetes_input_staging import stage_kubernetes_inputs

    content = b"ATOM\nEND\n"
    source_path = tmp_path / "protein.pdb"
    source_path.write_bytes(content)
    file_record = SimpleNamespace(
        id="file-1",
        filename="protein.pdb",
        storage_backend="local",
        storage_path=str(source_path),
        sha256=hashlib.sha256(content).hexdigest(),
        content_type="chemical/x-pdb",
    )
    storage = FakeStorage({})
    task = SimpleNamespace(
        id="task-1",
        inputs=SimpleNamespace(file_ids=["file-1"]),
        extra_data={},
    )

    await stage_kubernetes_inputs(
        FakeDb([file_record]),
        task=task,
        attempt_id="attempt-1",
        storage=storage,
    )

    assert storage.uploads == [
        ("inputs/task-1/attempt-1/file-0/protein.pdb", content, "chemical/x-pdb")
    ]


@pytest.mark.asyncio
async def test_stage_kubernetes_inputs_expands_standard_binding_files():
    from app.services.kubernetes_input_staging import stage_kubernetes_inputs

    files = {
        "file-residue": b"RESIDUE\n",
        "file-atom": b"ATOM\n",
    }
    file_records = [
        SimpleNamespace(
            id=file_id,
            filename=filename,
            storage_path=storage_path,
            sha256=hashlib.sha256(content).hexdigest(),
            content_type="chemical/x-pdb",
        )
        for file_id, filename, storage_path, content in [
            ("file-residue", "residue.pdb", "pocket/residue.pdb", files["file-residue"]),
            ("file-atom", "atom.pdb", "pocket/atom.pdb", files["file-atom"]),
        ]
    ]
    artifact_version = SimpleNamespace(
        id="artifact-version-1",
        manifest_json={
            "type": "binding_pocket@1",
            "metadata": {"center": [1.0, 2.0, 3.0]},
        },
        artifact=SimpleNamespace(standard_type="binding_pocket", standard_version=1),
        files=[
            SimpleNamespace(file_id="file-residue", role="residue_pocket_pdb"),
            SimpleNamespace(file_id="file-atom", role="atom_pocket_pdb"),
        ],
    )
    storage = FakeStorage(
        {
            "pocket/residue.pdb": files["file-residue"],
            "pocket/atom.pdb": files["file-atom"],
        }
    )
    task = SimpleNamespace(
        id="task-1",
        inputs=SimpleNamespace(file_ids=[]),
        extra_data={"input_bindings": {"pocket": "artifact-version-1"}},
    )

    inputs = await stage_kubernetes_inputs(
        FakeDb(file_records, [artifact_version]),
        task=task,
        attempt_id="attempt-1",
        storage=storage,
    )

    assert {(item.name, item.role) for item in inputs} == {
        ("pocket", "residue_pocket_pdb"),
        ("pocket", "atom_pocket_pdb"),
    }
    assert len(storage.uploads) == 2


@pytest.mark.asyncio
async def test_stage_kubernetes_inputs_preserves_standard_artifact_roles_and_metadata():
    from app.services.kubernetes_input_staging import stage_kubernetes_inputs

    content = b"ATOM\nEND\n"
    file_record = SimpleNamespace(
        id="file-1",
        filename="residue_pocket.pdb",
        storage_path="source/residue_pocket.pdb",
        sha256=hashlib.sha256(content).hexdigest(),
        content_type="chemical/x-pdb",
    )
    artifact_version = SimpleNamespace(
        id="artifact-version-1",
        manifest_json={
            "type": "binding_pocket@1",
            "metadata": {"center": [32.0, 28.0, 36.0]},
        },
        artifact=SimpleNamespace(standard_type="binding_pocket", standard_version=1),
        files=[SimpleNamespace(file_id="file-1", role="residue_pocket_pdb")],
    )
    task = SimpleNamespace(
        id="task-1",
        inputs=SimpleNamespace(file_ids=["file-1"]),
        extra_data={
            "standard_input_uploads": {"pocket": "file-1"},
            "materialized_standard_input_bindings": {"pocket": "artifact-version-1"},
        },
    )

    inputs = await stage_kubernetes_inputs(
        FakeDb([file_record], [artifact_version]),
        task=task,
        attempt_id="attempt-1",
        storage=FakeStorage({"source/residue_pocket.pdb": content}),
    )

    assert inputs[0].role == "residue_pocket_pdb"
    assert inputs[0].artifact_type == "binding_pocket@1"
    assert inputs[0].metadata == {"center": [32.0, 28.0, 36.0]}
    assert inputs[0].content_type == "chemical/x-pdb"


@pytest.mark.asyncio
async def test_stage_kubernetes_inputs_rejects_checksum_mismatch():
    from app.services.kubernetes_input_staging import KubernetesInputStagingError
    from app.services.kubernetes_input_staging import stage_kubernetes_inputs

    content = b"actual"
    file_record = SimpleNamespace(
        id="file-1",
        filename="input.txt",
        storage_path="source/input.txt",
        sha256="0" * 64,
        content_type="text/plain",
    )

    with pytest.raises(KubernetesInputStagingError, match="checksum"):
        await stage_kubernetes_inputs(
            FakeDb([file_record]),
            task=SimpleNamespace(
                id="task-1",
                inputs=SimpleNamespace(file_ids=["file-1"]),
                extra_data={},
            ),
            attempt_id="attempt-1",
            storage=FakeStorage({"source/input.txt": content}),
        )


@pytest.mark.asyncio
async def test_stage_kubernetes_inputs_normalizes_non_ascii_filenames():
    """Candidate-set exports are named after the set ("Pocket2Mol 生成集.csv").

    The staged object key doubles as a Job path segment, so such a name used to
    fail the whole task with "unsafe Kubernetes input path segment".
    """
    from app.services.kubernetes_input_staging import stage_kubernetes_inputs

    content = b"smiles\nCCO\n"
    file_record = SimpleNamespace(
        id="368db3de-979a-475a-9ee9-314311d08209",
        filename="Pocket2Mol 生成集.csv",
        storage_path="source/export.csv",
        sha256=hashlib.sha256(content).hexdigest(),
        content_type="text/csv",
    )
    storage = FakeStorage({"source/export.csv": content})
    task = SimpleNamespace(
        id="task-1",
        inputs=SimpleNamespace(file_ids=["368db3de-979a-475a-9ee9-314311d08209"]),
        extra_data={"standard_input_uploads": {"ligand_smiles": file_record.id}},
    )

    inputs = await stage_kubernetes_inputs(
        FakeDb([file_record]),
        task=task,
        attempt_id="attempt-1",
        storage=storage,
    )

    uri = inputs[0].uri
    assert inputs[0].name == "ligand_smiles"
    assert uri == "inputs/task-1/attempt-1/ligand_smiles/368db3de-Pocket2Mol.csv"
    assert re.fullmatch(r"[A-Za-z0-9_.-]+", uri.rsplit("/", 1)[-1])
    # The name the model sees is the uri basename, so the extension has to survive.
    assert uri.endswith(".csv")


def test_input_filename_keeps_safe_names_and_separates_collisions():
    from app.services.kubernetes_input_staging import _input_filename

    assert _input_filename("protein.pdb", "file-1") == "protein.pdb"
    assert _input_filename("run.tar.gz", "file-1") == "run.tar.gz"
    first = _input_filename("配体 表.csv", "aaaa1111-2b3c")
    second = _input_filename("配体 表.csv", "bbbb2222-9c8d")
    assert first == "aaaa1111-file.csv"
    assert second == "bbbb2222-file.csv"
    assert first != second
    assert _input_filename("..", "file-1") == "file"
