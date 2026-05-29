# 模型交付与 AI 生成 FastAPI 服务指南

**版本**: v1.0  
**最后更新**: 2026-05-26  
**适用对象**: 平台管理员、课题组模型维护人员

---

## 1. 目标

本指南用于规范课题组内部模型工具的接入流程。

在本流程中：

- 毕业同学只负责提交模型代码、权重和说明文档
- 管理员使用 Codex、Claude Code 等 AI 工具读取交付文件
- AI 自动生成新的 FastAPI 服务、Dockerfile 和平台导入配置
- 管理员完成验收、部署和平台发布

本指南默认新工具以 `remote_api` 方式接入平台。

仓库内已提供两个可直接复用的实体文件：

- 学生交付模板：[MODEL_DELIVERY.template.md](/data/zhouyc/cpumodel_sciminer/docs/guides/MODEL_DELIVERY.template.md)
- 通用服务骨架目录：[remote-api-tool-template](/data/zhouyc/cpumodel_sciminer/example/remote-api-tool-template)

如果主人希望 AI 直接生成“可直接构建完整镜像”的版本，并且希望 AI 先自动补 `MODEL_DELIVERY.md`，请优先看：

- [AI生成完整镜像服务与MODEL_DELIVERY指南.md](/data/zhouyc/cpumodel_sciminer/docs/guides/AI生成完整镜像服务与MODEL_DELIVERY指南.md)

如果主人希望走“SSH 上传输入文件 -> 远端统一 `platform_run.sh` -> 拉回结果文件”的第四种接入路线，请优先看：

- [AI生成统一platform_run.sh指南.md](/data/zhouyc/cpumodel_sciminer/docs/guides/AI生成统一platform_run.sh指南.md)

---

## 2. 推荐流程

### 2.1 总流程

```text
学生提交模型代码
    ->
提交标准交付文件 MODEL_DELIVERY.md
    ->
管理员将代码目录 + 交付文件交给 AI
    ->
AI 生成 FastAPI 服务 + Dockerfile + platform_tool.json
    ->
管理员本地测试与容器化部署
    ->
导入平台并发布
```

### 2.2 角色分工

| 角色 | 职责 |
|------|------|
| 学生/毕业同学 | 提交模型代码、权重、依赖、样例输入输出、交付说明 |
| 管理员 | 审核交付物、驱动 AI 生成服务、部署容器、导入平台 |
| 平台 | 通过 `remote_api` 调用工具服务，统一展示和调度 |

---

## 3. 学生交付规范

学生不需要编写 FastAPI，不需要编写平台配置，但必须保证交付物完整。

### 3.1 必须提交的文件

建议每个工具交付目录结构如下：

```text
<tool_slug>/
├── MODEL_DELIVERY.md
├── README.md
├── requirements.txt
├── src/
│   └── ...
├── weights/
│   └── ...
├── examples/
│   ├── sample_input/
│   ├── sample_output/
│   └── expected_result.json
└── scripts/
    └── run_inference.py   # 可选，但强烈建议提供
```

### 3.2 必填信息

学生必须提供以下信息：

- 工具名称
- 工具唯一标识 `slug` 建议值
- 模型用途和输入输出说明
- 运行环境与依赖
- 推理入口
- 至少一组可复现的示例输入输出
- 资源需求说明
- 已知限制和失败场景

### 3.3 不合格交付物

以下情况不应直接进入 AI 生成阶段：

- 没有可运行入口
- 没有依赖文件
- 没有示例输入输出
- 没有说明输入字段含义
- 代码只能在个人绝对路径下运行
- 权重文件来源不明或缺失

---

## 4. MODEL_DELIVERY.md 模板

学生必须在交付目录中提供 `MODEL_DELIVERY.md`，建议使用以下模板。

仓库内可直接复制的模板文件见：

- [MODEL_DELIVERY.template.md](/data/zhouyc/cpumodel_sciminer/docs/guides/MODEL_DELIVERY.template.md)

```md
# 模型交付说明

## 1. 基本信息

- 工具名称：
- 建议 slug：
- 作者：
- 联系方式：
- 模型版本：
- 任务类型：分类 / 回归 / 生成 / 检测 / 分割 / 结构预测 / 其他

## 2. 模型用途

- 该模型解决的问题：
- 适用数据范围：
- 不适用场景：

## 3. 运行环境

- Python 版本：
- 主要依赖：
- 是否需要 GPU：
- 推荐显存：
- 推荐 CPU / 内存：
- 操作系统要求：

## 4. 推理入口

- 主入口文件：
- 主入口函数或命令：
- 最小执行示例：

## 5. 输入说明

- 输入类型：JSON参数 / 文件 / 文件+参数
- 输入字段列表：

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
|        |      |      |        |      |

- 输入文件格式说明：
- 输入文件大小限制：

## 6. 输出说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
|        |      |      |

- 是否产生输出文件：
- 输出文件类型：
- 成功返回示例：
- 失败返回示例：

## 7. 示例数据

- 示例输入路径：
- 示例输出路径：
- 期望结果说明：

## 8. 部署说明

- 模型文件路径约定：
- 是否需要预加载模型：
- 启动耗时：
- 单次推理平均耗时：

## 9. 已知问题

- 

## 10. 其他备注

- 
```

