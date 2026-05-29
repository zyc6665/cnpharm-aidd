# SSH 作业执行器集成方案

## 1. 概述

### 1.1 背景

当前平台已经支持三种工具执行方式：

1. `remote_api`
2. `docker_image`
3. `python_script`

这三种方式覆盖了大部分“平台统一部署”的场景，但对课题组内部模型集成仍有一个明显痛点：

- 很多模型已经在各自服务器上由同学单独部署
- 这些模型常常已经有自己的容器、conda 环境和运行脚本
- 管理员为了接入平台，还要额外再封装一层 FastAPI 或重新打包镜像

这会带来重复部署、环境漂移和维护成本上升的问题。

### 1.2 目标

设计并实现第四种执行方式：

- `ssh_job`

使平台可以通过 SSH 连接到远端服务器，上传输入文件、调用统一的 `platform_run.sh`、拉回输出结果，从而直接复用远端已有模型容器或运行环境。

### 1.3 非目标

本方案**不**打算支持：

- 任意用户提交任意 SSH 命令
- 在平台配置中明文保存 SSH 私钥
- 平台直接接管远端容器生命周期编排
- 第一期就支持复杂分布式调度和实时流式日志

### 1.4 设计原则

- **最小侵入**：尽量复用现有任务执行器、文件管理和任务状态机
- **安全优先**：只允许管理员配置固定远端主机、固定入口脚本、固定目录
- **协议统一**：远端统一通过 `platform_run.sh` 暴露能力
- **向后兼容**：不影响现有 `remote_api` / `docker_image` / `python_script`
- **易扩展**：后续可扩展到更多远端执行模式

### 1.5 与现有架构的集成点

| 组件 | 文件位置 | 集成方式 |
|------|----------|----------|
| 工具类型枚举 | `backend/app/models/tools.py` | 新增 `ssh_job` |
| 工具配置校验 | `tool_import_config.py` / schema validator | 增加 `ssh_job` 配置规则 |
| 执行器工厂 | `backend/app/tasks/executor.py` | 新增 `SSHJobExecutor` |
| 文件存储 | `backend/app/models/files.py` 等 | 复用输入下载与输出入库 |
| 任务状态机 | `backend/app/tasks/state_machine.py` | 复用现有状态流转 |
| 管理后台 | 工具创建/导入页面 | 后续增加 `ssh_job` 表单项 |

---

## 2. 整体架构

### 2.1 核心流程

```text
用户创建任务
  ->
Celery Worker 取到任务
  ->
SSHJobExecutor 准备本地任务目录
  ->
下载平台输入文件
  ->
生成 params.json
  ->
SFTP 上传到远端任务目录
  ->
SSH 执行 platform_run.sh
  ->
远端写出 result.json / logs / artifacts
  ->
平台通过 SFTP 拉回输出
  ->
结果文件入库
  ->
更新任务状态
```

### 2.2 远端角色划分

平台不直接理解每个模型的内部实现，而是只要求远端提供统一入口：

- `platform_run.sh`

这个脚本负责：

- 接收平台标准参数
- 映射到模型原始命令
- 执行模型推理/生成任务
- 在固定输出目录中产出 `result.json`、日志和结果文件

### 2.3 远端执行模式

推荐将 `ssh_job` 分为以下模式：

1. `docker_exec`
   - 平台 SSH 到远端主机后，通过 `docker exec` 进入已有容器执行 `platform_run.sh`
   - 这是本课题组最推荐的模式

2. `shell`
   - 平台 SSH 到远端主机后，直接在宿主机 shell 或 conda 环境中执行 `platform_run.sh`
   - 适合未容器化但环境相对稳定的工具

3. `docker_run`
   - 预留扩展模式
   - 第一阶段不强制实现

第一阶段建议优先支持：

- `docker_exec`
- `shell`

---

## 3. 工具配置设计

### 3.1 配置结构

