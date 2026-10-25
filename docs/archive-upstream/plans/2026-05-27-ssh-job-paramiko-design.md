# SSH Job Paramiko Migration Design

**背景**

当前 `ssh_job` 执行器通过 `subprocess + ssh/scp/sshpass` 调宿主机，再 `docker exec` 进入远端模型容器。这个方案短期能跑，但运行时依赖多、认证方式分散、错误处理粗糙，不适合作为课题组内部长期集成方案。

**目标**

- 保留现有 `ssh_job` 配置结构与管理页面字段
- 底层切换为 `paramiko + SFTP`
- 同时保留 `auth_ref` 私钥认证与 `password_ref` 密码认证
- 不再依赖 `ssh/scp/sshpass`

**非目标**

- 第一版不做远端进程级精准杀任务
- 不改 `platform_run.sh` 协议
- 不引入第二套 `ssh_job` 配置格式

## 方案

### 1. 传输层拆分

新增 `backend/app/tasks/ssh_transport.py`，封装：

- SSH 建连
- host key 策略
- SFTP 上传/下载/递归建目录
- 远端命令执行
- 资源关闭

这一层只关心“怎么连、怎么传、怎么执行”，不关心平台任务模型和文件入库。

### 2. 执行器职责保持稳定

`SSHJobExecutor` 继续负责：

- 准备本地输入包
- 解析认证引用
- 组装 `platform_run.sh` 命令
- 解析 `output/result.json`
- 回收 `artifacts` 到平台文件表

变化点是：远端操作统一委托给 transport 层，而不是直接跑本地 shell 命令。

### 3. 认证兼容

保留现有配置字段：

- `auth_type=key` 对应 `auth_ref`
- `auth_type=password` 对应 `password_ref`

保留现有环境变量解析规则：

- `SSH_AUTH_REF_*` / `SSH_AUTH_REF_DIR`
- `SSH_PASSWORD_REF_*` / `SSH_PASSWORD_REF_DIR`
- `SSH_KNOWN_HOSTS_*` / `SSH_KNOWN_HOSTS`

所以迁移后，管理页面和导入配置都不用重做。

### 4. 线程模型

`paramiko` 是阻塞库。为了不阻塞 FastAPI 或 direct 模式的事件循环，transport 层的完整远端工作流将包在 `asyncio.to_thread(...)` 中执行。

这样：

- 不需要把现有执行器改成同步
- 不会阻塞 direct 模式下的后端异步任务
- 也不会影响 Celery 模式复用相同执行器

### 5. 错误语义

保持现有 `TaskExecutionError` 对外语义：

- 认证失败
- 连接失败
- 上传失败
- 远端命令返回非零
- 缺 `output/result.json`
- `result.json` 非法
- 下载失败

这些都会在 transport/执行器边界处转成平台已有错误结构。

## 取消策略

第一版不实现远端真正 kill。

direct / celery 取消任务只保证：

- 平台侧状态更新为 `CANCELED`
- 本地不再继续等待或处理后续步骤

若远端任务已经启动，它可能仍在远端宿主机或容器里继续运行。这是当前版本可接受的边界，后续若需要可再补 PID 文件或远端 kill 协议。

## 测试策略

### 单元测试

- 认证解析：`auth_ref` / `password_ref`
- host key 配置
- `docker_exec` / `shell` 命令拼装
- SFTP 上传下载与目录创建
- 失败分支：认证失败、返回码非零、缺失 `result.json`

### 集成测试

第一版不依赖真实远端主机。通过 monkeypatch 或 fake `paramiko.SSHClient` / fake `SFTPClient` 验证平台侧流程。

## 落地影响

- `backend/requirements.txt` 增加 `paramiko`
- `backend/Dockerfile` 后续不再需要 `sshpass`
- `ssh_job` 导入配置与管理页面无需改字段结构

