"""Build standard platform results from LVpocket legacy outputs."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .io import file_ref, read_json, write_json


LEGACY_ATOM_POCKET_CANDIDATES = (
    "artifacts/lv_results/input/pocket0.pdb",
    "artifacts/lv_results/pocket0.pdb",
    "artifacts/pocket0.pdb",
    "pocket0.pdb",
)
LEGACY_RESIDUE_POCKET_CANDIDATES = (
    "artifacts/lv_results/input/protein_pocket_residues.pdb",
    "artifacts/lv_results/protein_pocket_residues.pdb",
    "artifacts/protein_pocket_residues.pdb",
    "protein_pocket_residues.pdb",
)


def write_standard_result(
    *,
    request: dict[str, Any],
    raw_output_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Wrap legacy LVpocket pocket files as binding_pocket@1."""
    task = request.get("task") or {}
    task_id = str(task.get("id") or request.get("task_id") or "unknown-task")
    tool_slug = str(task.get("tool_slug") or "lvpocket-standard-pocket")

    pocket_dir = output_dir / "artifacts" / "pocket"
    report_dir = output_dir / "reports"
    pocket_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    prediction = _load_prediction(raw_output_dir)
    atom_pocket_source = _first_existing(raw_output_dir, _atom_pocket_candidates(prediction))
    residue_pocket_source = _first_existing(raw_output_dir, _residue_pocket_candidates(prediction))

    atom_pocket_path = pocket_dir / "atom_pocket.pdb"
    residue_pocket_path = pocket_dir / "residue_pocket.pdb"
    shutil.copyfile(atom_pocket_source, atom_pocket_path)
    shutil.copyfile(residue_pocket_source, residue_pocket_path)

    metadata = _build_metadata(prediction)
    metadata_path = pocket_dir / "pocket_metadata.json"
    write_json(metadata_path, metadata)

    report = {
        "tool": tool_slug,
        "adapter": "lvpocket_runtime",
        "status": "succeeded",
        "source_task_id": task_id,
        "model_choice": metadata.get("model_choice"),
        "distance_cutoff_angstrom": metadata.get("distance_cutoff_angstrom"),
        "residue_count": metadata.get("residue_count"),
        "atom_count": metadata.get("atom_count"),
    }
    report_path = report_dir / "report.json"
    write_json(report_path, report)

    result = {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "pocket": {
                "name": f"{task_id}_lvpocket_binding_pocket",
                "type": "binding_pocket@1",
                "files": {
                    "residue_pocket_pdb": file_ref(
                        output_dir=output_dir,
                        path=residue_pocket_path,
                        content_type="chemical/x-pdb",
                    ),
                    "atom_pocket_pdb": file_ref(
                        output_dir=output_dir,
                        path=atom_pocket_path,
                        content_type="chemical/x-pdb",
                    ),
                    "pocket_metadata_json": file_ref(
                        output_dir=output_dir,
                        path=metadata_path,
                        content_type="application/json",
                    ),
                },
                "metadata": metadata,
            },
            "report": {
                "name": f"{task_id}_lvpocket_adapter_report",
                "type": "run_report@1",
                "files": {
                    "report_json": file_ref(
                        output_dir=output_dir,
                        path=report_path,
                        content_type="application/json",
                    )
                },
                "metadata": {"source_task_id": task_id},
            },
        },
        "relations": [{"from": "report", "to": "pocket", "type": "describes"}],
    }
    write_json(output_dir / "result.json", result)
    return result


def _first_existing(base_dir: Path, candidates: tuple[str, ...]) -> Path:
    for candidate in candidates:
        path = base_dir / candidate
        if path.is_file():
            return path
    searched = ", ".join(candidates)
    raise FileNotFoundError(f"Missing LVpocket legacy output; searched: {searched}")


def _load_prediction(raw_output_dir: Path) -> dict[str, Any]:
    for candidate in (
        raw_output_dir / "prediction.json",
        raw_output_dir / "artifacts" / "prediction.json",
        raw_output_dir / "result.json",
    ):
        if not candidate.is_file():
            continue
        payload = read_json(candidate)
        if "outputs" in payload and isinstance(payload["outputs"], dict):
            return payload["outputs"]
        return payload
    return {}


def _atom_pocket_candidates(prediction: dict[str, Any]) -> tuple[str, ...]:
    candidates: list[str] = []
    pockets = prediction.get("pockets")
    if isinstance(pockets, list):
        for pocket in pockets:
            if isinstance(pocket, dict) and pocket.get("pdb"):
                candidates.append(str(pocket["pdb"]))
    candidates.extend(LEGACY_ATOM_POCKET_CANDIDATES)
    return tuple(dict.fromkeys(candidates))


def _residue_pocket_candidates(prediction: dict[str, Any]) -> tuple[str, ...]:
    candidates: list[str] = []
    residue_pocket = prediction.get("protein_pocket_residues")
    if isinstance(residue_pocket, dict):
        for key in ("path", "raw_path"):
            if residue_pocket.get(key):
                candidates.append(str(residue_pocket[key]))
    candidates.extend(LEGACY_RESIDUE_POCKET_CANDIDATES)
    return tuple(dict.fromkeys(candidates))


def _build_metadata(prediction: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "center": prediction.get("center"),
        "bbox": prediction.get("bbox"),
        "residue_ids": prediction.get("residue_ids", []),
        "atom_ids": prediction.get("atom_ids", []),
        "source_protein_ref": "input:protein",
    }
    optional_mapping = {
        "distance_cutoff": "distance_cutoff_angstrom",
        "residue_count": "residue_count",
        "atom_count": "atom_count",
        "model_choice": "model_choice",
        "device": "device",
    }
    for source_key, target_key in optional_mapping.items():
        if source_key in prediction:
            metadata[target_key] = prediction[source_key]
    residue_pocket = prediction.get("protein_pocket_residues")
    if isinstance(residue_pocket, dict):
        for source_key, target_key in optional_mapping.items():
            if target_key not in metadata and source_key in residue_pocket:
                metadata[target_key] = residue_pocket[source_key]
    return metadata
