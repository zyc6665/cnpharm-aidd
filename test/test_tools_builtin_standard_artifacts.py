"""Builtin standard result.v2 executor tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tools.builtin_tools import BuiltinToolArtifact, BuiltinToolResult
from app.tasks.executors.builtin import BuiltinExecutor


@pytest.mark.asyncio
async def test_builtin_executor_returns_standard_result_v2(tmp_path, monkeypatch):
    input_path = tmp_path / "protein.pdb"
    input_path.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n")
    standard_result = {
        "result_version": "aidd.sciminer/result",
        "artifacts": {
            "prepared_protein": {
                "type": "protein_structure@1",
                "name": "Prepared Protein",
                "files": {
                    "structure_file": {"path": "prepared.pdb", "sha256": "0" * 64},
                    "prepared_pdb": {"path": "prepared.pdb", "sha256": "0" * 64},
                    "receptor_pdbqt": {"path": "receptor.pdbqt", "sha256": "1" * 64},
                },
            }
        },
    }

    async def fake_run_builtin_tool(_slug, files, *, params=None):
        assert files["protein_structure@1"].path == input_path
        assert params == {"builtin_inputs": {"protein_structure@1": "file-protein"}}
        return BuiltinToolResult(
            standard_result=standard_result,
            artifacts=(
                BuiltinToolArtifact(
                    semantic_type="prepared_pdb",
                    filename="prepared.pdb",
                    content=b"ATOM\nEND\n",
                    content_type="chemical/x-pdb",
                ),
            ),
        )

    class FakeScalarResult:
        def scalars(self):
            return self

        def all(self):
            return [
                SimpleNamespace(
                    id="file-protein",
                    filename="protein.pdb",
                    storage_path=str(input_path),
                    content_type="chemical/x-pdb",
                )
            ]

    class FakeSession:
        async def execute(self, _statement):
            return FakeScalarResult()

    async def fake_get_async_session():
        yield FakeSession()

    monkeypatch.setenv("TASK_WORK_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr("app.tools.builtin_tools.run_builtin_tool", fake_run_builtin_tool)
    monkeypatch.setattr("app.tasks.executors.builtin.get_async_session", fake_get_async_session)

    task = SimpleNamespace(
        id="task-1",
        user_id="user-1",
        inputs=SimpleNamespace(params={"builtin_inputs": {"protein_structure@1": "file-protein"}}),
    )
    tool_version = SimpleNamespace(
        config={"type": "builtin", "builtin_slug": "builtin-protein-preparation"}
    )
    executor = BuiltinExecutor(task, tool_version)

    async def fake_collect_output_files(source_paths, *, output_root):
        assert [Path(path).name for path in source_paths] == ["prepared.pdb"]
        assert Path(output_root).name == "output"
        return ["file-prepared"]

    executor._collect_output_files = fake_collect_output_files

    result = await executor.execute()

    assert result["success"] is True
    assert result["result"] == standard_result
    assert result["output_file_ids"] == ["file-prepared"]


@pytest.mark.asyncio
async def test_builtin_executor_allows_parameter_only_tools(tmp_path, monkeypatch):
    standard_result = {
        "result_version": "aidd.sciminer/result",
        "artifacts": {
            "protein": {
                "type": "protein_structure@1",
                "name": "1ABC",
                "files": {
                    "structure_file": {"path": "1ABC.pdb", "sha256": "0" * 64},
                },
            }
        },
    }

    async def fake_run_builtin_tool(_slug, files, *, params=None):
        assert _slug == "builtin-fetch-pdb"
        assert files == {}
        assert params == {"pdb_id": "1abc"}
        return BuiltinToolResult(
            standard_result=standard_result,
            artifacts=(
                BuiltinToolArtifact(
                    semantic_type="protein_structure@1",
                    filename="1ABC.pdb",
                    content=b"HEADER\nEND\n",
                    content_type="chemical/x-pdb",
                ),
            ),
        )

    monkeypatch.setenv("TASK_WORK_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr("app.tools.builtin_tools.run_builtin_tool", fake_run_builtin_tool)

    task = SimpleNamespace(
        id="task-fetch",
        user_id="user-1",
        inputs=SimpleNamespace(params={"pdb_id": "1abc"}),
    )
    tool_version = SimpleNamespace(config={"type": "builtin", "builtin_slug": "builtin-fetch-pdb"})
    executor = BuiltinExecutor(task, tool_version)

    async def fake_collect_output_files(source_paths, *, output_root):
        assert [Path(path).name for path in source_paths] == ["1ABC.pdb"]
        assert Path(output_root).name == "output"
        return ["file-1abc"]

    executor._collect_output_files = fake_collect_output_files

    result = await executor.execute()

    assert result["success"] is True
    assert result["result"] == standard_result
    assert result["output_file_ids"] == ["file-1abc"]