在 `tool_versions.config` JSON 字段中新增 `ssh_job` 类型：

```json
{
  "type": "ssh_job",
  "host": "gpu-node-01.example.internal",
  "port": 22,
  "username": "platform_runner",
  "auth_ref": "ssh_gpu_node_01",
  "runner_mode": "docker_exec",
  "remote_base_dir": "/srv/platform-jobs",
  "entrypoint": "/app/platform_run.sh",
  "container_name": "targetdiff-prod",
  "work_dir_name": "work",
  "input_dir_name": "input",
  "output_dir_name": "output",
  "env": {
    "CUDA_VISIBLE_DEVICES": "0"
  },
  "timeout_sec": 3600,
  "cleanup_remote": true,
  "strict_host_key_checking": true,
  "output_globs": [
    "output/result.json",
    "output/logs/run.log",
    "output/artifacts/**/*"
  ],
  "input_schema": {},
  "output_schema": {}
}
```

### 3.2 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `type` | 是 | 固定为 `ssh_job` |
| `host` | 是 | 远端服务器地址 |
| `port` | 否 | SSH 端口，默认 `22` |
| `username` | 是 | SSH 用户名 |
| `auth_ref` | 是 | 凭据引用名，不直接保存私钥 |
| `runner_mode` | 是 | `docker_exec` 或 `shell` |
| `remote_base_dir` | 是 | 平台任务在远端的根目录 |
| `entrypoint` | 是 | 远端统一入口脚本路径 |
| `container_name` | 条件必填 | `docker_exec` 模式下必填 |
| `work_dir_name` | 否 | 默认 `work` |
| `input_dir_name` | 否 | 默认 `input` |
| `output_dir_name` | 否 | 默认 `output` |
| `env` | 否 | 额外环境变量 |
| `timeout_sec` | 否 | 执行超时时间 |
| `cleanup_remote` | 否 | 完成后是否清理远端任务目录 |
| `strict_host_key_checking` | 否 | 是否严格校验主机指纹 |
| `output_globs` | 否 | 要拉回的平台输出文件模式 |

### 3.3 凭据管理

`auth_ref` 只做**引用**，不在工具配置中保存实际密钥。

推荐凭据来源：

1. 平台部署环境变量
2. 独立密钥文件目录
3. 后续可扩展为数据库中的加密凭据表

第一阶段建议使用：

- 平台管理员在 Worker 节点预置 SSH 私钥
- `auth_ref` 映射到固定私钥路径和 known_hosts 策略

例如：

```text
auth_ref = ssh_gpu_node_01
-> /etc/sciminer/ssh/ssh_gpu_node_01
```

### 3.4 配置校验规则

工具配置校验至少应包含：

1. `type == ssh_job`
2. `host` / `username` / `auth_ref` / `remote_base_dir` / `entrypoint` 非空
3. `runner_mode in {docker_exec, shell}`
4. `docker_exec` 模式必须提供 `container_name`
5. `timeout_sec` 必须为正整数
6. `output_globs` 只能读取 `output/` 子目录，禁止越界路径

---

## 4. 远端协议设计

### 4.1 远端任务目录

平台每次执行任务时，在远端构造统一目录：

```text
<remote_base_dir>/<task_id>/
├── input/
├── output/
├── work/
└── params.json
```

例如：

```text
/srv/platform-jobs/0d80f9b6-xxxx-xxxx-xxxx-xxxxxxxxxxxx/
```

### 4.2 `platform_run.sh` 调用协议

平台统一调用：

```bash
bash "/app/platform_run.sh" \
  --task-id "<task_id>" \
  --input-dir "<remote_task_dir>/input" \
  --output-dir "<remote_task_dir>/output" \
  --params-json "<remote_task_dir>/params.json" \
  --work-dir "<remote_task_dir>/work"
```

可选：

```bash
--device "cuda:0"
```

### 4.3 `params.json` 协议

平台写出的 `params.json` 建议统一为：