---

## 5. AI 生成服务的目标规范

管理员将交付目录交给 AI 后，AI 生成的新服务必须满足以下要求。

### 5.1 服务目标

AI 必须生成一个独立可部署的 FastAPI 服务，负责：

- 加载模型
- 校验输入
- 执行推理
- 返回标准 JSON 结果
- 暴露 OpenAPI 文档
- 支持容器化部署

如果管理员希望 AI 基于固定骨架改造，而不是从零生成，建议直接使用：

- [example/remote-api-tool-template](/data/zhouyc/cpumodel_sciminer/example/remote-api-tool-template)

### 5.2 必须生成的文件

建议 AI 输出如下目录：

```text
<tool_slug>-service/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── adapter.py
│   ├── schemas.py
│   ├── config.py
│   └── errors.py
├── tests/
│   └── test_api.py
├── Dockerfile
├── requirements.txt
├── README.md
├── platform_tool.json
└── smoke_test_payload.json
```

### 5.3 API 约定

默认只要求同步模式接口。

#### `GET /health`

用于健康检查。

推荐返回：

```json
{
  "status": "healthy",
  "service": "tool-slug-service",
  "version": "1.0.0"
}
```

#### `POST /predict`

平台侧 `remote_api` 默认推荐调用该接口。

请求体推荐格式：

```json
{
  "task_id": "uuid-or-string",
  "params": {
    "field_a": "value",
    "field_b": 123
  },
  "input_files": {
    "input_file_1": "http://.../download",
    "input_file_2": "http://.../download"
  }
}
```

说明：

- 若工具无文件输入，可省略 `input_files`
- `params` 中只放业务参数
- 文件字段统一放入 `input_files`

成功响应推荐格式：

```json
{
  "success": true,
  "task_id": "same-task-id",
  "result": {
    "prediction": "xxx",
    "score": 0.98
  },
  "output_files": [
    {
      "name": "result.csv",
      "url": "http://service-host/files/result.csv",
      "size": 12345,
      "content_type": "text/csv"
    }
  ],
  "error": null
}
```

失败响应推荐格式：

```json
{
  "success": false,
  "task_id": "same-task-id",
  "result": null,
  "output_files": [],
  "error": {
    "code": "INFERENCE_ERROR",
    "message": "error message"
  }
}
```

### 5.4 Schema 规范

AI 必须使用 Pydantic 定义输入输出模型，再由模型导出 OpenAPI Schema。

不要手写不受约束的 JSON 文本 Schema。

平台导入时使用的 `input_schema` 和 `output_schema` 应来自：

- `request_model.model_json_schema()`
- `response_model.model_json_schema()`

### 5.5 兼容当前平台的关键要求

当前仓库中的 `remote_api` 执行器有以下约束：

- 仅支持 `GET` 和 `POST`
- 默认应使用 `POST`
- `ToolVersion.config` 中必须包含 `type` 和 `endpoint`
- 平台导入配置中的 `input_schema` / `output_schema` 必须放在 `tool_config` 内部

因此 AI 生成的 `platform_tool.json` 必须符合本仓库导入脚本的实际结构。

---

## 6. platform_tool.json 规范

AI 在生成 FastAPI 服务时，必须同时生成一个 `platform_tool.json` 文件，供管理员导入平台。

### 6.1 正确结构

```json
{
  "name": "示例工具",
  "slug": "example-tool",
  "description": "示例工具描述",
  "icon": "🧪",
  "category": "bioinformatics",
  "version": "1.0.0",
  "changelog": "Initial version",
  "tool_config": {
    "type": "remote_api",
    "endpoint": "http://example-tool-service:8000/predict",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json"
    },
    "timeout_sec": 600,
    "input_schema": {
      "type": "object",
      "properties": {
        "params": {
          "type": "object"
        },
        "input_files": {
          "type": "object"
        }
      }
    },
    "output_schema": {
      "type": "object",
      "properties": {
        "success": {
          "type": "boolean"
        },
        "result": {
          "type": "object"
        },
        "output_files": {
          "type": "array"
        },
        "error": {
          "type": "object"
        }
      }
    }
  }
}
```

### 6.2 特别注意

不要生成以下错误结构：

