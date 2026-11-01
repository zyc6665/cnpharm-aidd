#!/usr/bin/env bash
# 为 MSIGN 构建上下文打补丁：让 platform_run.sh 在 SMILES 转 3D 时把构象放到
# 蛋白重原子锚点（否则配体停在原点，模型报 "No protein pocket atoms were found
# within 5 Angstrom of the ligand"），并重新打包为 model_v2.tar.gz。
#
# 用法（在包含 model.tar.gz 的构建目录执行）：
#   bash prepare_build_context.sh
set -euo pipefail

src="${1:-model.tar.gz}"
out="${2:-model_v2.tar.gz}"
if [[ ! -f "${src}" ]]; then
  echo "missing ${src}" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
tar -xzf "${src}" -C "${tmp}"

python3 - "${tmp}/MSIGN/platform_run.sh" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
if "--center-from-protein" in text:
    raise SystemExit(0)
needle = '    --errors-json "${OUTPUT_DIR}/artifacts/smiles_conversion_errors.json" \\\n'
if needle not in text:
    raise SystemExit("platform_run.sh: smiles_to_sdf invocation not found; inspect before building")
text = text.replace(
    needle,
    needle + '    --center-from-protein "${PROTEIN_PDB}" \\\n',
    1,
)
path.write_text(text, encoding="utf-8")
PY

tar -czf "${out}" -C "${tmp}" MSIGN
echo "wrote ${out}"
