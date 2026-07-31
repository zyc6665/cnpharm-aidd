# Tool Package v1 编写指南

Tool Package 是平台工具扩展的稳定边界。一个包应描述科学语义、运行变体和
Artifact 契约，而不是携带集群地址、凭据或宿主机目录。

## 目录约定

- `tool.yaml`：包身份、版本、语义输入输出及变体索引。
- `schemas/`：参数、输入和输出的 JSON Schema Draft 2020-12 定义。
- `variants/`：CPU、NVIDIA CUDA、海光 DCU 的资源与执行声明。
- `runner/`：统一入口和结果解析器。
- `tests/`：契约测试、黄金样例测试和失败路径测试。
- `README.md`、`LICENSE`：运行说明与代码、模型、数据授权边界。

## 最小编写流程

1. 从 `example/tool-package-template` 复制目录并修改 `metadata.slug`、名称和版本。
2. 先定义输入输出的 `semantic_type` 与 `artifact_type`，再编写 JSON Schema。
3. 实现 runner，并确保只读取平台下发的请求和 Artifact URI，只写任务输出目录。
4. 为每种变体声明执行类型、镜像、入口、资源、设备和最低驱动版本。
5. 用固定公开样例记录来源、许可证、SHA-256、预处理规则和数值容差。
6. 在真实硬件运行黄金样例后才能将状态标记为 `validated`。

NVIDIA 变体必须声明设备和驱动要求。没有海光 DCU 真机时只能使用
`adapted_pending_hardware_validation`，不得将代码适配等同于硬件验证。

## AI 辅助打包

Codex 或 Claude Code 应首先读取包内 `AGENTS.md`。智能体可以生成 manifest、
Schema、runner 与测试，但不得修改平台契约版本，不得写入明文凭据、私网地址或
绝对宿主路径，也不得凭推断宣称硬件兼容。人工评审仍需核对科学方法、许可证、
镜像来源和黄金样例证据。

## 验证

从 `backend/` 执行生产校验器：

```bash
python -m app.tool_packages.validator ../example/tool-package-template
```

从仓库根目录执行模板和包内测试：

```bash
pytest test/test_tool_package_template.py \
  example/tool-package-template/tests/test_contract.py -q
```

发布前还必须经过平台签名、审核和镜像供应链检查；本地校验通过不代表可直接发布。
