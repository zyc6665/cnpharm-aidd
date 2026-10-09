#!/usr/bin/env bash
set -euo pipefail

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

if [[ -z "${INPUT_DIR}" || -z "${OUTPUT_DIR}" || -z "${PARAMS_JSON}" || -z "${WORK_DIR}" ]]; then
  echo "Missing required execution arguments" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_PYTHON="${PLATFORM_PYTHON:-python3}"
"${PLATFORM_PYTHON}" "${SCRIPT_DIR}/object_storage.py" prepare \
  --input-dir "${INPUT_DIR}" \
  --params-json "${PARAMS_JSON}"

/opt/sciminer/model/platform_run.sh \
  --model-root "${MODEL_PACKAGE_ROOT:-/opt/sciminer/model}" \
  --task-id "${TASK_ID}" \
  --input-dir "${INPUT_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --params-json "${PARAMS_JSON}" \
  --work-dir "${WORK_DIR}" \
  --device "${DEVICE}"

"${PLATFORM_PYTHON}" "${SCRIPT_DIR}/object_storage.py" upload \
  --output-dir "${OUTPUT_DIR}"
