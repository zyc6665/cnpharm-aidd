#!/usr/bin/env python3
"""Boltz-2 protein structure prediction entry for the SCIMINER Kubernetes runtime.

输入：参数 ``sequence``（单字母氨基酸序列，可带 FASTA 头）；可选 ``name``、
``sampling_steps``、``recycling_steps``、``diffusion_samples``、``seed``。
输出：``protein_structure@1``（Boltz 预测结构 PDB + metadata）与 ``run_report@1``。

权重不烘进镜像：由平台把宿主机缓存目录以只读方式挂到 ``BOLTZ_CACHE``
（默认 ``/opt/boltz2_cache``）。离线运行，不使用 MSA 服务器；单序列 A3M 由本脚本
本地生成，保证无外网也能推理。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

AA = set("ACDEFGHIKLMNPQRSTVWYBXZJUO")


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


def parse_pdb_stats(pdb: Path) -> dict[str, Any]:
    chains: list[str] = []
    residues: set[tuple[str, str, str]] = set()
    atoms = 0
    for line in pdb.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(("ATOM  ", "HETATM")):
            atoms += 1
            chain = line[21:22].strip() or "A"
            if chain not in chains:
                chains.append(chain)
            residues.add((chain, line[22:26].strip(), line[26:27].strip()))
    return {
        "chain_ids": chains or ["A"],
        "residue_count": len(residues),
        "atom_count": atoms,
    }


def find_first(root: Path, pattern: str) -> Path | None:
    matches = sorted(root.rglob(pattern))
    return matches[0] if matches else None


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
    run_params = params.get("params") or params.get("parameters") or {}
    # 平台 TaskInput.params 本身带一层 ``params`` 包装，legacy 桥接又会把它放到
    # ``params`` 下，因此这里逐层剥到真正含 ``sequence`` 的那一层。
    while isinstance(run_params, dict) and "sequence" not in run_params:
        nested = run_params.get("params")
        if not isinstance(nested, dict) or nested is run_params:
            break
        run_params = nested
    raw_sequence = run_params.get("sequence")
    if not raw_sequence:
        raise SystemExit("parameter 'sequence' is required")
    sequence = clean_sequence(str(raw_sequence))
    name = str(run_params.get("name") or "protein").strip().replace(" ", "_") or "protein"
    seed = int(run_params.get("seed") or 0)
    sampling_steps = int(run_params.get("sampling_steps") or 200)
    recycling_steps = int(run_params.get("recycling_steps") or 3)
    diffusion_samples = int(run_params.get("diffusion_samples") or 1)
    cache_dir = Path(os.environ.get("BOLTZ_CACHE", "/opt/boltz2_cache"))

    msa_path = work / f"{name}.a3m"
    msa_path.write_text(f">query\n{sequence}\n", encoding="utf-8")
    yaml_path = work / "boltz_input.yaml"
    yaml_path.write_text(
        "version: 1\n"
        "sequences:\n"
        "  - protein:\n"
        f"      id: A\n"
        f"      sequence: {sequence}\n"
        f"      msa: {msa_path}\n",
        encoding="utf-8",
    )

    boltz_bin = shutil.which("boltz") or "/opt/conda/bin/boltz"
    out_root = work / "boltz_out"
    cmd = [
        boltz_bin, "predict", str(yaml_path),
        "--out_dir", str(out_root),
        "--cache", str(cache_dir),
        "--accelerator", "gpu" if str(args.device).lower() in ("auto", "cuda", "gpu") else "cpu",
        "--devices", "1",
        "--output_format", "pdb",
        "--sampling_steps", str(sampling_steps),
        "--recycling_steps", str(recycling_steps),
        "--diffusion_samples", str(diffusion_samples),
        "--seed", str(seed),
        "--num_workers", "0",
        "--no_kernels",
    ]
    print("[boltz] " + " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, text=True, capture_output=True)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        raise SystemExit(f"boltz predict failed with exit code {completed.returncode}")

    pdb_candidates = [p for p in out_root.rglob("*.pdb") if p.is_file()]
    if not pdb_candidates:
        raise SystemExit("boltz produced no PDB structure")
    # 取模型 0 的主结构，优先文件名带 model_0 的
    pdb_candidates.sort(key=lambda p: (0 if "model_0" in p.name else 1, len(str(p))))
    structure = pdb_candidates[0]
    target_pdb = output_dir / "artifacts" / "structure.pdb"
    shutil.copyfile(structure, target_pdb)

    confidence: dict[str, Any] = {}
    conf_candidates = [p for p in out_root.rglob("confidence*.json") if p.is_file()]
    if conf_candidates:
        conf_candidates.sort(key=lambda p: (0 if "model_0" in p.name else 1, len(str(p))))
        try:
            confidence = json.loads(conf_candidates[0].read_text(encoding="utf-8"))
        except Exception:
            confidence = {}

    stats = parse_pdb_stats(target_pdb)
    metadata = {
        **stats,
        "structure_format": "pdb",
        "source_filename": target_pdb.name,
        "source_database": "tool_output",
        "source_id": args.task_id,
        "preparation_status": "raw",
    }
    metadata_path = output_dir / "artifacts" / "metadata.json"
    write_json(metadata_path, metadata)

    metrics = {
        "sequence_length": len(sequence),
        "confidence_score": confidence.get("confidence_score"),
        "ptm": confidence.get("ptm"),
        "iptm": confidence.get("iptm"),
        "complex_plddt": confidence.get("complex_plddt"),
        "sampling_steps": sampling_steps,
        "recycling_steps": recycling_steps,
        "diffusion_samples": diffusion_samples,
    }
    report_path = output_dir / "artifacts" / "report.json"
    write_json(
        report_path,
        {
            "source_task_id": args.task_id,
            "tool": "boltz-2",
            "status": "succeeded",
            "name": name,
            "sequence_length": len(sequence),
            "confidence": {k: v for k, v in confidence.items() if isinstance(v, (int, float, str))},
        },
    )

    result = {
        "result_version": "aidd.sciminer/result",
        "artifacts": {
            "predicted_structure": {
                "type": "protein_structure@1",
                "files": {
                    "structure_file": file_ref(output_dir, "artifacts/structure.pdb"),
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
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
