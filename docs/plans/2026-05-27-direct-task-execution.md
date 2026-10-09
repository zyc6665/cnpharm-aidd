# Direct Task Execution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在开发环境下让任务创建接口立即返回，并由当前 FastAPI 进程内的 `asyncio.create_task` 异步执行任务，不依赖 Celery Worker。

**Architecture:** 在配置层增加 `TASK_EXECUTION_BACKEND=direct|celery` 开关。接口层在 `direct` 模式下不再分发到 Celery，而是把任务交给进程内的 direct runner；direct runner 复用 `app.worker.tasks._execute_tool_task_impl`，并维护一个进程内注册表供取消任务与关闭应用时清理使用。

**Tech Stack:** FastAPI lifespan, asyncio, SQLAlchemy AsyncSession, 现有 TaskExecutor/worker 执行实现, pytest/httpx。

---

### Task 1: 锁定 direct 模式接口行为

**Files:**
- Create: `test/test_task_direct_execution.py`
- Reference: `backend/app/api/v1/tasks.py`

**Step 1: Write the failing test**

- `test_create_task_uses_direct_runner_when_enabled`
- `test_retry_task_uses_direct_runner_when_enabled`
- `test_cancel_task_cancels_registered_direct_task`

测试目标：
- `direct` 模式下创建任务时不调用 Celery 入队，而是调用 direct runner
- `direct` 模式下重试任务时同样走 direct runner
- `direct` 模式下取消任务时会调用 direct runner 取消注册中的 asyncio 任务

**Step 2: Run test to verify it fails**

Run: `pytest test/test_task_direct_execution.py -v`

Expected:
- 至少一个断言失败，说明当前接口层仍然只会走 Celery

### Task 2: 增加 direct 模式配置开关

**Files:**
- Modify: `backend/app/config.py`

**Step 1: Write minimal implementation**

- 增加 `TASK_EXECUTION_BACKEND: Literal["celery", "direct"] = "celery"`
- 增加辅助函数 `use_direct_task_execution()`

**Step 2: Run focused tests**

Run: `pytest test/test_task_direct_execution.py -v`

Expected:
- 仍然失败，但失败点推进到 direct runner 尚未实现

### Task 3: 实现进程内 direct runner

**Files:**
- Create: `backend/app/tasks/direct_runner.py`
- Modify: `backend/app/main.py`

**Step 1: Write minimal implementation**

- 创建 `DirectTaskRunner`
- 提供：
  - `schedule_task(task_id, tool_version_id)`
  - `cancel_task(task_id)`
  - `shutdown()`
- 内部维护 `task_id -> asyncio.Task` 注册表
- 复用 `app.worker.tasks._execute_tool_task_impl`
- 在 FastAPI `lifespan` 关闭时调用 `shutdown()`

**Step 2: Run focused tests**

Run: `pytest test/test_task_direct_execution.py -v`

Expected:
- direct runner 相关断言开始通过，接口层仍可能未接线

### Task 4: 接通任务接口到 direct runner

**Files:**
- Modify: `backend/app/api/v1/tasks.py`

**Step 1: Write minimal implementation**

- `create_task`:
  - `direct` 模式下不入 Celery
  - 提交事务后调用 `direct_task_runner.schedule_task(...)`
- `retry_task`:
  - `direct` 模式下同样直接调度
- `cancel_task`:
  - 若为 `direct` 模式，先尝试取消注册中的 asyncio 任务
  - Celery 模式保持原逻辑

**Step 2: Run focused tests**

Run: `pytest test/test_task_direct_execution.py -v`

Expected:
- direct 模式接口测试全部通过

### Task 5: 配置开发环境默认走 direct 模式

**Files:**
- Modify: `deploy/compose/docker-compose.dev.yml`

**Step 1: Write minimal implementation**

- 仅开发 `backend` 服务增加 `TASK_EXECUTION_BACKEND=direct`
- 不改生产或独立 Celery compose

**Step 2: Run regression tests**

Run:
- `pytest test/test_task_direct_execution.py test/test_tool_import_api.py test/test_admin_tool_permissions.py -v`
- `python3 -m compileall backend/app/api/v1/tasks.py backend/app/tasks/direct_runner.py backend/app/main.py backend/app/config.py`

Expected:
- 全部通过

### Task 6: 补充行为说明

**Files:**
- Optional Modify: `README.md` 或现有开发文档（仅在必要时）

**Step 1: Document**

- 说明开发模式下任务由当前后端进程直接执行
- 说明热重载/进程重启会中断运行中的 direct 任务

**Step 2: Final verification**

Run:
- `pytest test/test_task_direct_execution.py -v`
- 如有前端改动则补前端测试；本方案预计无需前端代码改动

Expected:
- 所有后端行为稳定，direct 模式可用于开发联调
