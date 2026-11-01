#!/usr/bin/env bash
# LVpocket-2 镜像构建脚本：prepare / build / smoke / push
#
# 用法：
#   export MODEL_SRC=/data/zhouyc/kaiwu/LVpocket-2     # 模型源目录（含 env/、new_best/、platform_run.sh）
#   export WEIGHTS_DIR=/data/zhouyc/model-cache/lvpocket/v2/new_best
#   ./build.sh prepare && ./build.sh build && ./build.sh smoke && ./build.sh push
#
# 设计说明：
#   - model/ 从源目录拷出后要跟软链（cp -aL / rsync -L），源目录里 new_best 是软链指向 new_best_1，
#     不跟软链会得到一个断链目录。
#   - 源目录的 env/（Python 虚拟环境，5.8 GB）**不要**拷——容器里按 requirements.txt 重装。
#   - 权重不进构建上下文，smoke 阶段才只读挂载。
set -Eeuo pipefail

MODEL_SLUG="${MODEL_SLUG:-lvpocket}"
MODEL_VERSION="${MODEL_VERSION:-2.0.0}"
BASE_IMAGE="${BASE_IMAGE:-python:3.11-slim}"
REGISTRY="${REGISTRY:-127.0.0.1:30500}"
IMAGE_REPO="${REGISTRY}/aidd/compute-${MODEL_SLUG}"
IMAGE_TAG="${MODEL_VERSION}-cu122"
IMAGE="${IMAGE_REPO}:${IMAGE_TAG}"
MODEL_SRC="${MODEL_SRC:?需要设置 MODEL_SRC（模型源目录）}"
WEIGHTS_DIR="${WEIGHTS_DIR:?需要设置 WEIGHTS_DIR（权重目录）}"
ADAPTOR_SRC="${ADAPTOR_SRC:-../../kubernetes/model-image-template/platform_adaptor}"
GPU_DEVICE="${GPU_DEVICE:-2}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${HERE}"

log() { printf '\n=== %s ===\n' "$*"; }

prepare() {
  log "准备构建上下文（源：${MODEL_SRC}）"
  rm -rf model platform_adaptor
  mkdir -p model

  # 1) 模型代码：跟软链拷贝，但排除 env/（虚拟环境，容器里重装）与 new_best/（权重）
  rsync -aL \
    --exclude 'env/' --exclude 'new_best/' --exclude 'new_best_*/' \
    --exclude '__pycache__/' --exclude '*.pyc' \
    "${MODEL_SRC}/" model/

  # 2) 适配层：从通用模板取，再叠本模型的 patch 脚本
  cp -r "${ADAPTOR_SRC}" platform_adaptor
  cp ../shared/patch_openbabel.py platform_adaptor/patch_openbabel.py

  # 3) requirements：若源目录没有，用本目录的（本目录的是按实际 pip list 固化的）
  [ -f model/requirements.txt ] || cp requirements.txt model/requirements.txt

  log "上下文大小"
  du -sh model platform_adaptor
  # 4) result.v2 契约对齐
  #    源目录的 platform_run.sh 产出的是 v1 形状（顶层 success/message/outputs/error、
  #    artifacts 是 list），而平台 StandardExecutionResult 是 extra="forbid"，
  #    只认 result_version/artifacts/relations/summary/metrics，且 artifacts 必须是
  #    按名分键的 object、每个产物必须带 type 与 files{role:{path,sha256}}。
  #    详见 patches/patch_result_v2.py 的模块 docstring。
  python3 patches/patch_result_v2.py model/platform_run.sh

  log "权重目录"
  du -sh "${WEIGHTS_DIR}"
}

build() {
  log "构建 ${IMAGE}"
  DOCKER_BUILDKIT=1 docker build \
    --build-arg BASE_IMAGE="${BASE_IMAGE}" \
    -t "${IMAGE}" .
  docker image ls "${IMAGE}" --format '镜像 {{.Repository}}:{{.Tag}} 大小 {{.Size}}'
}

smoke() {
  local out="/tmp/${MODEL_SLUG}-smoke-$(date +%s)"
  local ob=/usr/local/lib/python3.11/site-packages/openbabel
  mkdir -p "${out}/input"
  # 需要 ${HERE}/examples/protein.pdb 与 params.json
  cp "${HERE}"/examples/protein.pdb "${out}/input/protein.pdb"
  cat > "${out}/params.json" <<JSON
{"task_name":"${MODEL_SLUG}-smoke","params":{"model_choice":"auto","device":"gpu"},
 "input_files":{"protein_pdb":"protein.pdb"}}
JSON
  log "smoke 输出目录 ${out}"
  docker run --rm --gpus "\"device=${GPU_DEVICE}\"" \
    -v "${WEIGHTS_DIR}:/opt/sciminer/model/new_best:ro" \
    -v "${out}/input:/workspace/input" \
    -v "${out}/params.json:/workspace/params.json:ro" \
    -v "${out}:/workspace/output" \
    -e BABEL_LIBDIR="${ob}/lib" \
    -e BABEL_DATADIR="${ob}/share/openbabel/3.1.0" \
    "${IMAGE}" --task-id smoke-001 \
      --input-dir /workspace/input --output-dir /workspace/output \
      --params-json /workspace/params.json --work-dir /workspace/output/work \
      --device gpu 2>&1 | tail -20

  log "result.json"
  python3 - "${out}/result.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
out = data["outputs"]
print("success        ", data["success"])
print("message        ", data["message"])
print("device         ", out.get("device"))
print("pocket_count   ", out.get("pocket_count"))
print("selected_model ", out.get("selected_model"))
print("metrics        ", data["metrics"])
print("artifacts      ", len(data["artifacts"]))
PY
  echo "提示：手工 smoke 不注入 SCIMINER_OBJECT_STORAGE_*，上传阶段会报"
  echo "     ObjectStorageError（预期）。result.json 已写出即说明推理链路正常；"
  echo "     完整链路请由平台真实提交触发。"
}

push() {
  log "推送 ${IMAGE}"
  docker push "${IMAGE}"
  log "不可变 digest（填进 weights.json 与 ToolVersion.image）"
  docker image inspect "${IMAGE}" --format '{{index .RepoDigests 0}}'
}

case "${1:-}" in
  prepare) prepare ;;
  build) build ;;
  smoke) smoke ;;
  push) push ;;
  *) echo "用法: $0 {prepare|build|smoke|push}" >&2; exit 2 ;;
esac
