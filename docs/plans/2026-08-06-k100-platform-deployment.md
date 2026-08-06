# K100 Platform Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Package the SciMiner platform as a Docker Compose based K100 test deployment while keeping model runtimes external and callable through the existing execution Interface.

**Architecture:** Backend and Celery worker share one production backend image. Frontend is built into a static nginx image that proxies `/api/` and WebSocket traffic to backend. Postgres, Redis, and MinIO remain separate Compose services; model execution stays outside the platform Compose stack and is reached through `ssh_job`.

**Tech Stack:** Docker Compose, FastAPI, Celery, PostgreSQL 16, Redis 7, MinIO, Vue/Vite, nginx, Alembic.

---

### Task 1: Add Frontend Production Image

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`

**Step 1: Add nginx config**

Create an nginx config that serves `/usr/share/nginx/html`, falls back to `index.html`, proxies `/api/` to `backend:8000`, and supports WebSocket upgrade headers.

**Step 2: Add multi-stage frontend Dockerfile**

Build with `node:22-alpine`, run `npm ci` and `npm run build`, then copy `dist` and `nginx.conf` into `nginx:1.27-alpine`.

**Step 3: Verify syntax**

Run: `docker run --rm -v "$PWD/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine nginx -t`

Expected: nginx config syntax is ok.

**Step 4: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf
git commit -m "build(frontend): add production nginx image"
```

### Task 2: Add K100 Compose Stack

**Files:**
- Create: `docker-compose.k100-test.yml`
- Create: `.env.k100-test.example`
- Create: `backend/alembic.ini`

**Step 1: Add backend-local Alembic config**

Create `backend/alembic.ini` with `script_location = %(here)s/alembic` so `alembic upgrade head` works inside the backend image.

**Step 2: Add K100 Compose file**

Include `postgres`, `redis`, `minio`, `backend`, `celery-worker`, and `frontend`. Use explicit health checks and `env_file: .env.k100-test`.

**Step 3: Add env example**

Document required secrets and K100-specific SSH variables without real values.

**Step 4: Verify Compose config**

Run: `docker compose --env-file .env.k100-test.example -f docker-compose.k100-test.yml config >/tmp/sciminer-k100-compose.yml`

Expected: Compose renders successfully.

**Step 5: Commit**

```bash
git add docker-compose.k100-test.yml .env.k100-test.example backend/alembic.ini
git commit -m "deploy: add k100 compose test stack"
```

### Task 3: Add Deployment Runbook

**Files:**
- Create: `docs/guides/k100-platform-deployment.md`

**Step 1: Document build and transfer flow**

Include `docker compose build`, `docker save`, transfer, `docker load`, and `docker compose up -d` commands.

**Step 2: Document migration and health checks**

Include `docker compose run --rm backend-migrate` or `docker compose exec backend alembic upgrade head`, backend health, frontend health, worker logs, and MinIO checks.

**Step 3: Document model execution setup**

Explain that model packages stay outside platform images and are called through `ssh_job`; document required password/key env vars.

**Step 4: Verify Markdown and references**

Run: `git diff --check -- docs/guides/k100-platform-deployment.md docker-compose.k100-test.yml .env.k100-test.example frontend/Dockerfile frontend/nginx.conf backend/alembic.ini`

Expected: no whitespace errors.

**Step 5: Commit**

```bash
git add docs/guides/k100-platform-deployment.md
git commit -m "docs: add k100 platform deployment runbook"
```

