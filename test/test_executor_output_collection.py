"""Tests for BaseExecutor._collect_output_files consolidation."""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.tasks.executor import BaseExecutor, DockerExecutor, PythonScriptExecutor, SSHJobExecutor


def _build_task():
    return SimpleNamespace(id="task-1", user_id="user-1")


def _build_tool_version(config=None):
    return SimpleNamespace(config=config or {"type": "docker_image"})


@pytest.mark.asyncio
async def test_docker_executor_collect_uses_base_method():
    """DockerExecutor._collect_output_files should pass relative path callbacks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = os.path.join(tmpdir, "work")
        output_dir = os.path.join(work_dir, "output")
        os.makedirs(output_dir)
        with open(os.path.join(output_dir, "a.txt"), "w") as f:
            f.write("a")

        executor = DockerExecutor(_build_task(), _build_tool_version({"type": "docker_image"}))
        executor.work_dir = work_dir

        called_with = None
        called_kwargs = None

        async def fake_collect(self, source_paths, **kwargs):
            nonlocal called_with, called_kwargs
            called_with = source_paths
            called_kwargs = kwargs
            return ["file-1"]

        with patch.object(BaseExecutor, "_collect_output_files", fake_collect):
            result = await executor._collect_output_files()

        assert result == ["file-1"]
        assert called_with is not None
        assert called_kwargs.get("output_root") == output_dir
        assert "filename_builder" in called_kwargs
        assert "file_meta_builder" in called_kwargs
        assert called_kwargs.get("skip_names") == {"result.json"}
        assert any(p.endswith("a.txt") for p in called_with)


@pytest.mark.asyncio
async def test_python_script_executor_collect_skips_result_json():
    """PythonScriptExecutor._collect_output_files should skip result.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = os.path.join(tmpdir, "work")
        output_dir = os.path.join(work_dir, "output")
        os.makedirs(output_dir)
        with open(os.path.join(output_dir, "result.json"), "w") as f:
            f.write('{"ok": true}')
        with open(os.path.join(output_dir, "b.txt"), "w") as f:
            f.write("b")

        executor = PythonScriptExecutor(_build_task(), _build_tool_version({"type": "python_script"}))
        executor.work_dir = work_dir

        called_with = None
        called_kwargs = None

        async def fake_collect(self, source_paths, **kwargs):
            nonlocal called_with, called_kwargs
            called_with = source_paths
            called_kwargs = kwargs
            return ["file-2"]

        with patch.object(BaseExecutor, "_collect_output_files", fake_collect):
            result = await executor._collect_output_files()

        assert result == ["file-2"]
        assert called_kwargs.get("skip_names") == {"result.json"}
        assert any(p.endswith("b.txt") for p in called_with)


@pytest.mark.asyncio
async def test_ssh_executor_collect_uses_relative_path_callbacks():
    """SSHJobExecutor._collect_output_files should pass filename/file_meta builders."""
    with tempfile.TemporaryDirectory() as tmpdir:
        download_root = os.path.join(tmpdir, "download")
        output_root = os.path.join(download_root, "output")
        nested = os.path.join(output_root, "subdir")
        os.makedirs(nested)
        with open(os.path.join(nested, "c.txt"), "w") as f:
            f.write("c")

        executor = SSHJobExecutor(
            _build_task(),
            _build_tool_version({
                "type": "ssh_job",
                "host": "localhost",
                "username": "root",
                "runner_mode": "shell",
            }),
        )

        called_with = None
        called_kwargs = None

        async def fake_collect(self, source_paths, **kwargs):
            nonlocal called_with, called_kwargs
            called_with = source_paths
            called_kwargs = kwargs
            return ["file-3"]

        with patch.object(BaseExecutor, "_collect_output_files", fake_collect):
            result = await executor._collect_output_files(download_root)

        assert result == ["file-3"]
        assert called_kwargs.get("output_root") == output_root
        assert "filename_builder" in called_kwargs
        assert "file_meta_builder" in called_kwargs
        assert called_kwargs.get("skip_names") == {"result.json"}
