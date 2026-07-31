#!/usr/bin/env bash
set -euo pipefail

request_path="${TOOL_REQUEST_PATH:-request.json}"
output_dir="${TOOL_OUTPUT_DIR:-output}"

mkdir -p "${output_dir}"
python -m runner.tool_impl "${request_path}" "${output_dir}"
python -m runner.result_parser "${output_dir}/result.json" "${output_dir}"
