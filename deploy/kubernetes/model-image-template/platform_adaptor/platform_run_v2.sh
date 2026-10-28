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

# 部分遗留模型的入口脚本不认 --model-root（它们从脚本自身所在目录解析模型根），
# 直接传会以 `Unknown argument: --model-root` 退出码 2 失败。先探测脚本是否支持该参数。
MODEL_ROOT_ARGS=()
if grep -q -- '--model-root)' /opt/sciminer/model/platform_run.sh 2>/dev/null; then
  MODEL_ROOT_ARGS+=(--model-root "${MODEL_PACKAGE_ROOT:-/opt/sciminer/model}")
fi

/opt/sciminer/model/platform_run.sh \
  ${MODEL_ROOT_ARGS[@]+"${MODEL_ROOT_ARGS[@]}"} \
  --task-id "${TASK_ID}" \
  --input-dir "${INPUT_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --params-json "${PARAMS_JSON}" \
  --work-dir "${WORK_DIR}" \
  --device "${DEVICE}"

"${PLATFORM_PYTHON}" "${SCRIPT_DIR}/object_storage.py" upload \
  --output-dir "${OUTPUT_DIR}"
