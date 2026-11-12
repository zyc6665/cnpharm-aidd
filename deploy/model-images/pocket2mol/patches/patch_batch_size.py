#!/usr/bin/env python3
"""给 Pocket2Mol 平台适配层加 `batch_size`（并行采样批数）与分批合并。

上游 Pocket2Mol 的采样是**逐分子串行**的：`sample_for_pdb.py` 用
`while len(pool.finished) < config.sample.num_samples` 驱动，每一步对 beam 队列里
的每个分子单独做一次 batch-of-1 前向。因此「一批多少个」在上游并不是一个配置项
——它在采样阶段根本不存在，只存在于训练配置（configs/train.yml）。

平台上能真正影响吞吐的是**并行跑几路采样**：每路是一个独立进程，各分到
`ceil(num_samples / batch_size)` 个分子、种子依次偏移，最后合并结果。
本补丁实现的就是这件事，并把它作为参数 `batch_size` 暴露出去。

用法（在模型目录下执行）：

    python3 patch_batch_size.py /opt/sciminer/Pocket2Mol-main

补丁是幂等的：已经打过会直接说明并退出 0。
"""

from __future__ import annotations

import sys
from pathlib import Path

PLATFORM_PY = "pocket2mol_platform.py"
RUN_SH = "platform_run.sh"

OLD_WRITE_SIGNATURE = '''def write_sample_config(path: Path, *, checkpoint: Path, params: dict[str, Any]) -> None:'''

NEW_WRITE_SIGNATURE = '''def write_sample_config(
    path: Path,
    *,
    checkpoint: Path,
    params: dict[str, Any],
    num_samples: int | None = None,
    seed: int | None = None,
) -> None:'''

OLD_SEED_LINES = '''    seed = int_param(params, "seed", 2020, 0)
    num_samples = int_param(params, "num_samples", 100, 1, 10000)'''

NEW_SEED_LINES = '''    # 分批采样时每个进程分到的分子数与种子由调用方给定（batch_size > 1 时）。
    if seed is None:
        seed = int_param(params, "seed", 2020, 0)
    if num_samples is None:
        num_samples = int_param(params, "num_samples", 100, 1, 10000)'''

OLD_WRITE_CALL = '''    metadata_json = work_dir / "pocket2mol_platform_metadata.json"
    write_sample_config(config_out, checkpoint=checkpoint, params=params)'''

NEW_WRITE_CALL = '''    metadata_json = work_dir / "pocket2mol_platform_metadata.json"

    # 并行采样批数：batch_size 路进程各分一批分子。上游采样逐分子串行，
    # 单进程再快也只能用满一个核的调度队列；多进程能真正把 GPU 填满。
    batch_size = int_param(params, "batch_size", 1, 1, 8)
    total_samples = int_param(params, "num_samples", 100, 1, 10000)
    base_seed = int_param(params, "seed", 2020, 0)
    batch_count = max(1, min(batch_size, total_samples))
    batch_configs: list[str] = []
    batch_outdirs: list[str] = []
    samples_per_batch: list[int] = []
    for index in range(batch_count):
        # 前 remainder 批多分一个，保证总数恰好等于 num_samples。
        assigned = total_samples // batch_count + (1 if index < total_samples % batch_count else 0)
        config_path = (
            config_out
            if index == 0
            else config_out.with_name(f"{config_out.stem}.batch{index}{config_out.suffix}")
        )
        write_sample_config(
            config_path,
            checkpoint=checkpoint,
            params=params,
            num_samples=assigned,
            seed=base_seed + index,
        )
        batch_configs.append(str(config_path))
        batch_outdirs.append(str(sample_outdir / f"batch{index}"))
        samples_per_batch.append(assigned)'''

OLD_METADATA_TAIL = '''        "num_samples": int_param(params, "num_samples", 100, 1, 10000),'''

NEW_METADATA_TAIL = '''        "num_samples": total_samples,
        "batch_size": batch_size,
        "batch_count": batch_count,
        "samples_per_batch": samples_per_batch,
        "batch_configs": batch_configs,
        "batch_outdirs": batch_outdirs,'''

OLD_ENV_TAIL = '''            "POCKET2MOL_CONFIG": config_out,'''

NEW_ENV_TAIL = '''            "POCKET2MOL_CONFIG": config_out,
            "POCKET2MOL_BATCH_COUNT": batch_count,
            "POCKET2MOL_BATCH_CONFIGS": " ".join(batch_configs),
            "POCKET2MOL_BATCH_OUTDIRS": " ".join(batch_outdirs),'''

OLD_FINALIZE_HEAD = '''    run_dir = newest_run_dir(sample_outdir)
    sdf_dir = run_dir / "SDF"
    sdf_files = sorted(sdf_dir.glob("*.sdf")) if sdf_dir.is_dir() else []
    smiles = read_smiles(run_dir / "SMILES.txt")'''

