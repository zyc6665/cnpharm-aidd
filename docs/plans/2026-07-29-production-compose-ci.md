# Production Compose CI Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 GitHub Actions 中验证生产 Compose 配置并构建后端生产镜像。

**Architecture:** 新增独立 `production-compose` job，使用非敏感占位变量运行 Compose 配置解析和后端服务构建。保留 pytest 静态结构测试作为本地快速门禁，不在 CI 中启动整套服务。

**Tech Stack:** GitHub Actions、Docker Compose v2、Docker BuildKit、pytest、PyYAML

---

### Task 1: 锁定 CI 验证契约

**Files:**
- Modify: `test/test_production_compose.py`

**Steps:**
1. 添加测试，读取 `.github/workflows/ci.yml` 并断言 `production-compose` job 存在。
2. 断言 job 包含 `docker compose ... config --quiet` 和 `docker compose ... build backend`。
3. 断言 job 提供 Compose 必填变量的非空占位值。
4. 运行 `pytest test/test_production_compose.py -q`，确认测试因 job 缺失失败。

### Task 2: 添加生产 Compose CI job

**Files:**
- Modify: `.github/workflows/ci.yml`
- Test: `test/test_production_compose.py`

**Steps:**
1. 新增 `production-compose` job 和 CI 专用占位环境变量。
2. 添加 checkout、Compose 配置校验和后端生产镜像构建步骤。
3. 运行 `pytest test/test_production_compose.py test/test_deployment_hardening.py test/test_dependency_profiles.py -q`。
4. 运行 YAML 解析检查与 `git diff --check`。
5. 提交 `ci: validate production compose build`。

### Task 3: 完整回归验证

**Files:**
- Verify: `.github/workflows/ci.yml`
- Verify: `deploy/compose/docker-compose.prod.yml`
- Verify: `backend/Dockerfile`

**Steps:**
1. 运行 `pytest test`。
2. 运行 `npm run test -- --run`。
3. 运行 `npm run build`。
4. 确认工作区只保留既有本地未跟踪文件。
