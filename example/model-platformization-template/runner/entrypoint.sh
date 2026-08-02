#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODEL_PACKAGE_ROOT="${MODEL_PACKAGE_ROOT:-${BUNDLE_ROOT}/model}"
MODEL_ENTRYPOINT="${MODEL_ENTRYPOINT:-${MODEL_PACKAGE_ROOT}/platform_run.sh}"

if [[ ! -x "${MODEL_ENTRYPOINT}" ]]; then
  echo "Model package entrypoint is not executable: ${MODEL_ENTRYPOINT}" >&2
  exit 2
fi

exec "${MODEL_ENTRYPOINT}" "$@"
