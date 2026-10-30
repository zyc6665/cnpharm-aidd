#!/usr/bin/env bash
# 停止本地开发中间件的 port-forward；--purge 连同集群内数据服务一起删除（会丢数据！）
set -euo pipefail
cd "$(dirname "$0")/.."
PF_DIR=backend/.tmp_portforward

echo "== 停止 port-forward =="
if [ -d "$PF_DIR" ]; then
  for f in "$PF_DIR"/*.pid; do
    [ -e "$f" ] || continue
    pid=$(cat "$f")
    if kill -0 "$pid" 2>/dev/null; then kill "$pid" && echo "  stopped pid $pid"; fi
    rm -f "$f"
  done
fi

if [ "${1:-}" = "--purge" ]; then
  echo "== 删除中间件工作负载（PVC 保留，除非另行删除 PVC） =="
  kubectl delete -f deploy/kubernetes/minio-dev-nodeport.yaml --ignore-not-found
  kubectl delete -f deploy/kubernetes/minio-dev.yaml --ignore-not-found
  kubectl delete -f deploy/kubernetes/data-services-dev.yaml --ignore-not-found
  echo "如需连数据一起删除：kubectl -n sciminer-system delete pvc --all && kubectl -n sciminer-storage delete pvc --all"
fi
