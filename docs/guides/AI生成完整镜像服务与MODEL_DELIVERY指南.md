# AI 生成完整镜像服务与 MODEL_DELIVERY 指南

**版本**: v1.0  
**最后更新**: 2026-05-26  
**适用对象**: 平台管理员、课题组内部模型接入维护人员

---

## 1. 目标

本指南专门解决两个问题：

1. 当手头只有模型代码时，如何让 Codex / Claude Code 直接帮你补出 `MODEL_DELIVERY.md`
2. 如何让 AI 直接生成一个**可直接构建完整镜像**的 `remote_api` 服务，而不是只生成一个依赖宿主机挂载的 FastAPI 壳子

这份指南默认你在本仓库内工作，并且最终要把新工具接入当前平台。

---

## 2. 推荐顺序

建议固定按下面顺序操作：

```text
拿到模型代码目录
  ->
让 AI 自动补一版 MODEL_DELIVERY.md
  ->
人工快速检查和修正明显错误
  ->
让 AI 基于 MODEL_DELIVERY.md + 代码目录生成完整镜像服务
  ->
本地验证
  ->
导入平台
```

不要跳过 `MODEL_DELIVERY.md` 这一步。

原因：

- 它能逼 AI 先把模型入口、依赖、输入输出、示例数据整理清楚
- 后面生成服务时，AI 更不容易乱猜
- 后续毕业同学离组后，管理员还能靠这份文档继续维护

---

## 3. 现成参考物

仓库里已经有两套现成参考物：

- 通用交付模板：[MODEL_DELIVERY.template.md](/data/zhouyc/cpumodel_sciminer/docs/guides/MODEL_DELIVERY.template.md)
- 可直接构建完整镜像的示例服务：[targetdiff-pocket-generation-service](/data/zhouyc/cpumodel_sciminer/example/targetdiff-pocket-generation-service)

其中第二个目录已经不是单纯模板，而是一个“完整镜像版本”的参考实现，包含：

- `app/`
- `Dockerfile`
- `environment.targetdiff-service.yml`
- `bundle_targetdiff_runtime.py`
- `vendor/targetdiff-main/`
- `platform_tool.json`
- `tests/`

如果你要让 AI 生成新的**完整镜像服务**，优先要求 AI 参考这个目录的结构，而不是只参考 `remote-api-tool-template`。

---

## 4. 场景 A：让 AI 自动写 MODEL_DELIVERY.md

### 4.1 适用场景

你已经拿到了模型代码目录，但目录里：

- 没有 `MODEL_DELIVERY.md`
- 或者有说明，但不完整
- 或者说明太散，AI 很难稳定接入

### 4.2 操作目标

让 AI 在模型代码目录中直接生成：

- `MODEL_DELIVERY.md`

并尽量从代码、README、配置文件、示例数据中自动提取：

- 模型用途
- 运行环境
- 主入口
- 输入输出
- 示例数据路径
- 资源需求
- 已知限制

### 4.3 给 AI 的标准提示词

把下面这段直接发给 Codex / Claude Code，并替换真实路径：

```text
请读取以下目录中的所有关键信息，并直接在模型目录下生成一份完整的 MODEL_DELIVERY.md：

- 模型代码目录：<MODEL_CODE_DIR>
- 重点阅读：README.md、requirements.txt、environment.yml、configs/、scripts/、examples/、weights/、checkpoints/

要求：
1. 参考 /data/zhouyc/cpumodel_sciminer/docs/guides/MODEL_DELIVERY.template.md 的结构和字段。
2. 不要只写“见代码”，要把管理员和后续 AI 接入需要的信息直接整理到文档中。
3. 尽量从代码中推断主入口文件、主入口命令、输入文件格式、输出文件格式、依赖和 GPU 要求。
4. 如果某些信息无法确认，不要编造，请明确写“待确认”，并在文档末尾列出“需要管理员确认的项”。
5. 如果项目包含多个任务，只先整理最适合作为第一版平台工具的那一条能力，并在文档中写清楚为什么选择它。
6. 生成结果文件路径固定为：<MODEL_CODE_DIR>/MODEL_DELIVERY.md
```

### 4.4 AI 输出后你要检查什么

最少检查这几项：

- 主入口文件是否真实存在
- 示例命令是否能对上代码结构
- 输入字段和文件格式是否写对
- 输出产物是否写对
- 是否把“多个任务”误写成一个接口

如果只改少量字段，直接改 `MODEL_DELIVERY.md` 即可，不要急着让 AI 重写。

