"""Build standard platform results from Pocket2Mol legacy outputs."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from .io import file_ref, read_json, write_json


SDF_CANDIDATES = (
    "artifacts/generated_molecules.sdf",
    "artifacts/molecules.sdf",
    "artifacts/samples.sdf",
    "generated_molecules.sdf",
    "molecules.sdf",
)
TABLE_CANDIDATES = (
    "artifacts/molecules.csv",
    "artifacts/generated_smiles.csv",
    "artifacts/smiles.csv",
    "molecules.csv",
    "generated_smiles.csv",
    "smiles.csv",
)
MOLFILE_COUNTS_LINE = re.compile(r"^\s*\d{1,3}\s+\d{1,3}\s+.+\bV(?:2000|3000)\b")


def write_standard_result(
    *,
    request: dict[str, Any],
    raw_output_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Wrap legacy Pocket2Mol SDF/table outputs as result.v2."""
    task = request.get("task") or {}
    task_id = str(task.get("id") or request.get("task_id") or "unknown-task")
    tool_slug = str(task.get("tool_slug") or "pocket2mol-pocket-ligand-generation")

    molecules_dir = output_dir / "artifacts" / "molecules"
    ligands_dir = output_dir / "artifacts" / "ligands"
    report_dir = output_dir / "reports"
    molecules_dir.mkdir(parents=True, exist_ok=True)
    ligands_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    source_sdf = _first_sdf(raw_output_dir)
    ligand_paths = _split_sdf(source_sdf, ligands_dir)
    molecule_rows = _molecule_rows(raw_output_dir, ligand_count=len(ligand_paths))

    table_path = molecules_dir / "molecules.csv"
    _write_molecule_table(table_path, molecule_rows)
    metadata = {
        "molecule_id_field": "molecule_id",
        "source_task_id": task_id,
        "row_count": len(molecule_rows),
        "model_name": "Pocket2Mol",
        "source_input_ref": "input:pocket",
    }
    metadata_path = molecules_dir / "metadata.json"
    write_json(metadata_path, metadata)

    report = {
        "tool": tool_slug,
        "adapter": "pocket2mol_runtime",
        "status": "succeeded",
        "source_task_id": task_id,
        "generated_ligand_count": len(ligand_paths),
    }
    report_path = report_dir / "report.json"
    write_json(report_path, report)

    ligands = [
        {
            "name": ligand_path.stem,
            "type": "ligand_structure@1",
            "files": {
                "structure_file": file_ref(
                    output_dir=output_dir,
                    path=ligand_path,
                    content_type="chemical/x-mdl-sdfile",
                )
            },
            "metadata": {"ligand_id": ligand_path.stem},
        }
        for ligand_path in ligand_paths
    ]
    result = {
        "result_version": "aidd.sciminer/result.v2",
        "artifacts": {
            "molecules": {
                "name": f"{task_id}_pocket2mol_generated_molecules",
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(
                        output_dir=output_dir,
                        path=table_path,
                        content_type="text/csv",
                    ),
                    "metadata_json": file_ref(
                        output_dir=output_dir,
                        path=metadata_path,
                        content_type="application/json",
                    ),
                },
                "metadata": metadata,
            },
            "ligands": ligands,
            "report": {
                "name": f"{task_id}_pocket2mol_adapter_report",
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
        "relations": [
            *[
                {"from": "molecules", "to": f"ligands[{index}]", "type": "contains"}
                for index in range(len(ligands))
            ],
            {"from": "report", "to": "molecules", "type": "describes"},
        ],
    }
    write_json(output_dir / "result.json", result)
    return result


def _first_sdf(raw_output_dir: Path) -> Path:
    for candidate in SDF_CANDIDATES:
        path = raw_output_dir / candidate
        if path.is_file():
            return path
    for path in sorted((raw_output_dir / "artifacts").glob("**/*.sdf")):
        if path.is_file():
            return path
    result_json = raw_output_dir / "result.json"
    if result_json.is_file():
        payload = read_json(result_json)
        outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
        for value in outputs.values():
            if isinstance(value, str) and value.endswith(".sdf") and (raw_output_dir / value).is_file():
                return raw_output_dir / value
    raise FileNotFoundError("Missing Pocket2Mol SDF output")


def _split_sdf(source_sdf: Path, ligands_dir: Path) -> list[Path]:
    text = source_sdf.read_text(encoding="utf-8", errors="replace")
    blocks = [block.strip() for block in text.split("$$$$") if block.strip()]
    if not blocks:
        raise ValueError(f"SDF contains no molecule records: {source_sdf}")
    paths: list[Path] = []
    for index, block in enumerate(blocks, start=1):
        path = ligands_dir / f"ligand_{index:03d}.sdf"
        path.write_text(_normalize_sdf_block(block) + "\n$$$$\n", encoding="utf-8")
        paths.append(path)
    return paths


def _normalize_sdf_block(block: str) -> str:
    """Ensure the molfile counts line follows the three-line header."""
    normalized = block.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    counts_index = next(
        (index for index, line in enumerate(lines) if MOLFILE_COUNTS_LINE.match(line)),
        None,
    )
    if counts_index is not None and counts_index < 3:
        lines[counts_index:counts_index] = [""] * (3 - counts_index)
    return "\n".join(lines).strip()


def _molecule_rows(raw_output_dir: Path, *, ligand_count: int) -> list[dict[str, str]]:
    table = next((raw_output_dir / candidate for candidate in TABLE_CANDIDATES if (raw_output_dir / candidate).is_file()), None)
    if table is None:
        return [
            {"molecule_id": f"ligand_{index:03d}", "smiles": "", "rank": str(index)}
            for index in range(1, ligand_count + 1)
        ]
    with table.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    normalized: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        molecule_id = row.get("molecule_id") or row.get("ligand_id") or f"ligand_{index:03d}"
        normalized.append(
            {
                "molecule_id": molecule_id,
                "smiles": row.get("smiles") or row.get("SMILES") or "",
                "rank": row.get("rank") or str(index),
            }
        )
    return normalized or [
        {"molecule_id": f"ligand_{index:03d}", "smiles": "", "rank": str(index)}
        for index in range(1, ligand_count + 1)
    ]


def _write_molecule_table(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["molecule_id", "smiles", "rank"])
        writer.writeheader()
        writer.writerows(rows)
