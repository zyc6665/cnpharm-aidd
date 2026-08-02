#!/usr/bin/env bash
set -euo pipefail

MODEL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${GCDM_PYTHON:-python3}"

TASK_ID=""
INPUT_DIR=""
OUTPUT_DIR=""
PARAMS_JSON=""
WORK_DIR=""
DEVICE="auto"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-id) TASK_ID="$2"; shift 2 ;;
    --input-dir) INPUT_DIR="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --params-json) PARAMS_JSON="$2"; shift 2 ;;
    --work-dir) WORK_DIR="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "${INPUT_DIR}" || -z "${OUTPUT_DIR}" || -z "${PARAMS_JSON}" ]]; then
  echo "Missing required arguments: --input-dir, --output-dir, --params-json" >&2
  exit 2
fi

if [[ -z "${WORK_DIR}" ]]; then
  WORK_DIR="$(dirname "${OUTPUT_DIR}")/work"
fi

mkdir -p "${OUTPUT_DIR}/logs" "${WORK_DIR}"
LOG_FILE="${OUTPUT_DIR}/logs/run.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

export PYTHONUNBUFFERED=1
export PYTHONPATH="${MODEL_ROOT}/src:${PYTHONPATH:-}"

"${PYTHON_BIN}" -m gcdm_runtime.cli \
  --model-root "${MODEL_ROOT}" \
  --task-id "${TASK_ID}" \
  --input-dir "${INPUT_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --params-json "${PARAMS_JSON}" \
  --work-dir "${WORK_DIR}" \
  --device "${DEVICE}"
