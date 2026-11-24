#!/usr/bin/env python3
"""Convert a legacy model result.json into the platform standard result.v2.

The model containers in this directory wrap upstream research scripts that emit a
legacy ``result.json`` (``success``/``outputs``/``artifacts``).  The platform
Kubernetes adaptor accepts ``aidd.platform/result`` (and legacy ``aidd.platform/result``), so after the
model entry finishes we translate the legacy payload into standard artifacts with
the file roles required by each artifact type.

Usage:
    python postprocess_result.py --model molp-pc --output-dir OUT --task-id ID
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any


RESULT_VERSION = "aidd.platform/result"
LEGACY_RESULT_VERSION = "aidd.platform/result"
ACCEPTED_RESULT_VERSIONS = {RESULT_VERSION, LEGACY_RESULT_VERSION}

# 与前端 `druglikeness.ts` 及内置 `builtin-rdkit-properties` 保持同一列名，
# Pocket2Mol 生成表落库后即可直接进类药性面板。
DESCRIPTOR_COLUMNS = [
    "molecular_weight",
    "logp",
    "hbd",
    "hba",
    "tpsa",
    "rotatable_bonds",
    "qed",
    "lipinski_violations",
    "scaffold",
]

_SMILES_HEADER_TOKENS = frozenset(
    {"smiles", "smile", "smi", "canonical_smiles", "isomeric_smiles"}
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_ref(output_dir: Path, relative: str) -> dict[str, str]:
    path = output_dir / relative
    if not path.is_file():
        raise SystemExit(f"declared output file is missing: {relative}")
    return {"path": relative, "sha256": sha256_file(path)}


def molecule_table_metadata(output_dir: Path, task_id: str, field: str) -> str:
    relative = "artifacts/metadata.json"
    write_json(
        output_dir / relative,
        {
            "molecule_id_field": field,
            "source_task_id": task_id,
            "generated_by": "platform_postprocess",
        },
    )
    return relative


def run_report(output_dir: Path, task_id: str, tool: str, summary: dict[str, Any]) -> str:
    relative = "artifacts/report.json"
    write_json(
        output_dir / relative,
        {"source_task_id": task_id, "tool": tool, "status": "succeeded", **summary},
    )
    return relative


def load_legacy(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "result.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("result_version") in ACCEPTED_RESULT_VERSIONS:
        raise SystemExit("result.json already uses result.v2")
    if not payload.get("success"):
        raise SystemExit("legacy result reports failure; no v2 payload to build")
    return payload


def flatten_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in prediction.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            row[key] = value
        elif isinstance(value, dict):
            for inner_key, inner_value in value.items():
                if isinstance(inner_value, (str, int, float, bool)) or inner_value is None:
                    row[f"{key}.{inner_key}"] = inner_value
    return row


def molp_pc(output_dir: Path, task_id: str, legacy: dict[str, Any]) -> dict[str, Any]:
    table = "artifacts/cb_data_result.csv"
    metadata = molecule_table_metadata(output_dir, task_id, "SMILES")
    report = run_report(output_dir, task_id, "molp-pc-property-prediction", legacy.get("outputs") or {})
    return {
        "result_version": RESULT_VERSION,
        "artifacts": {
            "properties": {
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(output_dir, table),
                    "metadata_json": file_ref(output_dir, metadata),
                },
                "metadata": {"molecule_id_field": "SMILES", "source_task_id": task_id},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, report)},
                "metadata": {"source_task_id": task_id},
            },
        },
        "metrics": legacy.get("metrics") or {},
    }


def msign(output_dir: Path, task_id: str, legacy: dict[str, Any]) -> dict[str, Any]:
    outputs = legacy.get("outputs") or {}
    rows: list[dict[str, Any]] = []
    predictions = outputs.get("predictions")
    if isinstance(predictions, list):
        for index, item in enumerate(predictions):
            row = flatten_prediction(item if isinstance(item, dict) else {})
            row.setdefault("molecule_id", str(item.get("complex_id") if isinstance(item, dict) else index))
            rows.append(row)
    else:
        prediction = outputs.get("prediction") if isinstance(outputs.get("prediction"), dict) else {}
        row = flatten_prediction(prediction)
        row.setdefault("molecule_id", str(outputs.get("complex_id") or "complex_1"))
        rows.append(row)
    conversion_path = output_dir / "artifacts/smiles_conversion_errors.json"
    conversion_summary: dict[str, Any] = {}
    if conversion_path.is_file():
        try:
            conversion_summary = json.loads(conversion_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            conversion_summary = {}
        for item in conversion_summary.get("errors") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "molecule_id": str(item.get("molecule_id") or ""),
                    "smiles": item.get("smiles"),
                    "error": item.get("error") or "SMILES to 3D conversion failed",
                }
            )
    if not rows:
        raise SystemExit("MSIGN legacy result has no prediction rows")

    table = "artifacts/affinity.csv"
    fieldnames = sorted({key for row in rows for key in row})
    with (output_dir / table).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    metadata = molecule_table_metadata(output_dir, task_id, "molecule_id")
    report_summary = dict(outputs)
    if conversion_summary:
        report_summary["smiles_conversion"] = {
            "requested_count": conversion_summary.get("requested_count"),
            "written_count": conversion_summary.get("written_count"),
            "failed_count": conversion_summary.get("failed_count"),
        }
    report = run_report(output_dir, task_id, "msign-affinity-prediction", report_summary)
    return {
        "result_version": RESULT_VERSION,
        "artifacts": {
            "affinity": {
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(output_dir, table),
                    "metadata_json": file_ref(output_dir, metadata),
                },
                "metadata": {"molecule_id_field": "molecule_id", "source_task_id": task_id},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, report)},
                "metadata": {"source_task_id": task_id},
            },
        },
        "metrics": legacy.get("metrics") or {},
    }


def _format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{round(float(value), 3)}"


def _molecule_descriptors(smiles: str) -> tuple[dict[str, str], bool, int]:
    """Return (formatted descriptor cells, is_valid, lipinski_violations).

    RDKit 只在函数内导入：molp-pc / msign / therapainter 的镜像即使没有 RDKit
    也能正常走后处理，不受这里影响。
    """
    blank = {column: "" for column in DESCRIPTOR_COLUMNS}
    text = (smiles or "").strip()
    if not text:
        return blank, False, 0
    try:
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, QED, rdMolDescriptors
        from rdkit.Chem.Scaffolds import MurckoScaffold
    except ImportError as exc:  # pragma: no cover - 运行时镜像自带 RDKit
        raise SystemExit(f"Pocket2Mol post-processing requires RDKit: {exc}") from exc

    molecule = Chem.MolFromSmiles(text)
    if molecule is None:
        return blank, False, 0

    molecular_weight = float(Descriptors.MolWt(molecule))
    logp = float(Crippen.MolLogP(molecule))
    hbd = int(rdMolDescriptors.CalcNumHBD(molecule))
    hba = int(rdMolDescriptors.CalcNumHBA(molecule))
    try:
        qed: float | str = round(float(QED.qed(molecule)), 3)
    except Exception:  # noqa: BLE001 - 个别分子 QED 计算失败时留空即可
        qed = ""
    violations = int(
        sum(
            (
                molecular_weight > 500,
                logp > 5,
                hbd > 5,
                hba > 10,
            )
        )
    )
    cells = {
        "molecular_weight": _format_float(molecular_weight),
        "logp": _format_float(logp),
        "hbd": str(hbd),
        "hba": str(hba),
        "tpsa": _format_float(rdMolDescriptors.CalcTPSA(molecule)),
        "rotatable_bonds": str(int(rdMolDescriptors.CalcNumRotatableBonds(molecule))),
        "qed": "" if isinstance(qed, str) else _format_float(qed),
        "lipinski_violations": str(violations),
        "scaffold": MurckoScaffold.MurckoScaffoldSmiles(mol=molecule),
    }
    return cells, True, violations


def _read_csv_table(text: str) -> tuple[list[dict[str, Any]], list[str], str]:
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        return [], [], "smiles"
    smiles_key = next(
        (field for field in fieldnames if field.strip().lower() == "smiles"), None
    )
    if smiles_key is None:
        smiles_key = next(
            (field for field in fieldnames if "smiles" in field.strip().lower()), None
        )
    if smiles_key is None:
        raise SystemExit("Pocket2Mol molecule table must contain a SMILES column")
    rows = [
        {
            key: (value if value is not None else "")
            for key, value in row.items()
            if key is not None
        }
        for row in reader
    ]
    return rows, fieldnames, smiles_key


def _read_smiles_text_table(text: str) -> tuple[list[dict[str, Any]], list[str], str]:
    """Parse headerless ``SMILES.txt`` (one SMILES per line, optional extra columns)."""
    data_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not data_lines:
        return [], [], "smiles"

    fieldnames: list[str] | None = None
    if data_lines[0].split()[0].lower() in _SMILES_HEADER_TOKENS:
        fieldnames = [token.strip() for token in data_lines[0].split()]
        fieldnames[0] = "smiles"
        data_lines = data_lines[1:]

    token_rows = [line.split() for line in data_lines]
    max_columns = max((len(tokens) for tokens in token_rows), default=1)
    if fieldnames is None:
        fieldnames = ["smiles"]
        if max_columns >= 2:
            fieldnames.append("score")
        fieldnames.extend(f"column_{index}" for index in range(3, max_columns + 1))
    else:
        fieldnames.extend(
            f"column_{index}" for index in range(len(fieldnames) + 1, max_columns + 1)
        )

    rows = [
        dict(zip(fieldnames, tokens + [""] * (len(fieldnames) - len(tokens))))
        for tokens in token_rows
    ]
    return rows, fieldnames, fieldnames[0]


def _read_molecule_table(path: Path) -> tuple[list[dict[str, Any]], list[str], str]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first:
        return [], [], "smiles"
    if "," in first:
        return _read_csv_table(text)
    return _read_smiles_text_table(text)


def _enrich_molecule_rows(
    rows: list[dict[str, Any]], fieldnames: list[str], smiles_key: str
) -> tuple[list[dict[str, Any]], list[str], dict[str, int]]:
    preserved = [
        field
        for field in fieldnames
        if field != smiles_key and field not in DESCRIPTOR_COLUMNS
    ]
    output_fieldnames = ["smiles", *preserved, *DESCRIPTOR_COLUMNS]

    enriched: list[dict[str, Any]] = []
    valid_count = 0
    lipinski_pass_count = 0
    scaffolds: set[str] = set()
    for row in rows:
        smiles = str(row.get(smiles_key) or "").strip()
        cells, valid, violations = _molecule_descriptors(smiles)
        output_row: dict[str, Any] = {"smiles": smiles}
        for field in preserved:
            output_row[field] = row.get(field, "")
        output_row.update(cells)
        enriched.append(output_row)
        if valid:
            valid_count += 1
            if violations == 0:
                lipinski_pass_count += 1
            scaffold = cells.get("scaffold") or ""
            if scaffold:
                scaffolds.add(scaffold)

    summary = {
        "molecule_count": len(enriched),
        "valid_molecule_count": valid_count,
        "lipinski_pass_count": lipinski_pass_count,
        "unique_scaffold_count": len(scaffolds),
    }
    return enriched, output_fieldnames, summary


def pocket2mol(output_dir: Path, task_id: str, legacy: dict[str, Any]) -> dict[str, Any]:
    outputs = legacy.get("outputs") or {}
    source = str(outputs.get("smiles_file") or "artifacts/SMILES.txt")
    source_path = output_dir / source
    if not source_path.is_file():
        raise SystemExit(f"declared output file is missing: {source}")

    rows, fieldnames, smiles_key = _read_molecule_table(source_path)
    if not rows:
        raise SystemExit(f"Pocket2Mol molecule table is empty: {source}")
    enriched, output_fieldnames, summary = _enrich_molecule_rows(
        rows, fieldnames, smiles_key
    )
    if summary["valid_molecule_count"] == 0:
        raise SystemExit(f"Pocket2Mol molecule table has no valid SMILES: {source}")

    # 原始 SMILES.txt 保留在盘上不动；富化结果另写 CSV 供下游与前端直接读取。
    table = "artifacts/generated_molecules.csv"
    with (output_dir / table).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=output_fieldnames, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(enriched)

    sdf = str(outputs.get("combined_sdf") or "artifacts/generated_molecules.sdf")
    metadata = molecule_table_metadata(output_dir, task_id, "smiles")
    report_summary = dict(outputs)
    report_summary.update(summary)
    report = run_report(
        output_dir, task_id, "pocket2mol-pocket-ligand-generation", report_summary
    )
    return {
        "result_version": RESULT_VERSION,
        "artifacts": {
            "molecules": {
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(output_dir, table),
                    "metadata_json": file_ref(output_dir, metadata),
                },
                "metadata": {"molecule_id_field": "smiles", "source_task_id": task_id},
            },
            "ligands": {
                "type": "ligand_structure@1",
                "files": {"structure_file": file_ref(output_dir, sdf)},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, report)},
                "metadata": {"source_task_id": task_id},
            },
        },
        "metrics": legacy.get("metrics") or {},
    }


def therapainter(output_dir: Path, task_id: str, legacy: dict[str, Any]) -> dict[str, Any]:
    """DualPep peptide activity/toxicity prediction -> molecule_table@1."""
    outputs = legacy.get("outputs") or {}
    table = "artifacts/predictions.csv"
    if not (output_dir / table).is_file():
        raise SystemExit("TheraPainter legacy result has no predictions.csv")
    metadata = molecule_table_metadata(output_dir, task_id, "seq")
    report = run_report(
        output_dir,
        task_id,
        "therapainter-peptide-prediction",
        {
            "sequence_count": outputs.get("sequence_count"),
            "prediction_mode": outputs.get("prediction_mode"),
            "top_prediction": outputs.get("top_prediction"),
        },
    )
    return {
        "result_version": RESULT_VERSION,
        "artifacts": {
            "peptides": {
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(output_dir, table),
                    "metadata_json": file_ref(output_dir, metadata),
                },
                "metadata": {"molecule_id_field": "seq", "source_task_id": task_id},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, report)},
                "metadata": {"source_task_id": task_id},
            },
        },
        "metrics": legacy.get("metrics") or {},
    }


BUILDERS = {
    "molp-pc": molp_pc,
    "msign": msign,
    "pocket2mol": pocket2mol,
    "therapainter": therapainter,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=sorted(BUILDERS))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--task-id", default="unknown")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    legacy = load_legacy(output_dir)
    (output_dir / "result.legacy.json").write_text(
        json.dumps(legacy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    payload = BUILDERS[args.model](output_dir, args.task_id, legacy)
    (output_dir / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
