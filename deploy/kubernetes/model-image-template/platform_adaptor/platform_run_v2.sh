#!/usr/bin/env bash
set -euo pipefail

TASK_ID=""
INPUT_DIR=""
OUTPUT_DIR=""
PARAMS_JSON=""
WORK_DIR=""
DEVICE=""

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

# 过渡期双契约：优先使用 K8s Job 传入的 CLI 参数，缺省时回退到 drp-runner 的 DRP_* 环境变量。
# 这样旧调用方式与 docs/07 §3.6 的新契约可以同时被识别（两套变量都认）。
INPUT_DIR="${INPUT_DIR:-${DRP_IN_DIR:-}}"
OUTPUT_DIR="${OUTPUT_DIR:-${DRP_OUT_DIR:-}}"
PARAMS_JSON="${PARAMS_JSON:-${DRP_TASK_FILE:-}}"
WORK_DIR="${WORK_DIR:-${DRP_WORK_DIR:-}}"
TASK_ID="${TASK_ID:-${DRP_TASK_ID:-}}"
DEVICE="${DEVICE:-${DRP_DEVICE:-auto}}"

if [[ -z "${INPUT_DIR}" || -z "${OUTPUT_DIR}" || -z "${PARAMS_JSON}" || -z "${WORK_DIR}" ]]; then
  echo "Missing required execution arguments" >&2
  exit 2
fi

# 归一化并导出 DRP_* 变量，让模型与 Runner 两侧读到同一份取值（与 SCIMINER_* 并存）。
DRP_TASK_FILE="${DRP_TASK_FILE:-${PARAMS_JSON}}"
DRP_RESULT_FILE="${DRP_RESULT_FILE:-${OUTPUT_DIR}/result.json}"
DRP_OUT_DIR="${DRP_OUT_DIR:-${OUTPUT_DIR}}"
DRP_MODEL_ENTRY="${DRP_MODEL_ENTRY:-/opt/sciminer/model/platform_run.sh}"
DRP_DEVICE="${DRP_DEVICE:-${DEVICE}}"
DRP_HEARTBEAT_SEC="${DRP_HEARTBEAT_SEC:-10}"
DRP_MAX_MINUTES="${DRP_MAX_MINUTES:-}"
export DRP_TASK_FILE DRP_RESULT_FILE DRP_OUT_DIR DRP_MODEL_ENTRY DRP_DEVICE DRP_HEARTBEAT_SEC DRP_MAX_MINUTES

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_PYTHON="${PLATFORM_PYTHON:-python3}"

# Agent 超时会先向容器发 SIGTERM（docs/07 §3.6）。on_term 尽力把已产出物上传后再退出，
# 退出码 13 表示「超时被 Agent SIGTERM」，由 Agent 判 TIMEOUT；被 SIGKILL 时则由 Agent 兜底上传。
on_term() {
  trap - TERM
  echo "Received SIGTERM; uploading partial artifacts before exit 13" >&2
  if [[ -d "${OUTPUT_DIR}" ]]; then
    # 模型可能没有产出 result.json；合成一个最小 FAILED 清单，让 upload 至少提交已产出文件。
    if [[ ! -f "${OUTPUT_DIR}/result.json" ]]; then
      printf '{"result_version":"aidd.sciminer/result","status":"FAILED","reason":"timeout","artifacts":{}}\n' \
        > "${OUTPUT_DIR}/result.json" 2>/dev/null || true
    fi
    "${PLATFORM_PYTHON}" "${SCRIPT_DIR}/object_storage.py" upload \
      --output-dir "${OUTPUT_DIR}" >/dev/null 2>&1 || true
  fi
  exit 13
}
trap 'on_term' TERM

# 步骤 1/2：下载并校验输入；sha256 不符或输入非法 → 退出码 10。
if ! "${PLATFORM_PYTHON}" "${SCRIPT_DIR}/object_storage.py" prepare \
  --input-dir "${INPUT_DIR}" \
  --params-json "${PARAMS_JSON}"; then
  echo "Input preparation failed (invalid input or checksum mismatch)" >&2
  exit 10
fi

# 部分遗留模型的入口脚本不认 --model-root（它们从脚本自身所在目录解析模型根），
# 直接传会以 `Unknown argument: --model-root` 退出码 2 失败。先探测脚本是否支持该参数。
MODEL_ROOT_ARGS=()
if grep -q -- '--model-root)' "${DRP_MODEL_ENTRY}" 2>/dev/null; then
  MODEL_ROOT_ARGS+=(--model-root "${MODEL_PACKAGE_ROOT:-/opt/sciminer/model}")
fi

# 步骤 3：运行模型。非 0（含被信号终止）→ 视为模型异常，退出码 12；
# 若超时 SIGTERM 已触发，on_term 会先执行并 exit 13。
set +e
"${DRP_MODEL_ENTRY}" \
  ${MODEL_ROOT_ARGS[@]+"${MODEL_ROOT_ARGS[@]}"} \
  --task-id "${TASK_ID}" \
  --input-dir "${INPUT_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --params-json "${PARAMS_JSON}" \
  --work-dir "${WORK_DIR}" \
  --device "${DEVICE}"
MODEL_EXIT=$?
set -e
if [[ ${MODEL_EXIT} -ne 0 ]]; then
  echo "Model entry failed with exit code ${MODEL_EXIT}" >&2
  exit 12
fi

# 步骤 4：校验 result.json 存在、schema 正确且产物不越界 → 缺失/越界退出码 11。
if ! "${PLATFORM_PYTHON}" "${SCRIPT_DIR}/object_storage.py" validate \
  --output-dir "${OUTPUT_DIR}"; then
  echo "Result validation failed (missing result.json or artifact path escape)" >&2
  exit 11
fi

# 步骤 5：上传产物并最后发布 result.json；存储侧失败归为其它错误（退出码 1）。
if ! "${PLATFORM_PYTHON}" "${SCRIPT_DIR}/object_storage.py" upload \
  --output-dir "${OUTPUT_DIR}"; then
  echo "Artifact upload failed" >&2
  exit 1
fi
