"""Standard result.v2 parser and file verification tests."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.execution.result_parser import StandardResultParserError, parse_standard_result
from app.execution.standard_contracts import DeclaredArtifactOutput


def _write_file(path: Path, content: bytes = b"content") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _write_binding_pocket_result(output_dir: Path) -> Path:
    residue_sha = _write_file(output_dir / "artifacts/pocket/residue.pdb", b"residue")
    atom_sha = _write_file(output_dir / "artifacts/pocket/atom.pdb", b"atom")
    metadata_sha = _write_file(output_dir / "artifacts/pocket/metadata.json", b'{"center":[0,0,0]}')
    result_path = output_dir / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "result_version": "aidd.sciminer/result.v2",
                "artifacts": {
                    "pocket": {
                        "name": "Top pocket",
                        "type": "binding_pocket@1",
                        "files": {
                            "residue_pocket_pdb": {
                                "path": "artifacts/pocket/residue.pdb",
                                "sha256": residue_sha,
                            },
                            "atom_pocket_pdb": {
                                "path": "artifacts/pocket/atom.pdb",
                                "sha256": atom_sha,
                            },
                            "pocket_metadata_json": {
                                "path": "artifacts/pocket/metadata.json",
                                "sha256": metadata_sha,
                                "content_type": "application/json",
                            },
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return result_path


def test_parser_reads_result_json_and_returns_normalized_artifacts(tmp_path: Path):
    output_dir = tmp_path / "output"
    result_path = _write_binding_pocket_result(output_dir)

    parsed = parse_standard_result(
        result_path=result_path,
        output_dir=output_dir,
        declared_outputs=[DeclaredArtifactOutput(name="pocket", type="binding_pocket@1")],
    )

    assert len(parsed.artifacts) == 1
    artifact = parsed.artifacts[0]
    assert artifact.output_name == "pocket"
    assert artifact.name == "Top pocket"
    assert artifact.type == "binding_pocket@1"
    assert set(artifact.files) == {
        "residue_pocket_pdb",
        "atom_pocket_pdb",
        "pocket_metadata_json",
    }
    assert artifact.files["pocket_metadata_json"].content_type == "application/json"
    assert artifact.files["atom_pocket_pdb"].path == output_dir / "artifacts/pocket/atom.pdb"


def test_parser_recomputes_hash_and_rejects_mismatch(tmp_path: Path):
    output_dir = tmp_path / "output"
    result_path = _write_binding_pocket_result(output_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["artifacts"]["pocket"]["files"]["atom_pocket_pdb"]["sha256"] = "0" * 64
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StandardResultParserError, match="checksum mismatch"):
        parse_standard_result(
            result_path=result_path,
            output_dir=output_dir,
            declared_outputs=[DeclaredArtifactOutput(name="pocket", type="binding_pocket@1")],
        )


def test_parser_rejects_missing_required_file_role(tmp_path: Path):
    output_dir = tmp_path / "output"
    result_path = _write_binding_pocket_result(output_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    del payload["artifacts"]["pocket"]["files"]["atom_pocket_pdb"]
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StandardResultParserError, match="missing required file roles"):
        parse_standard_result(
            result_path=result_path,
            output_dir=output_dir,
            declared_outputs=[DeclaredArtifactOutput(name="pocket", type="binding_pocket@1")],
        )


def test_parser_rejects_output_path_escaping_output_dir(tmp_path: Path):
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    result_path = output_dir / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "result_version": "aidd.sciminer/result.v2",
                "artifacts": {
                    "report": {
                        "type": "run_report@1",
                        "files": {
                            "report_json": {"path": "../secret.json", "sha256": "1" * 64}
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StandardResultParserError, match="Unsafe output path"):
        parse_standard_result(
            result_path=result_path,
            output_dir=output_dir,
            declared_outputs=[DeclaredArtifactOutput(name="report", type="run_report@1")],
        )


def test_parser_rejects_missing_result_json(tmp_path: Path):
    with pytest.raises(StandardResultParserError, match="Missing standard result"):
        parse_standard_result(
            result_path=tmp_path / "output/result.json",
            output_dir=tmp_path / "output",
            declared_outputs=[DeclaredArtifactOutput(name="report", type="run_report@1")],
        )