```json
{
  "task_id": "uuid",
  "tool_slug": "targetdiff-pocket-generation",
  "task_name": "pocket_generation",
  "params": {
    "num_samples": 10,
    "batch_size": 5
  },
  "input_files": {
    "pocket_pdb": "input/pocket10.pdb"
  }
}
```

### 4.4 `result.json` 协议

远端脚本执行完成后，必须写出：

```json
{
  "success": true,
  "message": "Job completed",
  "outputs": {
    "num_generated": 10
  },
  "artifacts": [
    {
      "name": "sample_000.sdf",
      "path": "artifacts/sample_000.sdf",
      "content_type": "chemical/x-mdl-sdfile"
    }
  ],
  "metrics": {
    "duration_sec": 42.3
  }
}
```

失败时也应尽量产出：

```json
{
  "success": false,
  "message": "Job failed",
  "error": {
    "code": "MODEL_EXECUTION_FAILED",
    "details": "stderr or short traceback"
  }
}
```

### 4.5 输出目录约定

远端脚本必须输出：

```text
output/
├── result.json
├── logs/
│   └── run.log
└── artifacts/
```

平台只从 `output/` 下回收文件，不读取其他路径。

---

## 5. 平台执行器设计

### 5.1 新执行器类

新增：

- `SSHJobExecutor(BaseExecutor)`

主要职责：

1. 准备本地工作目录
2. 下载输入文件
3. 写本地 `params.json`
4. 建立 SSH/SFTP 连接
5. 创建远端任务目录
6. 上传输入与参数文件
7. 远程执行 `platform_run.sh`
8. 拉回 `result.json` 和 artifacts
9. 入库输出文件并返回标准结果

### 5.2 工厂扩展

在执行器工厂中增加：

```python
ToolType.SSH_JOB.value: SSHJobExecutor
"ssh_job": SSHJobExecutor
```

### 5.3 建议实现结构

建议在执行器内部拆成以下方法：

- `_prepare_local_inputs()`
- `_build_params_json()`
- `_connect_ssh()`
- `_ensure_remote_dirs()`
- `_upload_task_bundle()`
- `_build_remote_command()`
- `_execute_remote_command()`
- `_download_remote_outputs()`
- `_parse_result_json()`
- `_cleanup_remote_task_dir()`

### 5.4 远程命令生成

`docker_exec` 模式推荐命令形态：

```bash
docker exec <container_name> bash -lc '
  export CUDA_VISIBLE_DEVICES=0
  bash "/app/platform_run.sh" \
    --task-id "<task_id>" \
    --input-dir "<remote_task_dir>/input" \
    --output-dir "<remote_task_dir>/output" \
    --params-json "<remote_task_dir>/params.json" \
    --work-dir "<remote_task_dir>/work"
'
```

`shell` 模式推荐命令形态：

```bash
bash -lc '
  export CUDA_VISIBLE_DEVICES=0
  bash "<entrypoint>" \
    --task-id "<task_id>" \
    --input-dir "<remote_task_dir>/input" \
    --output-dir "<remote_task_dir>/output" \
    --params-json "<remote_task_dir>/params.json" \
    --work-dir "<remote_task_dir>/work"
'
```

### 5.5 结果回传

执行器应：

1. 下载 `output/result.json`
2. 解析其中的 `success`
3. 下载 `output/logs/run.log`
4. 下载 `output/artifacts/` 下的文件
5. 将文件入库并生成 `output_file_ids`

如果 `result.json.success == false`，应抛出 `TaskExecutionError`，而不是把任务当成功。

---

## 6. 安全设计

### 6.1 基本约束

必须遵守：

1. 只有管理员可以创建或修改 `ssh_job` 工具
2. 普通用户不能自定义远端主机、容器名和入口命令
3. 平台不接受前端透传任意 shell 片段
4. 平台不在数据库明文保存 SSH 私钥

### 6.2 主机校验

