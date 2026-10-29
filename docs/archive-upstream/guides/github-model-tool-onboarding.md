# 从 GitHub 模型到平台工具

本文说明如何把一个 GitHub 上下载的模型接入 SciMiner，并让管理员在平台中发布为可运行工具。

## 先选择接入方式

| 模型现状 | 推荐路径 |
| --- | --- |
| 已经部署成 HTTP 服务，并提供 `/.well-known/sciminer-tool.json` | 工具管理 → 新增工具 → 远程服务自发现 |
| 本地 Python/GPU 模型，需要平台调度输入、输出和资源 | Tool Package v2 |
| 临时验证一个简单脚本 | 高级工具配置，验证后迁移到 Tool Package v2 |

Tool Package v2 是模型交付格式，不是执行器。平台仍然使用 SSH、Docker、K8s 或 Slurm 执行模型。

## 模型侧准备

1. 阅读 GitHub 项目的许可证、依赖、权重下载方式和输入输出格式。
2. 编写 adapter，把平台标准 Artifact 转成原模型输入，并把原模型输出整理成平台标准 Artifact。
3. 提供 `platform_run.sh`，接受平台通用参数：

   ```bash
   --task-id --input-dir --output-dir --params-json --work-dir --device
   ```

4. 在输出目录生成 `result.json`，内容使用 `aidd.sciminer/result`。
5. 为输入发现、参数解析、模型调用和结果格式编写合同测试。

可参考 `example/pocket2mol/tool-package-v2/`、`example/MolP-PC/tool-package-v2/` 和 `docs/guides/model-runtime-packaging.md`。

## 运行环境准备

生产环境推荐不可变容器：

```bash
docker build -t registry.example.com/my-model:1.0.0 .
docker push registry.example.com/my-model:1.0.0
docker inspect --format '{{index .RepoDigests 0}}' registry.example.com/my-model:1.0.0
```

同时准备：

- 容器镜像 digest；
- 权重清单 URI 和 SHA256；
- conda-pack 或 venv-pack fallback 的 URI 和 SHA256；
- 已验证的 CPU/GPU/DCU 变体及资源需求。

平台不会在任务执行时安装依赖，也不会使用宿主机上的临时 conda 环境替代已验证 Runtime Env。

## Tool Package v2 内容

`tool.yaml` 至少声明：

- `metadata`：slug、名称、版本；
- `artifacts.inputs/outputs`：平台标准 Artifact 槽；
- `parameters_schema`：业务参数；
- `adapter`：输入输出转换方法和校验器；
- `runtime`：Python、容器、fallback、权重和缓存策略；
- `variants`：CPU、CUDA、DCU 的执行入口和资源。

标准 Artifact 类型必须使用平台注册表中的版本化类型，例如 `protein_structure@1`、`binding_pocket@1`、`molecule_table@1` 和 `run_report@1`。

本地校验：

```bash
cd backend
python -m app.tool_packages.validator ../path/to/tool-package-v2
```

## 管理员上线流程

1. 打开“管理员 → 工具 → 新增工具”。
2. 选择“Tool Package v2”。
3. 在“管理员 → Tool Packages”中使用“向导生成”或“粘贴 JSON”注册 manifest。
4. 填写真实镜像 digest、权重清单、fallback 包和签名。
5. 打开 Package 详情，点击“创建平台工具”。
6. 平台会自动带入名称、slug、版本和 manifest；管理员只需选择分类并补充执行器连接信息。
7. 对 SSH 执行器填写主机、账号、凭据引用、远端目录和入口脚本；凭据只填写 `auth_ref/password_ref`，不要把密钥写进 manifest。
8. 保存后，manifest 会写入新 `ToolVersion.config.tool_package_manifest`，同时保留实际执行器配置。
9. 在工具管理页检查契约校验、资源画像和 smoke test，确认成功后发布平台 Tool。

## 发布前检查

- Tool Package 版本校验状态为 `valid`；
- manifest 已签名；
- ToolVersion 的实际 executor 配置完整；
- 输入 Artifact 能通过 readiness 校验；
- 输出 `result.v2` 能生成标准 Artifact；
- 对应硬件完成 golden smoke 后，才把 variant 标记为已验证。

没有真实权重或目标硬件时，只能发布为草稿或 `adapted_pending_hardware_validation`，不能宣称生产硬件已支持。
