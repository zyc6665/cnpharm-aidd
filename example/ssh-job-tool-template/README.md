# SSH Job Tool Template

这个目录提供一个最小可用的 `ssh_job` 工具导入模板。

适用场景：

- 模型已经部署在课题组自己的服务器上
- 远端已经有现成容器或 conda 环境
- 不想再额外封装 FastAPI 服务

## 文件说明

- `platform_tool.json`
  - 可直接用于平台导入
  - 需要按真实服务器、容器名、入口脚本和 schema 修改

## 导入前需要替换的关键字段

至少替换这些值：

- `tool_config.host`
- `tool_config.username`
- `tool_config.auth_ref`
- `tool_config.remote_base_dir`
- `tool_config.entrypoint`
- `tool_config.runner_mode`
- `tool_config.container_name`
- `tool_config.container_base_dir`
- `tool_config.input_schema`
- `tool_config.output_schema`

如果工具不是容器内运行，而是直接在宿主机 shell 中运行：

- 把 `runner_mode` 改成 `shell`
- 删除 `container_name`
- 可以删除 `container_base_dir`

## Worker 节点要求

平台 Worker 节点需要满足：

- 已安装 `ssh` 和 `scp`
- 已预置与 `auth_ref` 对应的私钥
- 可通过环境变量或目录映射找到该密钥

推荐方式：

```text
SSH_AUTH_REF_DIR=/etc/sciminer/ssh
```

例如：

```text
auth_ref = ssh_gpu_node_01
-> /etc/sciminer/ssh/ssh_gpu_node_01
```

## 远端要求

远端服务器或容器内需要提供统一入口：

- `platform_run.sh`

建议优先阅读：

- [AI生成统一platform_run.sh指南.md](/data/zhouyc/cpumodel_sciminer/docs/guides/AI生成统一platform_run.sh指南.md)
- [09-SSH作业执行器集成方案.md](/data/zhouyc/cpumodel_sciminer/docs/design/09-SSH作业执行器集成方案.md)

## 校验命令

在仓库根目录执行：

```bash
python "create_tool.py" --config "example/ssh-job-tool-template/platform_tool.json" --validate-only
```