NEW_FINALIZE_HEAD = '''    run_dirs = batch_run_dirs(sample_outdir)
    run_dir = run_dirs[0]
    # batch_size > 1 时每批各自一个 run 目录，产物要按批次顺序合并：
    # SMILES 直接拼接，SDF 加批次前缀避免同名覆盖。
    smiles: list[str] = []
    merged_sdf: list[Path] = []
    merged_sdf_dir = artifact_dir / "SDF"
    if merged_sdf_dir.exists():
        shutil.rmtree(merged_sdf_dir)
    for index, batch_run_dir in enumerate(run_dirs):
        smiles.extend(read_smiles(batch_run_dir / "SMILES.txt"))
        batch_sdf_dir = batch_run_dir / "SDF"
        if not batch_sdf_dir.is_dir():
            continue
        merged_sdf_dir.mkdir(parents=True, exist_ok=True)
        for sdf_path in sorted(batch_sdf_dir.glob("*.sdf")):
            name = f"b{index}-{sdf_path.name}" if len(run_dirs) > 1 else sdf_path.name
            target = merged_sdf_dir / name
            shutil.copy2(sdf_path, target)
            merged_sdf.append(target)
    sdf_files = merged_sdf'''

OLD_SMILES_COPY = '''    if copy_file_if_exists(run_dir / "SMILES.txt", artifact_dir / "SMILES.txt"):
        artifacts.append(artifact("artifacts/SMILES.txt", "text/plain"))'''

NEW_SMILES_COPY = '''    if smiles:
        merged_smiles = artifact_dir / "SMILES.txt"
        merged_smiles.write_text("\\n".join(smiles) + "\\n", encoding="utf-8")
        artifacts.append(artifact("artifacts/SMILES.txt", "text/plain"))
    for index, batch_run_dir in enumerate(run_dirs):
        suffix = "" if len(run_dirs) == 1 else f".batch{index}"
        copy_file_if_exists(batch_run_dir / "log.txt", artifact_dir / f"sample{suffix}.log")'''

OLD_ARTIFACT_LOG = '''    if copy_file_if_exists(run_dir / "log.txt", artifact_dir / "sample.log"):
        artifacts.append(artifact("artifacts/sample.log", "text/plain", "sample.log"))'''

NEW_ARTIFACT_LOG = '''    for index, batch_run_dir in enumerate(run_dirs):
        suffix = "" if len(run_dirs) == 1 else f".batch{index}"
        log_name = f"sample{suffix}.log"
        if (artifact_dir / log_name).is_file():
            artifacts.append(artifact(f"artifacts/{log_name}", "text/plain", log_name))'''

OLD_SDF_BLOCK = '''    if sdf_files:
        individual_sdf_dir = artifact_dir / "SDF"
        if individual_sdf_dir.exists():
            shutil.rmtree(individual_sdf_dir)
        individual_sdf_dir.mkdir(parents=True, exist_ok=True)
        for sdf_file in sdf_files:
            shutil.copy2(sdf_file, individual_sdf_dir / sdf_file.name)
        combined_sdf = artifact_dir / "generated_molecules.sdf"'''

NEW_SDF_BLOCK = '''    if sdf_files:
        combined_sdf = artifact_dir / "generated_molecules.sdf"'''

OLD_NEWEST = '''def newest_run_dir(sample_outdir: Path) -> Path:'''

NEW_NEWEST = '''def batch_run_dirs(sample_outdir: Path) -> list[Path]:
    """返回每一批采样的 run 目录（按批次序）。

    batch_size > 1 时样本目录下是 ``batch0/``、``batch1/``…，每个里面各有一次
    ``sample_for_pdb.py`` 生成的 run 目录；batch_size == 1 时退回单目录布局。
    """
    batch_dirs = sorted(
        (path for path in sample_outdir.iterdir() if path.is_dir() and path.name.startswith("batch")),
        key=lambda path: path.name,
    )
    if batch_dirs:
        return [newest_run_dir(path) for path in batch_dirs]
    return [newest_run_dir(sample_outdir)]


def newest_run_dir(sample_outdir: Path) -> Path:'''

OLD_RUN_SH_BLOCK = '''RUN_CMD=(
  "${MODEL_PYTHON}"
  "${MODEL_ROOT}/sample_for_pdb.py"
  --pdb_path "${POCKET2MOL_PDB_PATH}"
  --center "${POCKET2MOL_CENTER}"
  --bbox_size "${POCKET2MOL_BBOX_SIZE}"
  --config "${POCKET2MOL_CONFIG}"
  --device "${POCKET2MOL_RUNTIME_DEVICE}"
  --outdir "${POCKET2MOL_SAMPLE_OUTDIR}"
)

if [[ -n "${POCKET2MOL_TASKSET_CPU}" ]] && command -v taskset >/dev/null 2>&1; then
  echo "[platform_run] taskset_cpu=${POCKET2MOL_TASKSET_CPU}"
  taskset -c "${POCKET2MOL_TASKSET_CPU}" "${RUN_CMD[@]}"
else
  "${RUN_CMD[@]}"
fi'''

