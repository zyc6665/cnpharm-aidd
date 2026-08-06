# K100 Platform Deployment Runbook

This runbook packages the platform side for K100/DCU compatibility testing. Model
runtime packages stay outside the platform image and are invoked through the
existing `ssh_job` execution Interface.

## 1. Prepare Test Configuration

On the build machine:

```bash
cp .env.k100-test.example .env.k100-test
```

Edit `.env.k100-test` and replace all placeholder secrets. Do not commit the real
file. For HTTP/IP testing, keep `ENVIRONMENT=development`; switch to `production`
only when using trusted HTTPS origins and production secrets.

Important variables:

- `FRONTEND_PORT`: browser entrypoint, default `8585`.
- `BACKEND_PORT`: direct API port, default `9501`.
- `JWT_SECRET_KEY` and `SETTINGS_ENCRYPTION_KEY`: different values, at least 32
  characters each.
- `SSH_PASSWORD_REF_K100_MODEL_TEST`: password for tools whose
  `password_ref` is `k100_model_test`.
- `SSH_PASSWORD_REF_SSH_4090_ZHOUYC`: compatibility placeholder only if imported
  tools still reference the old password ref.

## 2. Build Images

Build the platform images and pull third-party service images:

```bash
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml build
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml pull postgres redis minio
```

If the K100 host cannot pull images from the network, export all required images:

```bash
docker save \
  sciminer-backend:k100-test \
  sciminer-frontend:k100-test \
  postgres:16-alpine \
  redis:7-alpine \
  minio/minio:RELEASE.2024-06-13T22-53-53Z \
  -o sciminer-k100-platform-images.tar
```

Package deployment files without secrets:

```bash
tar --use-compress-program="zstd -T0 -3" \
  -cf sciminer-k100-platform-deploy.tar.zst \
  docker-compose.k100-test.yml \
  .env.k100-test.example
```

Transfer `sciminer-k100-platform-images.tar`,
`sciminer-k100-platform-deploy.tar.zst`, and the separately prepared
`.env.k100-test` to the K100 test host.

## 3. Load And Start On K100 Host

On the K100 host:

```bash
docker load -i sciminer-k100-platform-images.tar
mkdir -p /opt/sciminer/platform
tar --use-compress-program=unzstd -xf sciminer-k100-platform-deploy.tar.zst -C /opt/sciminer/platform
cp .env.k100-test /opt/sciminer/platform/.env.k100-test
cd /opt/sciminer/platform
```

Start infrastructure first:

```bash
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml up -d postgres redis minio
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml ps
```

Run database migrations:

```bash
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml --profile tools run --rm backend-migrate
```

Start platform services:

```bash
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml up -d backend celery-worker frontend
```

## 4. Health Checks

Check service state:

```bash
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml ps
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml logs --tail=100 backend
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml logs --tail=100 celery-worker
```

Check HTTP endpoints:

```bash
curl -f http://127.0.0.1:${BACKEND_PORT:-9501}/api/v1/system/health
curl -f http://127.0.0.1:${FRONTEND_PORT:-8585}/health
```

Open the frontend:

```text
http://<k100-host-ip>:8585
```

## 5. Model Execution Setup

Keep model packages in the existing K100 `model_test` container or another model
runtime container. Do not copy model runtimes into the platform images.

For same-host testing, the Compose stack maps `host.docker.internal` to the Docker
host. Configure `ssh_job` tools with this shape:

```json
{
  "type": "ssh_job",
  "host": "host.docker.internal",
  "port": 22,
  "username": "root",
  "auth_type": "password",
  "password_ref": "k100_model_test",
  "runner_mode": "docker_exec",
  "container_name": "model_test",
  "remote_base_dir": "/tmp/sciminer-platform-tasks",
  "container_work_dir": "/workspace",
  "entrypoint": "/workspace/<model>/platform_run.sh"
}
```

If SSH to `host.docker.internal` is blocked by host policy, use the K100 host IP
or a dedicated model execution host instead. The worker only needs the matching
`SSH_PASSWORD_REF_<PASSWORD_REF>` or `SSH_AUTH_REF_<AUTH_REF>` environment value.

## 6. Acceptance Checklist

- Frontend loads from `http://<k100-host-ip>:8585`.
- Backend health endpoint returns a structured system health response.
- Alembic migration reaches `head` without errors.
- Login, project creation, and file upload work.
- A CPU-smoke model task can be submitted from the UI.
- Task center shows status, remote log/progress, and final Artifact output.
- Workflow can reference CPU-compatible tools without depending on DCU acceleration.

## 7. Cleanup

Stop the platform without deleting data:

```bash
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml down
```

Delete test volumes only when the test data can be discarded:

```bash
docker compose --env-file .env.k100-test -f docker-compose.k100-test.yml down -v
```