建议默认：

- `strict_host_key_checking = true`

并在 Worker 节点维护已知主机指纹。

如果为了过渡期允许关闭，也应：

- 仅对内网受控主机开放
- 在日志中明确标记风险

### 6.3 目录边界

平台只允许读写：

- `<remote_base_dir>/<task_id>/...`

不允许：

- 上传到任意系统目录
- 从 `output/` 之外抓文件
- 通过 `../` 路径穿越

### 6.4 命令边界

平台不允许自由拼接业务命令，只允许两种固定模板：

1. `docker exec <container_name> ... <entrypoint>`
2. `bash <entrypoint> ...`

`entrypoint` 必须是管理员预先配置的固定脚本路径。

### 6.5 审计日志

建议记录：

- 远端主机
- SSH 用户
- 执行模式
- 远端任务目录
- 开始/结束时间
- 返回码
- 远端日志文件路径

---

## 7. 错误处理

### 7.1 错误分类

建议至少区分：

1. `SSH_CONNECT_FAILED`
2. `SSH_AUTH_FAILED`
3. `REMOTE_DIR_CREATE_FAILED`
4. `INPUT_UPLOAD_FAILED`
5. `REMOTE_COMMAND_FAILED`
6. `RESULT_JSON_MISSING`
7. `RESULT_JSON_INVALID`
8. `ARTIFACT_DOWNLOAD_FAILED`

### 7.2 超时处理

`timeout_sec` 到期后：

1. 平台终止 SSH 会话
2. 任务状态标记为失败
3. 尽量拉回已存在的 `run.log`
4. 是否进一步清理远端目录由 `cleanup_remote` 决定

### 7.3 幂等与重试

第一阶段建议：

- **任务执行本身不自动重试**
- 因为科学计算任务通常代价较大，自动重试可能造成重复耗时和资源浪费

但可以考虑对以下细分步骤做有限重试：

- SSH 建连
- 文件上传
- 文件下载

---

## 8. 分阶段实施建议

### 8.1 第一阶段

目标：跑通最小闭环

范围：

1. 增加 `ssh_job` 类型
2. 增加 `SSHJobExecutor`
3. 支持 `docker_exec` / `shell`
4. 支持上传输入文件、拉回结果文件
5. 使用 `auth_ref -> 本地私钥文件` 映射
6. 仅管理员可配置

### 8.2 第二阶段

目标：提高可维护性

范围：

1. 管理后台增加 `ssh_job` 表单
2. 导入配置支持 `ssh_job`
3. 增加远端连通性测试
4. 增加 `result.json` 协议校验
5. 增加主机指纹管理

### 8.3 第三阶段

目标：增强运维能力

范围：

1. 执行中日志抓取
2. 任务取消与远端清理
3. 加密凭据存储
4. 远端执行审计报表

---

## 9. 对现有指南的关系

本方案与以下两份文档配套：

1. [AI生成统一platform_run.sh指南.md](/data/zhouyc/cpumodel_sciminer/docs/guides/AI生成统一platform_run.sh指南.md)
   - 负责模型侧统一入口脚本生成

2. [模型交付与AI生成FastAPI服务指南.md](/data/zhouyc/cpumodel_sciminer/docs/guides/模型交付与AI生成FastAPI服务指南.md)
   - 负责 `remote_api` 路线

两条路线不是互斥关系：

- 外部共享服务、规范化程度高的工具，适合 `remote_api`
- 课题组内部已有容器、已有运行环境的工具，适合 `ssh_job`

---

## 10. 推荐结论

对当前课题组内部平台，浮浮酱建议：

1. 保留现有三种执行方式
2. 新增第四种 `ssh_job`
3. 课题组内部现成模型优先走 `ssh_job`
4. 对外部规范服务或长期公共服务继续走 `remote_api`

这样可以在不牺牲平台统一调度能力的前提下，大幅降低管理员反复封装和重复部署的成本。