NEW_RUN_SH_BLOCK = '''BATCH_COUNT="${POCKET2MOL_BATCH_COUNT:-1}"
read -r -a BATCH_CONFIGS <<< "${POCKET2MOL_BATCH_CONFIGS:-${POCKET2MOL_CONFIG}}"
read -r -a BATCH_OUTDIRS <<< "${POCKET2MOL_BATCH_OUTDIRS:-${POCKET2MOL_SAMPLE_OUTDIR}}"

echo "[platform_run] batch_count=${BATCH_COUNT}"

run_batch() {
  local index="$1"
  local config="${BATCH_CONFIGS[$index]}"
  local outdir="${BATCH_OUTDIRS[$index]}"
  mkdir -p "${outdir}"
  echo "[platform_run] batch ${index}: config=${config} outdir=${outdir}"
  local cmd=(
    "${MODEL_PYTHON}"
    "${MODEL_ROOT}/sample_for_pdb.py"
    --pdb_path "${POCKET2MOL_PDB_PATH}"
    --center "${POCKET2MOL_CENTER}"
    --bbox_size "${POCKET2MOL_BBOX_SIZE}"
    --config "${config}"
    --device "${POCKET2MOL_RUNTIME_DEVICE}"
    --outdir "${outdir}"
  )
  if [[ -n "${POCKET2MOL_TASKSET_CPU}" ]] && command -v taskset >/dev/null 2>&1; then
    echo "[platform_run] batch ${index} taskset_cpu=${POCKET2MOL_TASKSET_CPU}"
    taskset -c "${POCKET2MOL_TASKSET_CPU}" "${cmd[@]}"
  else
    "${cmd[@]}"
  fi
}

if [[ "${BATCH_COUNT}" -le 1 ]]; then
  run_batch 0
else
  # 多批并行：任一失败都要让整个任务失败，否则会拿到「少了几批」的结果却显示成功。
  pids=()
  for ((i = 0; i < BATCH_COUNT; i++)); do
    run_batch "${i}" &
    pids+=("$!")
  done
  failed=0
  for pid in "${pids[@]}"; do
    if ! wait "${pid}"; then
      failed=1
    fi
  done
  if [[ "${failed}" -ne 0 ]]; then
    echo "One or more sampling batches failed" >&2
    exit 1
  fi
fi'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"[patch] {label}: 期望命中 1 次，实际 {text.count(old)} 次")
    return text.replace(old, new, 1)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    platform_py = root / PLATFORM_PY
    run_sh = root / RUN_SH
    for path in (platform_py, run_sh):
        if not path.is_file():
            raise SystemExit(f"[patch] 找不到 {path}")

    py_text = platform_py.read_text(encoding="utf-8")
    if "POCKET2MOL_BATCH_COUNT" in py_text:
        # 早期版本的补丁漏掉了「合并 SMILES / 逐批复制 log」两段（常量写了但没接线），
        # 对已经打过补丁的树只补齐缺失的两段，其余保持原样。
        print("[patch] pocket2mol_platform.py 已含 batch 支持，只补齐缺失片段")
    else:
        py_text = replace_once(py_text, OLD_WRITE_SIGNATURE, NEW_WRITE_SIGNATURE, "write_sample_config 签名")
        py_text = replace_once(py_text, OLD_SEED_LINES, NEW_SEED_LINES, "seed/num_samples 取参")
        py_text = replace_once(py_text, OLD_NEWEST, NEW_NEWEST, "batch_run_dirs")
        py_text = replace_once(py_text, OLD_WRITE_CALL, NEW_WRITE_CALL, "prepare 分批")
        py_text = replace_once(py_text, OLD_METADATA_TAIL, NEW_METADATA_TAIL, "metadata 分批字段")
        py_text = replace_once(py_text, OLD_ENV_TAIL, NEW_ENV_TAIL, "环境变量导出")
        py_text = replace_once(py_text, OLD_FINALIZE_HEAD, NEW_FINALIZE_HEAD, "finalize 合并入口")
        py_text = replace_once(py_text, OLD_SDF_BLOCK, NEW_SDF_BLOCK, "finalize SDF 拷贝")

    # 这两段单独判断：只要还是旧写法就换掉，已经是新写法则跳过。
    if OLD_SMILES_COPY in py_text:
        py_text = replace_once(py_text, OLD_SMILES_COPY, NEW_SMILES_COPY, "合并 SMILES 与逐批 log")
    elif "merged_smiles" not in py_text:
        raise SystemExit("[patch] 合并 SMILES 段缺失且无法识别，请人工检查")
    if OLD_ARTIFACT_LOG in py_text:
        py_text = replace_once(py_text, OLD_ARTIFACT_LOG, NEW_ARTIFACT_LOG, "逐批 log artifact")
    platform_py.write_text(py_text, encoding="utf-8")

    sh_text = run_sh.read_text(encoding="utf-8")
    if OLD_RUN_SH_BLOCK in sh_text:
        sh_text = replace_once(sh_text, OLD_RUN_SH_BLOCK, NEW_RUN_SH_BLOCK, "platform_run.sh 并行采样")
        run_sh.write_text(sh_text, encoding="utf-8")
    elif "POCKET2MOL_BATCH_COUNT" not in sh_text:
        raise SystemExit("[patch] platform_run.sh 既没有旧采样块也没有 batch 支持，请人工检查")
    print("[patch] 完成：batch_size（并行采样批数）已接入 prepare / platform_run.sh / finalize")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