- 将 `input_schema` 放在 `tool_config` 外层
- 将 `output_schema` 放在 `tool_config` 外层
- 将 `timeout` 写成 `timeout` 而不是 `timeout_sec`
- 让 `method` 使用 `PUT` 或 `DELETE`

---

## 7. 管理员给 AI 的标准提示词

以下提示词适用于 Codex、Claude Code 等代码代理工具。

管理员应在工具根目录执行，并让 AI 读取交付文件和代码目录。

### 7.1 标准提示词

```text
请阅读当前目录中的 MODEL_DELIVERY.md、README.md、requirements.txt、src/、weights/、examples/ 等交付文件。

目标：基于现有模型代码生成一个独立可部署的 FastAPI 服务，用于接入课题组内部 SciMiner 平台。新工具默认通过 remote_api 方式接入。

请严格遵守以下要求：

1. 生成一个新的服务目录 <tool_slug>-service/。
2. 服务必须包含：
   - app/main.py
   - app/adapter.py
   - app/schemas.py
   - Dockerfile
   - requirements.txt
   - README.md
   - smoke_test_payload.json
   - platform_tool.json
3. API 必须至少提供：
   - GET /health
   - POST /predict
4. POST /predict 请求体格式为：
   - task_id: string
   - params: object
   - input_files: object，可选
5. 响应格式必须为：
   - success: boolean
   - task_id: string
   - result: object | null
   - output_files: array
   - error: object | null
6. 输入输出 Schema 必须通过 Pydantic 定义生成，不要手写松散 JSON。
7. 同时生成 platform_tool.json，用于导入平台。
8. platform_tool.json 中必须把 input_schema 和 output_schema 放在 tool_config 内部。
9. endpoint 默认写为 http://<tool_slug>-service:8000/predict。
10. 优先复用学生提交的推理入口，不要重写核心算法逻辑。
11. 若学生代码缺少必要信息，请在 README.md 中列出待管理员补充项。
12. 生成后请给出本地启动命令、测试命令和导入平台的步骤。

请先分析现有代码结构，再开始生成文件。
```

### 7.2 如果需要 AI 额外生成平台导入命令

可以追加：

```text
另外请根据生成的 platform_tool.json，给出使用 create_tool.py 导入平台的示例命令。
```

---

## 8. 管理员验收清单

AI 生成完成后，管理员至少检查以下内容。

### 8.1 代码层面

- `adapter.py` 是否只是做输入转换和推理编排，没有改写核心模型逻辑
- `schemas.py` 是否覆盖了真实输入输出
- `main.py` 是否只暴露必要接口
- 是否有清晰的错误处理

### 8.2 运行层面

- `uvicorn` 能正常启动
- `/health` 可访问
- `/docs` 可访问
- `/predict` 能通过示例请求
- Docker 镜像可构建

### 8.3 平台接入层面

- `platform_tool.json` 可读
- `tool_config.type == remote_api`
- `endpoint` 正确
- `timeout_sec` 合理
- `input_schema` 在 `tool_config` 内
- `output_schema` 在 `tool_config` 内
- 示例请求与平台参数组织方式一致

---

## 9. 平台导入建议步骤

### 9.1 启动服务

先在本地或测试环境启动新服务，确认：

- `GET /health` 正常
- `POST /predict` 正常
- OpenAPI 文档正常

### 9.2 生成并核对平台配置

确认 `platform_tool.json` 中以下字段正确：

- `name`
- `slug`
- `version`
- `tool_config.endpoint`
- `tool_config.input_schema`
- `tool_config.output_schema`

建议先执行一次静态校验：

```bash
python "create_tool.py" --config "<tool_slug>-service/platform_tool.json" --validate-only
```

该命令会：

- 校验必填字段
- 校验 `tool_config.type`
- 校验 `remote_api` 方法是否为 `GET/POST`
- 校验 `input_schema` / `output_schema`
- 自动兼容部分旧字段，如 `timeout -> timeout_sec`

### 9.3 导入平台

可使用本仓库中的导入脚本：

```bash
python "create_tool.py" --config "<tool_slug>-service/platform_tool.json"
```

### 9.4 导入后验证

导入后至少验证：

- 工具详情页是否能渲染参数
- 参数默认值是否正确
- 文件字段是否按预期上传
- 任务是否能成功创建
- 结果是否能正确展示

---

## 10. 推荐的长期演进方向

当工具数量继续增长时，建议进一步收敛为：

1. 统一的 FastAPI 服务模板仓库
2. 统一的 `MODEL_DELIVERY.md` 模板
3. 统一的 `platform_tool.json` 生成器
4. 平台侧新增“读取远程 OpenAPI 自动导入工具”能力

这样管理员后续的工作会从“手工写服务”逐步变成“审核 AI 生成结果”，更适合课题组长期维护。
