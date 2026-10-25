# SSH Job Paramiko Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `ssh_job` 执行器从 `ssh/scp/sshpass` 外部命令链迁移到 `paramiko + SFTP`，同时保留密码认证和私钥认证。

**Architecture:** 新增独立 `ssh_transport` 模块封装 SSH/SFTP 细节，`SSHJobExecutor` 继续保留平台级任务准备、命令拼装、结果回收职责。阻塞的远端传输工作流通过 `asyncio.to_thread(...)` 在后台线程执行。

**Tech Stack:** Python, Paramiko, asyncio, SQLAlchemy async, pytest。

---

### Task 1: 为 paramiko 迁移写失败测试

**Files:**
- Create: `test/test_ssh_transport.py`
- Modify: `test/test_ssh_job_support.py`

**Step 1: Write the failing test**

- transport 支持密码认证连接
- transport 支持私钥认证连接
- `SSHJobExecutor` 不再依赖 `sshpass` 命令拼装
- transport 在 `strict_host_key_checking=false` 时自动接受 host key

**Step 2: Run test to verify it fails**

Run: `pytest test/test_ssh_transport.py test/test_ssh_job_support.py -v`

Expected:
- 因为 transport 模块还不存在、测试或旧 sshpass 断言失败而变红

### Task 2: 新增 transport 模块

**Files:**
- Create: `backend/app/tasks/ssh_transport.py`

**Step 1: Write minimal implementation**

- `SSHCommandResult`
- `ParamikoSSHTransport`
  - `connect()`
  - `close()`
  - `ensure_dir()`
  - `upload_file()`
  - `upload_tree()`
  - `download_tree()`
  - `run_command()`
  - `remove_tree()`

**Step 2: Run focused tests**

Run: `pytest test/test_ssh_transport.py -v`

Expected:
- transport 层测试通过

### Task 3: 执行器切换到 transport

**Files:**
- Modify: `backend/app/tasks/executor.py`

**Step 1: Write minimal implementation**

- 删除对 `ssh/scp/sshpass` 命令链的依赖
- 保留认证解析和命令拼装逻辑
- 新增 `_run_remote_workflow()`，内部使用 `asyncio.to_thread(...)`
- 复用原有结果解析与文件回收逻辑

**Step 2: Run focused tests**

Run: `pytest test/test_ssh_job_support.py -v`

Expected:
- `ssh_job` 单元测试通过

### Task 4: 引入依赖并做回归

**Files:**
- Modify: `backend/requirements.txt`

**Step 1: Write minimal implementation**

- 增加 `paramiko`

**Step 2: Run regression tests**

Run:
- `pytest test/test_ssh_transport.py test/test_ssh_job_support.py test/test_tool_import_config.py test/test_task_direct_execution.py -v`
- `python3 -m compileall backend/app/tasks/executor.py backend/app/tasks/ssh_transport.py`

Expected:
- 所有相关测试通过

### Task 5: 清理运行时依赖说明

**Files:**
- Optional Modify: `backend/Dockerfile`
- Optional Modify: 文档

**Step 1: Adjust docs/runtime**

- 明确 `ssh_job` 迁移后不再依赖 `sshpass`
- 如果镜像已无用依赖，可移除 `sshpass`

**Step 2: Final verification**

Run:
- 所有相关后端测试

Expected:
- direct 模式与 ssh_job 模式可以共存，开发态不依赖 Celery 也可调用远端模型
