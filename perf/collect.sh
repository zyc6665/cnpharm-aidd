#!/usr/bin/env bash
# 压测前后环境快照：对 结果/产物/任务/workflow 列表 跑 EXPLAIN (ANALYZE, BUFFERS)，并抓 /metrics。
#
# 缺 psql / /metrics 未接线时**降级**：记录跳过原因，不中断、不报错退出。
#
# 用法：
#   perf/collect.sh --label before --out perf/results/20261101-1200 --project-id <pid>
#   perf/collect.sh --label after  --out perf/results/20261101-1200 --project-id <pid>
#
# 参数：
#   --label        before|after（默认 snapshot）
#   --out          输出根目录（默认 perf/results/<timestamp>）
#   --project-id   要 EXPLAIN 的项目 id（默认 $PERF_PROJECT_ID）
#   --base-url     API 根（默认 $PERF_BASE_URL 或 http://127.0.0.1:8000/api/v1）
#   --database-url 覆盖数据库连接串（默认从 backend/.env 的 DATABASE_URL 派生）
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

LABEL="snapshot"
OUT=""
PROJECT_ID="${PERF_PROJECT_ID:-}"
BASE_URL="${PERF_BASE_URL:-http://127.0.0.1:8000/api/v1}"
DATABASE_URL_ARG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --label) LABEL="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --project-id) PROJECT_ID="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --database-url) DATABASE_URL_ARG="$2"; shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$OUT" ]; then
  OUT="$SCRIPT_DIR/results/$(date +%Y%m%d-%H%M%S)"
fi
SNAP_DIR="$OUT/$LABEL"
mkdir -p "$SNAP_DIR"

BASE_URL="${BASE_URL%/}"
ORIGIN="${BASE_URL%/api/v1}"

# 数据库连接串：优先参数，其次 backend/.env
PGURL="$DATABASE_URL_ARG"
if [ -z "$PGURL" ] && [ -f "$REPO_ROOT/backend/.env" ]; then
  PGURL="$(grep -E '^DATABASE_URL=' "$REPO_ROOT/backend/.env" | head -1 | cut -d= -f2-)"
  PGURL="$(echo "$PGURL" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
fi
# psql 不认 +asyncpg，去掉驱动后缀
PGURL="$(echo "$PGURL" | sed 's/+asyncpg//g; s/+aiosqlite//g')"

{
  echo "label=$LABEL"
  echo "time=$(date -Iseconds 2>/dev/null || date)"
  echo "base_url=$BASE_URL"
  echo "project_id=${PROJECT_ID:-<none>}"
  echo "psql=$(command -v psql >/dev/null 2>&1 && echo yes || echo no)"
  echo "database=${PGURL%%\?*}"
} > "$SNAP_DIR/meta.txt"

# ---- /metrics 与健康检查 -------------------------------------------------
HEALTH_CODE="$(curl -sS -o "$SNAP_DIR/health.json" -w '%{http_code}' "$BASE_URL/system/health" 2>/dev/null || echo "ERR")"
echo "health: HTTP $HEALTH_CODE -> $SNAP_DIR/health.json"

METRICS_CODE="$(curl -sS -o "$SNAP_DIR/metrics.txt" -w '%{http_code}' "$ORIGIN/metrics" 2>/dev/null || echo "ERR")"
if [ "$METRICS_CODE" = "200" ]; then
  echo "metrics: HTTP 200 -> $SNAP_DIR/metrics.txt"
else
  {
    echo "# /metrics 未可取（HTTP $METRICS_CODE）。"
    echo "# 注：backend/app/monitoring/prometheus_metrics.py 已实现 PrometheusMiddleware/metrics_endpoint，"
    echo "#     且已在 backend/app/main.py 注册（METRICS_ENABLED=true），请确认后端已重启且未被网关拦截。"
  } > "$SNAP_DIR/metrics.txt"
  echo "metrics: 不可取（HTTP $METRICS_CODE），已写说明 -> $SNAP_DIR/metrics.txt"
fi

# ---- EXPLAIN (ANALYZE, BUFFERS) -----------------------------------------
if ! command -v psql >/dev/null 2>&1; then
  echo "psql: 未安装，跳过 EXPLAIN（安装 postgresql-client 后重跑本脚本）" | tee "$SNAP_DIR/psql_missing.txt"
  exit 0
fi

if [ -z "$PGURL" ]; then
  echo "psql: 未取到 DATABASE_URL，跳过 EXPLAIN" | tee "$SNAP_DIR/psql_missing.txt"
  exit 0
fi

if [ -z "$PROJECT_ID" ]; then
  echo "psql: 未提供 --project-id，跳过 EXPLAIN" | tee "$SNAP_DIR/psql_missing.txt"
  exit 0
fi

run_explain() {
  local name="$1"; local sql="$2"
  if psql "$PGURL" -v ON_ERROR_STOP=1 -c "EXPLAIN (ANALYZE, BUFFERS) $sql" > "$SNAP_DIR/${name}.explain.txt" 2>&1; then
    echo "  [ok]   $name -> ${name}.explain.txt"
  else
    echo "  [warn] $name 失败（见 ${name}.explain.txt）"
  fi
}

echo "EXPLAIN（project_id=$PROJECT_ID）："
run_explain "results" "SELECT id FROM tasks WHERE project_id='$PROJECT_ID' AND status IN ('success','failure','canceled','timeout') ORDER BY finished_at DESC, id DESC LIMIT 50"
run_explain "artifacts" "SELECT a.id FROM artifacts a WHERE a.project_id='$PROJECT_ID' AND EXISTS (SELECT 1 FROM artifact_versions v WHERE v.id = a.latest_version_id AND v.status = 'available' AND (v.expires_at IS NULL OR v.expires_at > now())) ORDER BY a.created_at DESC, a.id DESC LIMIT 50"
run_explain "tasks" "SELECT id FROM tasks WHERE project_id='$PROJECT_ID' ORDER BY created_at DESC, id DESC LIMIT 50"
run_explain "workflows" "SELECT id FROM workflow_runs WHERE project_id='$PROJECT_ID' ORDER BY created_at DESC, id DESC LIMIT 50"

echo "快照完成 -> $SNAP_DIR"