---

## 5. 场景 B：让 AI 生成可直接构建完整镜像的服务

### 5.1 适用场景

你已经有：

- 模型代码目录
- 一份可用的 `MODEL_DELIVERY.md`

你想让 AI 直接生成一个**完整镜像版本**服务，要求：

- `docker build` 后即可构建
- 不依赖宿主机额外挂载模型工程目录
- 能直接作为平台 `remote_api` 工具接入

### 5.2 目标输出

建议让 AI 输出到：

```text
example/<tool-slug>-service/
```

输出目录里至少应包含：

```text
<tool-slug>-service/
├── app/
├── tests/
├── vendor/
│   └── <runtime-bundle>/
├── bundle_<tool>_runtime.py
├── environment.<tool>.yml
├── Dockerfile
├── .dockerignore
├── README.md
├── platform_tool.json
├── smoke_test_payload.json
└── export_platform_tool.py
```

### 5.3 对 AI 的结构约束

你必须明确告诉 AI：

- 不要只生成 FastAPI 壳子
- 不要依赖宿主机挂载上游源码目录
- 要把模型运行所需的最小源码子集、checkpoint、配置一并纳入镜像上下文
- 要生成“bundle/sync 脚本”，方便以后重新同步上游代码

### 5.4 给 AI 的标准提示词

把下面这段直接发给 Codex / Claude Code，并替换路径：

```text
请基于当前仓库中的完整镜像示例服务：
/data/zhouyc/cpumodel_sciminer/example/targetdiff-pocket-generation-service

以及以下模型交付目录：
<MODEL_CODE_DIR>

读取以下文件和目录：
- <MODEL_CODE_DIR>/MODEL_DELIVERY.md
- <MODEL_CODE_DIR>/README.md
- <MODEL_CODE_DIR>/requirements.txt
- <MODEL_CODE_DIR>/environment.yml
- <MODEL_CODE_DIR>/configs/
- <MODEL_CODE_DIR>/scripts/
- <MODEL_CODE_DIR>/examples/
- <MODEL_CODE_DIR>/weights/
- <MODEL_CODE_DIR>/checkpoints/

请生成一个新的、可直接构建完整镜像的 FastAPI remote_api 服务，输出到：
<OUTPUT_SERVICE_DIR>

硬性要求：
1. 参考 targetdiff-pocket-generation-service 的目录结构，而不是只参考 remote-api-tool-template。
2. 新服务必须是“完整镜像版本”，不能依赖宿主机挂载模型源码目录。
3. 需要把运行所需的最小源码子集、必要配置和模型权重纳入服务目录中的 vendor/ 或等价目录。
4. 需要生成一个 bundle/sync 脚本，用于后续从原始模型目录重新同步运行时文件。
5. 需要生成完整 Dockerfile，使管理员可以直接在 <OUTPUT_SERVICE_DIR> 下执行 docker build。
6. 需要生成 conda/micromamba 环境文件，明确 Python、PyTorch、CUDA、PyG、RDKit 或其他关键依赖版本。
7. 必须保留统一接口：
   - GET /health
   - POST /predict
8. 如果平台需要回收输出文件，必须提供可下载的 artifacts 路由。
9. 必须生成 platform_tool.json，并确保 input_schema/output_schema 位于 tool_config 内部。
10. 必须补测试，至少覆盖：
   - /health
   - /predict 的请求响应结构
   - 打包脚本或 Dockerfile 的关键约束
11. 优先复用现有模型代码，不要为了包装服务而重写核心算法。
12. 如果原项目支持多个任务，只先接第一版最合适的一条能力，并在 README 中明确边界。

交付完成后，请继续执行以下验证：
1. pytest
2. python export_platform_tool.py
3. python -m compileall app export_platform_tool.py bundle_*.py
4. python /data/zhouyc/cpumodel_sciminer/create_tool.py --config <OUTPUT_SERVICE_DIR>/platform_tool.json --validate-only

如果某一步无法执行，请明确说明原因，不要假装成功。
```

---

## 6. 一步式提示词

如果你不想分两次对话，也可以直接把“补 MODEL_DELIVERY + 生成完整镜像服务”合成一步。

建议只在模型结构比较清晰时这样做。

