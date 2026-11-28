"""平台适配层输出上传契约：未声明的可选影片被跳过，其余文件保持原语义。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

_UPLOADER_PATH = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "kubernetes"
    / "model-image-template"
    / "platform_adaptor"
    / "object_storage.py"
)
_spec = importlib.util.spec_from_file_location("object_storage_under_test", _UPLOADER_PATH)
object_storage = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules[_spec.name] = object_storage
_spec.loader.exec_module(object_storage)


class _FakeStorage:
    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes]] = []

    def put_object(self, bucket: str, key: str, handle, size: int, content_type: str | None = None) -> None:
        self.puts.append((key, handle.read()))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_outputs(tmp_path: Path, *, declare_movie: bool) -> Path:
    output_dir = tmp_path / "out"
    (output_dir / "artifacts").mkdir(parents=True)
    topology = output_dir / "artifacts" / "topology.pdb"
    topology.write_text("ATOM      1  CA  ALA A   1\n", encoding="utf-8")
    movie = output_dir / "artifacts" / "trajectory_movie.pdb"
    movie.write_text("MODEL        1\nENDMDL\nEND\n", encoding="utf-8")
    files = {
        "topology_pdb": {"path": "artifacts/topology.pdb", "sha256": _sha256(topology)},
    }
    if declare_movie:
        files["trajectory_movie_pdb"] = {
            "path": "artifacts/trajectory_movie.pdb",
            "sha256": _sha256(movie),
        }
    (output_dir / "result.json").write_text(
        json.dumps(
            {
                "result_version": "aidd.platform/result",
                "artifacts": {
                    "trajectory": {"type": "md_trajectory@1", "files": files},
                },
            }
        ),
        encoding="utf-8",
    )
    return output_dir


def test_upload_skips_undeclared_optional_movie(tmp_path: Path):
    output_dir = _write_outputs(tmp_path, declare_movie=False)
    storage = _FakeStorage()
    uploaded = object_storage.upload_output_directory(
        output_dir=output_dir,
        result_path=output_dir / "result.json",
        storage=storage,
        bucket="bucket",
        prefix="executions/t1",
    )
    assert not any(key.endswith("trajectory_movie.pdb") for key in uploaded)
    assert any(key.endswith("artifacts/topology.pdb") for key in uploaded)
    assert uploaded[-1].endswith("result.json")  # 提交标记仍最后发布


def test_upload_publishes_declared_optional_movie(tmp_path: Path):
    output_dir = _write_outputs(tmp_path, declare_movie=True)
    storage = _FakeStorage()
    uploaded = object_storage.upload_output_directory(
        output_dir=output_dir,
        result_path=output_dir / "result.json",
        storage=storage,
        bucket="bucket",
        prefix="executions/t1",
    )
    assert any(key.endswith("artifacts/trajectory_movie.pdb") for key in uploaded)
    assert uploaded[-1].endswith("result.json")


def test_upload_keeps_other_undeclared_files(tmp_path: Path):
    """豁免只针对影片这一条固定路径；其他未声明文件仍按原语义上传。"""
    output_dir = _write_outputs(tmp_path, declare_movie=False)
    extra = output_dir / "artifacts" / "extra.csv"
    extra.write_text("time,potential\n", encoding="utf-8")
    storage = _FakeStorage()
    uploaded = object_storage.upload_output_directory(
        output_dir=output_dir,
        result_path=output_dir / "result.json",
        storage=storage,
        bucket="bucket",
        prefix="executions/t1",
    )
    assert any(key.endswith("artifacts/extra.csv") for key in uploaded)
