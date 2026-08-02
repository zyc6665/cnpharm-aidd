#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODEL_ENTRYPOINT="${MOLP_PC_MODEL_ENTRYPOINT:-${BUNDLE_ROOT}/model/platform_run.sh}"

exec "${MODEL_ENTRYPOINT}" "$@"
