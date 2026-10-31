#!/usr/bin/env python3
"""Boltz-2 protein-ligand binding affinity entry for the SCIMINER Kubernetes runtime.

输入：
  * 参数 ``sequence``：受体蛋白单字母氨基酸序列（可带 FASTA 头）。
  * 输入文件 ``ligand_smiles``：``molecule_table@1`` CSV，需含 ``smiles`` 列，
    可选 ``molecule_id`` / ``id`` / ``name`` 列；每行一个配体。

输出：
  * ``molecule_table@1``：``affinity_results.csv``，逐配体给出
    ``affinity_pred_value``（Boltz-2 的 log(IC50) 值，越小亲和力越强）、
    ``affinity_probability_binary``（结合概率）、``confidence_score``、``iptm``。
  * ``run_report@1``：运行汇总。

Boltz-2 当前只支持「单次运行一个 affinity ligand」，因此本脚本对 CSV 中每个配体
分别构造 YAML 并顺序推理；单个配体失败会记录 ``status=error`` 行而不中断整批。
权重不烘进镜像，由平台把宿主机缓存以只读方式挂到 ``BOLTZ_CACHE``。
离线运行：蛋白单序列 A3M 由本脚本本地生成。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

AA = set("ACDEFGHIKLMNPQRSTVWYBXZJUO")
SMILES_KEYS = ("smiles", "canonical_smiles", "smile")
ID_KEYS = ("molecule_id", "id", "name", "compound_id")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_ref(output_dir: Path, relative: str) -> dict[str, str]:
    path = output_dir / relative
    if not path.is_file():
        raise SystemExit(f"declared output file is missing: {relative}")
    return {"path": relative, "sha256": sha256_file(path)}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_input(input_dir: Path, value: str) -> Path:
    for candidate in (Path(value), input_dir / value, input_dir / Path(value).name, input_dir.parent / value):
        if candidate.is_file():
            return candidate
    raise SystemExit(f"input file not found: {value}")


def pick_csv(files: dict[str, str], input_dir: Path) -> Path:
    for key, value in files.items():
        if "ligand" in key.lower() or "smiles" in key.lower():
            try:
                candidate = resolve_input(input_dir, value)
            except SystemExit:
                continue
            if candidate.suffix.lower() == ".csv":
                return candidate
    for path in sorted(input_dir.rglob("*.csv")):
        if path.is_file():
            return path
    raise SystemExit("cannot find ligand_smiles CSV input")


def clean_sequence(raw: str) -> str:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if lines and lines[0].startswith(">"):
        lines = lines[1:]
    sequence = "".join(lines).upper().replace(" ", "").replace("-", "")
    invalid = sorted(set(sequence) - AA)
    if invalid:
        raise SystemExit(f"sequence contains invalid residues: {''.join(invalid)}")
    if not (4 <= len(sequence) <= 2000):
        raise SystemExit("sequence length must be between 4 and 2000 residues")
    return sequence


def read_ligands(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("ligand_smiles CSV is empty")
    fields = {name.strip().lower(): name for name in rows[0].keys() if name}
    smiles_key = next((fields[key] for key in SMILES_KEYS if key in fields), None)
    if smiles_key is None:
        # 无表头单列 CSV：csv.DictReader 会给出 None 键
        raise SystemExit("ligand_smiles CSV must contain a 'smiles' column")
    id_key = next((fields[key] for key in ID_KEYS if key in fields), None)
    ligands: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        smiles = (row.get(smiles_key) or "").strip()
        if not smiles:
            continue
        molecule_id = (row.get(id_key) or f"ligand_{index}").strip() if id_key else f"ligand_{index}"
        ligands.append({"molecule_id": molecule_id, "smiles": smiles})
    if not ligands:
        raise SystemExit("no non-empty SMILES rows in ligand_smiles CSV")
    return ligands


def find_first(root: Path, pattern: str) -> Path | None:
    matches = sorted(root.rglob(pattern))
    return matches[0] if matches else None


def run_one(
    boltz_bin: str,
    cache_dir: Path,
    work: Path,
    sequence: str,
    ligand: dict[str, str],
    index: int,
    seed: int,
    sampling_steps: int,
    recycling_steps: int,
    diffusion_samples: int,
    sampling_steps_affinity: int,
) -> dict[str, Any]:
    tag = f"lig{index}"
    msa_path = work / "protein.a3m"
    yaml_path = work / f"{tag}.yaml"
    yaml_path.write_text(
        "version: 1\n"
        "sequences:\n"
        "  - protein:\n"
        "      id: A\n"
        f"      sequence: {sequence}\n"
        f"      msa: {msa_path}\n"
        "  - ligand:\n"
        "      id: B\n"
        f"      smiles: {ligand['smiles']}\n"
        "properties:\n"
        "  - affinity:\n"
        "      binder: B\n",
        encoding="utf-8",
    )
    out_root = work / f"boltz_{tag}"
    cmd = [
        boltz_bin,
        "predict",
        str(yaml_path),
        "--out_dir",
        str(out_root),
        "--cache",
        str(cache_dir),
        "--accelerator",
        "gpu",
        "--devices",
        "1",
        "--output_format",
        "pdb",
        "--sampling_steps",
        str(sampling_steps),
        "--recycling_steps",
        str(recycling_steps),
        "--diffusion_samples",
        str(diffusion_samples),
        "--sampling_steps_affinity",
        str(sampling_steps_affinity),
        "--seed",
        str(seed + index),
        "--num_workers",
        "0",
        "--no_kernels",
    ]
    print(f"[boltz-affinity] {ligand['molecule_id']}: " + " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, text=True, capture_output=True)
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-5:]
        return {
            "molecule_id": ligand["molecule_id"],
            "smiles": ligand["smiles"],
            "status": "error",
            "error": " | ".join(tail) or f"exit code {completed.returncode}",
        }

    affinity_path = find_first(out_root, "affinity*.json")
    if affinity_path is None:
        return {
            "molecule_id": ligand["molecule_id"],
            "smiles": ligand["smiles"],
            "status": "error",
            "error": "boltz produced no affinity json",
        }
    try:
        affinity = json.loads(affinity_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "molecule_id": ligand["molecule_id"],
            "smiles": ligand["smiles"],
            "status": "error",
            "error": f"invalid affinity json: {exc}",
        }

    confidence: dict[str, Any] = {}
    conf_path = find_first(out_root, "confidence*.json")
    if conf_path is not None:
        try:
            confidence = json.loads(conf_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            confidence = {}

    return {
        "molecule_id": ligand["molecule_id"],
        "smiles": ligand["smiles"],
        "status": "ok",
        "error": "",
        "affinity_pred_value": affinity.get("affinity_pred_value"),
        "affinity_probability_binary": affinity.get("affinity_probability_binary"),
        "confidence_score": confidence.get("confidence_score"),
        "iptm": confidence.get("iptm"),
        "ligand_iptm": confidence.get("ligand_iptm"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default="unknown")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--params-json", required=True)
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    work = Path(args.work_dir or (output_dir / "work")).resolve()
    work.mkdir(parents=True, exist_ok=True)
    (output_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    params = json.loads(Path(args.params_json).read_text(encoding="utf-8"))
    files = params.get("input_files") or {}
    run_params = params.get("params") or params.get("parameters") or {}
    while isinstance(run_params, dict) and "sequence" not in run_params:
        nested = run_params.get("params")
        if not isinstance(nested, dict) or nested is run_params:
            break
        run_params = nested

    raw_sequence = run_params.get("sequence")
    if not raw_sequence:
        raise SystemExit("parameter 'sequence' is required")
    sequence = clean_sequence(str(raw_sequence))
    name = str(run_params.get("name") or "complex").strip().replace(" ", "_") or "complex"
    seed = int(run_params.get("seed") or 0)
    sampling_steps = int(run_params.get("sampling_steps") or 100)
    recycling_steps = int(run_params.get("recycling_steps") or 2)
    diffusion_samples = int(run_params.get("diffusion_samples") or 1)
    sampling_steps_affinity = int(run_params.get("sampling_steps_affinity") or 50)
    cache_dir = Path(os.environ.get("BOLTZ_CACHE", "/opt/boltz2_cache"))

    msa_path = work / "protein.a3m"
    msa_path.write_text(f">query\n{sequence}\n", encoding="utf-8")

    ligand_csv = pick_csv(files, input_dir)
    ligands = read_ligands(ligand_csv)

    boltz_bin = shutil.which("boltz") or "/opt/conda/bin/boltz"
    rows: list[dict[str, Any]] = []
    for index, ligand in enumerate(ligands, start=1):
        rows.append(
            run_one(
                boltz_bin,
                cache_dir,
                work,
                sequence,
                ligand,
                index,
                seed,
                sampling_steps,
                recycling_steps,
                diffusion_samples,
                sampling_steps_affinity,
            )
        )

    columns = [
        "molecule_id",
        "smiles",
        "status",
        "error",
        "affinity_pred_value",
        "affinity_probability_binary",
        "confidence_score",
        "iptm",
        "ligand_iptm",
    ]
    table_path = output_dir / "artifacts" / "affinity_results.csv"
    with table_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in columns})

    metadata_path = output_dir / "artifacts" / "metadata.json"
    write_json(
        metadata_path,
        {
            "table_format": "csv",
            "columns": columns,
            "row_count": len(rows),
            "smiles_column": "smiles",
            "molecule_id_column": "molecule_id",
            "source_task_id": args.task_id,
            "source_database": "tool_output",
        },
    )

    ok_rows = [row for row in rows if row.get("status") == "ok"]
    metric_values = [
        float(row["affinity_pred_value"])
        for row in ok_rows
        if isinstance(row.get("affinity_pred_value"), (int, float))
    ]
    metrics = {
        "ligand_count": len(rows),
        "success_count": len(ok_rows),
        "failed_count": len(rows) - len(ok_rows),
        "best_affinity_pred_value": min(metric_values) if metric_values else None,
        "sequence_length": len(sequence),
    }
    report_path = output_dir / "artifacts" / "report.json"
    write_json(
        report_path,
        {
            "source_task_id": args.task_id,
            "tool": "boltz-2-affinity",
            "status": "succeeded" if ok_rows else "failed",
            "name": name,
            **metrics,
            "rows": rows,
        },
    )

    result = {
        "result_version": "aidd.sciminer/result",
        "artifacts": {
            "affinity_table": {
                "type": "molecule_table@1",
                "files": {
                    "table_file": file_ref(output_dir, "artifacts/affinity_results.csv"),
                    "metadata_json": file_ref(output_dir, "artifacts/metadata.json"),
                },
                "metadata": {"source_task_id": args.task_id, "source_database": "tool_output"},
            },
            "report": {
                "type": "run_report@1",
                "files": {"report_json": file_ref(output_dir, "artifacts/report.json")},
                "metadata": {"source_task_id": args.task_id},
            },
        },
        "metrics": metrics,
    }
    write_json(output_dir / "result.json", result)
    if not ok_rows:
        raise SystemExit("all ligand affinity predictions failed")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
