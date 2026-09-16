from __future__ import annotations

from pathlib import Path

from app.files import storage_path


def test_get_file_path_uses_safe_filename_basename(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage_path, "STORAGE_PATH", tmp_path)

    assert storage_path.get_file_path("abcdef", "nested/../result.pdb") == (
        tmp_path / "ab" / "abcdef_result.pdb"
    )
    assert storage_path.get_file_path("abcdef", "windows\\nested\\report.json") == (
        tmp_path / "ab" / "abcdef_report.json"
    )


def test_get_file_path_falls_back_when_filename_has_no_basename(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(storage_path, "STORAGE_PATH", tmp_path)

    assert storage_path.get_file_path("abcdef", "..") == tmp_path / "ab" / "abcdef_file"