```text
请读取 <MODEL_CODE_DIR> 中的代码、README、配置、依赖、示例和权重。

第一步：
先在 <MODEL_CODE_DIR>/MODEL_DELIVERY.md 生成一份完整的模型交付说明，格式参考：
/data/zhouyc/cpumodel_sciminer/docs/guides/MODEL_DELIVERY.template.md

第二步：
再基于：
/data/zhouyc/cpumodel_sciminer/example/targetdiff-pocket-generation-service

生成一个新的、可直接构建完整镜像的 FastAPI remote_api 服务，输出到：
<OUTPUT_SERVICE_DIR>

要求：
- 不依赖宿主机挂载模型源码目录
- 生成 vendor runtime bundle
- 生成 bundle/sync 脚本
- 生成完整 Dockerfile
- 生成环境文件
- 生成 platform_tool.json
- 生成 README、smoke_test_payload.json、tests
- 保持 /health、/predict、artifacts 接口约定

如果 MODEL_DELIVERY.md 中有不确定项，请先标注“待确认”，再继续生成服务，但 README 中必须同步提示这些不确定项的风险。
```

---

## 7. AI 输出后的验收清单

无论使用哪种提示词，最终至少检查以下内容。

### 7.1 文档层

- `MODEL_DELIVERY.md` 是否完整
- 是否明确写出了第一版只接入哪条能力
- README 是否写清了镜像构建和运行命令

### 7.2 代码层

- `app/schemas.py` 是否和真实输入输出一致
- `app/adapter.py` 是否优先复用了原始模型入口
- 是否有 bundle/sync 脚本
- `vendor/` 中是否包含实际运行所需文件

### 7.3 镜像层

- Dockerfile 是否真的复制了运行时 bundle
- 是否有完整环境文件，而不是只写 `pip install fastapi`
- 是否明确 Python / CUDA / PyTorch / 关键依赖版本

### 7.4 平台接入层

- `platform_tool.json` 是否是 `remote_api`
- `endpoint`、`method`、`timeout_sec` 是否合理
- `input_schema` / `output_schema` 是否位于 `tool_config` 内部

---

## 8. 本仓库内建议的标准操作

假设：

- 模型目录：`/path/to/model-code`
- 输出服务目录：`/data/zhouyc/cpumodel_sciminer/example/my-new-tool-service`

推荐顺序：

1. 先让 AI 生成 `/path/to/model-code/MODEL_DELIVERY.md`
2. 人工快速校对
3. 再让 AI 生成完整镜像服务目录
4. 在服务目录内执行：

```bash
pytest
python "export_platform_tool.py"
python -m compileall "app" "export_platform_tool.py"
```

5. 在仓库根目录执行：

```bash
python "create_tool.py" --config "example/my-new-tool-service/platform_tool.json" --validate-only
```

6. 如果环境有 Docker，再执行：

```bash
docker build -t "my-new-tool-service:0.1.0" "example/my-new-tool-service"
```

---

## 9. 适合直接复制的管理员说明

如果你只是想快速把需求发给 AI，可以直接复制下面这段：

```text
请先读取模型代码目录，自动补一份 MODEL_DELIVERY.md。
然后基于 /data/zhouyc/cpumodel_sciminer/example/targetdiff-pocket-generation-service 的结构，生成一个新的、可直接构建完整镜像的 FastAPI remote_api 服务。
不要只生成依赖宿主机挂载源码的壳子。
必须包含 vendor runtime bundle、bundle/sync 脚本、完整 Dockerfile、环境文件、platform_tool.json、README、smoke_test_payload.json 和测试。
最后请自动执行 pytest、export_platform_tool.py、compileall 和 create_tool.py --validate-only。
```

---

## 10. 什么时候不要一步到位

以下情况不建议直接让 AI 一步生成完整镜像：

- 原模型项目过大，任务很多，第一版能力边界不清
- 权重文件缺失
- 依赖环境高度混乱
- 没有任何示例输入输出
- 连主入口都不清楚

这时应该先让 AI 只做：

1. 代码入口梳理
2. `MODEL_DELIVERY.md` 草稿
3. 第一版能力选择建议

确认后再生成服务。

---

## 11. 相关文件

- [MODEL_DELIVERY.template.md](/data/zhouyc/cpumodel_sciminer/docs/guides/MODEL_DELIVERY.template.md)
- [模型交付与AI生成FastAPI服务指南.md](/data/zhouyc/cpumodel_sciminer/docs/guides/模型交付与AI生成FastAPI服务指南.md)
- [targetdiff-pocket-generation-service](/data/zhouyc/cpumodel_sciminer/example/targetdiff-pocket-generation-service)
