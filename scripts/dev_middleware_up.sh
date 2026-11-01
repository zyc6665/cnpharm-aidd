#!/usr/bin/env bash
# 本地开发中间件（kind）：PostgreSQL / Redis / MinIO 一键拉起
# 用法：bash scripts/dev_middleware_up.sh
# 说明：数据服务跑在 kind 集群里，后端/前端仍在本机直接启动；集群服务通过 kubectl
#       port-forward 暴露到本机固定端口，等价于内网私有化部署的中间件形态。
set -euo pipefail
cd "$(dirname "$0")/.."

SECRETS_FILE=backend/.tmp_mw.env
ENV_FILE=backend/.env
PF_DIR=backend/.tmp_portforward

if [ -f "$SECRETS_FILE" ]; then
  # 复用已生成的密码（PVC 数据仍在，密码必须一致）
  set -a; . "$SECRETS_FILE"; set +a
else
  PGPW=$(openssl rand -hex 24)
  REDISPW=$(openssl rand -hex 24)
  MINIOUSER=sciminer-admin
  MINIOPW=$(openssl rand -hex 24)
  ADMIN_EMAIL=admin@sciminer.com
  ADMIN_PASSWORD=$(openssl rand -base64 12 | tr -d '/+=')
  umask 077
  cat > "$SECRETS_FILE" <<EOF
PGPW=$PGPW
REDISPW=$REDISPW
MINIOUSER=$MINIOUSER
MINIOPW=$MINIOPW
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMIN_PASSWORD
EOF
fi

# 兼容早期生成、尚未包含管理员字段的密码文件
if [ -z "${ADMIN_EMAIL:-}" ]; then
  ADMIN_EMAIL=admin@sciminer.com
  echo "ADMIN_EMAIL=$ADMIN_EMAIL" >> "$SECRETS_FILE"
fi
if [ -z "${ADMIN_PASSWORD:-}" ]; then
  ADMIN_PASSWORD=$(openssl rand -base64 12 | tr -d '/+=')
  echo "ADMIN_PASSWORD=$ADMIN_PASSWORD" >> "$SECRETS_FILE"
fi
export ADMIN_EMAIL ADMIN_PASSWORD

echo "== namespaces =="
kubectl apply -f deploy/kubernetes/namespace.yaml

echo "== secrets =="
kubectl -n sciminer-system create secret generic sciminer-postgres-credentials \
  --from-literal=POSTGRES_DB=scitool \
  --from-literal=POSTGRES_USER=scitool \
  --from-literal=POSTGRES_PASSWORD="$PGPW" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sciminer-system create secret generic sciminer-redis-credentials \
  --from-literal=REDIS_PASSWORD="$REDISPW" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sciminer-storage create secret generic sciminer-minio-credentials \
  --from-literal=MINIO_ROOT_USER="$MINIOUSER" \
  --from-literal=MINIO_ROOT_PASSWORD="$MINIOPW" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "== apply data services =="
kubectl apply -f deploy/kubernetes/data-services-dev.yaml
kubectl apply -f deploy/kubernetes/minio-dev.yaml
kubectl apply -f deploy/kubernetes/minio-dev-nodeport.yaml

echo "== rollout =="
kubectl -n sciminer-system rollout status deployment/sciminer-postgres --timeout=300s
kubectl -n sciminer-system rollout status deployment/sciminer-redis --timeout=300s
kubectl -n sciminer-storage rollout status deployment/sciminer-minio --timeout=300s

echo "== port-forward =="
mkdir -p "$PF_DIR"
start_pf() { # name ns svc local remote
  local name=$1 ns=$2 svc=$3 local=$4 remote=$5
  if [ -f "$PF_DIR/$name.pid" ]; then
    old=$(cat "$PF_DIR/$name.pid")
    kill "$old" 2>/dev/null || true
    rm -f "$PF_DIR/$name.pid"
    sleep 0.5
  fi
  nohup kubectl -n "$ns" port-forward "svc/$svc" "$local:$remote" \
    >"$PF_DIR/$name.log" 2>&1 &
  echo $! > "$PF_DIR/$name.pid"
  echo "  $name -> 127.0.0.1:$local"
}
start_pf postgres sciminer-system sciminer-postgres 15432 5432
start_pf redis    sciminer-system sciminer-redis    16379 6379
start_pf minio    sciminer-storage sciminer-minio   19000 9000
start_pf minio-ui sciminer-storage sciminer-minio   19001 9001
sleep 3

echo "== 生成 backend/.env（仅当不存在） =="
if [ ! -f "$ENV_FILE" ]; then
  JWT=$(openssl rand -hex 32)
  ENC=$(openssl rand -hex 32)
  umask 077
  cat > "$ENV_FILE" <<EOF
ENVIRONMENT=development
DEBUG=false
DATABASE_URL=postgresql+asyncpg://scitool:${PGPW}@127.0.0.1:15432/scitool
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_RECYCLE=3600
PUBLIC_API_BASE_URL=http://localhost:8000
JWT_SECRET_KEY=${JWT}
SETTINGS_ENCRYPTION_KEY=${ENC}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7
STORAGE_BACKEND=minio
MINIO_ENDPOINT=127.0.0.1:19000
MINIO_ACCESS_KEY=${MINIOUSER}
MINIO_SECRET_KEY=${MINIOPW}
MINIO_BUCKET=scitool-files
MINIO_SECURE=false
MAX_FILE_SIZE_MB=100
CACHE_BACKEND=redis
REDIS_HOST=127.0.0.1
REDIS_PORT=16379
REDIS_DB=0
REDIS_PASSWORD=${REDISPW}
REQUEST_RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_TRUST_PROXY_HEADERS=false
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
LOG_LEVEL=INFO
EOF
  echo "  已生成 backend/.env"
else
  echo "  backend/.env 已存在，跳过"
fi

echo "== 管理员账号自举 =="
(
  cd backend
  PYTHONUTF8=1 python -m app.cli.ensure_admin --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD"
)

echo
echo "中间件就绪："
echo "  PostgreSQL  127.0.0.1:15432  db=scitool user=scitool"
echo "  Redis       127.0.0.1:16379"
echo "  MinIO API   127.0.0.1:19000  console http://127.0.0.1:19001"
echo "启动后端：cd backend && python -m alembic upgrade head && python -m uvicorn app.main:app --port 8000"
echo "启动前端：cd frontend && npm run dev"
