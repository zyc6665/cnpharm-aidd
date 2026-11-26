#!/usr/bin/env bash
set -euo pipefail

TASK_ID="unknown"
INPUT_DIR=""
OUTPUT_DIR=""
PARAMS_JSON=""
WORK_DIR=""
DEVICE="auto"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-id)
      TASK_ID="${2:-unknown}"
      shift 2
      ;;
    --input-dir)
      INPUT_DIR="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --params-json)
      PARAMS_JSON="${2:-}"
      shift 2
      ;;
    --work-dir)
      WORK_DIR="${2:-}"
      shift 2
      ;;
    --device)
      DEVICE="${2:-auto}"
      shift 2
      ;;
    --model-root)
      MODEL_PACKAGE_ROOT="${2:-/opt/aidd/lddm}"
      shift 2
      ;;
    *)
      echo "[lddm_platform_run] unknown argument: $1" >&2
      shift
      ;;
  esac
done

MODEL_ROOT="${MODEL_PACKAGE_ROOT:-/opt/aidd/lddm}"
MODEL_PYTHON="${MODEL_PYTHON:-/opt/conda/bin/python}"
PLATFORM_PYTHON="${PLATFORM_PYTHON:-${MODEL_PYTHON}}"

mkdir -p "${OUTPUT_DIR}/artifacts" "${WORK_DIR}"
START_TS="$(date +%s)"

on_err() {
  local rc=$?
  "${PLATFORM_PYTHON}" "${MODEL_ROOT}/lddm_platform.py" fail \
    --output-dir "${OUTPUT_DIR}" \
    --message "LDDM execution failed (exit ${rc})" \
    --start-ts "${START_TS}" || true
  exit "${rc}"
}
trap 'on_err' ERR

RUN_ENV="${WORK_DIR}/lddm_env.sh"
META_JSON="${WORK_DIR}/lddm_metadata.json"
RAW_SDF="${WORK_DIR}/lddm_raw_samples.sdf"

"${PLATFORM_PYTHON}" "${MODEL_ROOT}/lddm_platform.py" prepare \
  --task-id "${TASK_ID}" \
  --input-dir "${INPUT_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --params-json "${PARAMS_JSON}" \
  --work-dir "${WORK_DIR}" \
  --device "${DEVICE}" \
  --env-out "${RUN_ENV}" \
  --metadata-out "${META_JSON}" \
  --sdf-out "${RAW_SDF}"

# shellcheck disable=SC1090
source "${RUN_ENV}"

echo "[lddm_platform_run] mode=${LDDM_MODE:-design} (${LDDM_GENERATION_MODE:-denovo})"
echo "[lddm_platform_run] protein=${LDDM_PROTEIN}"
echo "[lddm_platform_run] ref_ligand=${LDDM_REF_LIGAND}"
echo "[lddm_platform_run] checkpoint=${LDDM_CHECKPOINT}"
echo "[lddm_platform_run] n_samples=${LDDM_N_SAMPLES} batch_size=${LDDM_BATCH_SIZE} n_steps=${LDDM_N_STEPS} sampler=${LDDM_SAMPLER}"
echo "[lddm_platform_run] device=${LDDM_RUNTIME_DEVICE}"

cd "${MODEL_ROOT}"
export PYTHONPATH="${MODEL_ROOT}:${PYTHONPATH:-}"

CMD=(
  "${MODEL_PYTHON}"
  "${MODEL_ROOT}/scripts/sample.py"
  "${LDDM_MODE:-design}"
  --protein "${LDDM_PROTEIN}"
  --ref_ligand "${LDDM_REF_LIGAND}"
  --checkpoint "${LDDM_CHECKPOINT}"
  --output "${LDDM_OUTPUT_SDF}"
  --n_samples "${LDDM_N_SAMPLES}"
  --batch_size "${LDDM_BATCH_SIZE}"
  --n_steps "${LDDM_N_STEPS}"
  --sampler "${LDDM_SAMPLER}"
  --sampling_noise "${LDDM_SAMPLING_NOISE}"
  --seed "${LDDM_SEED}"
  --device "${LDDM_RUNTIME_DEVICE}"
)

if [[ -n "${LDDM_MOLECULE_SIZE:-}" ]]; then
  CMD+=(--molecule_size "${LDDM_MOLECULE_SIZE}")
fi
if [[ -n "${LDDM_FRAG_LIGAND:-}" ]]; then
  CMD+=(--ligand "${LDDM_FRAG_LIGAND}")
fi
if [[ "${LDDM_MODE:-design}" == "dock" && -n "${LDDM_ATOMS_TO_DOCK:-}" ]]; then
  read -r -a DOCK_ATOMS <<< "${LDDM_ATOMS_TO_DOCK}"
  CMD+=(--atoms_to_dock "${DOCK_ATOMS[@]}")
fi

"${CMD[@]}"

"${PLATFORM_PYTHON}" "${MODEL_ROOT}/lddm_platform.py" finalize \
  --task-id "${TASK_ID}" \
  --output-dir "${OUTPUT_DIR}" \
  --sdf-path "${LDDM_OUTPUT_SDF}" \
  --metadata-json "${LDDM_METADATA_JSON}" \
  --start-ts "${START_TS}"

echo "[lddm_platform_run] done"
