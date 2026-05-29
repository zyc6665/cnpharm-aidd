# Remote API Tool Template

这是一个面向课题组内部平台的通用 FastAPI 工具服务模板。

目标：

- 管理员或 AI 基于学生提交的模型代码快速生成新服务
- 服务默认通过 `remote_api` 方式接入平台
- 尽量避免手写平台 `input_schema` / `output_schema`

## 1. 模板结构

```text
remote-api-tool-template/
├── app/
│   ├── adapter.py
│   ├── config.py
│   ├── errors.py
│   ├── main.py
│   └── schemas.py
├── Dockerfile
├── export_platform_tool.py
├── platform_tool.json
├── requirements.txt
└── smoke_test_payload.json
```

## 2. 应该优先修改的文件

### `app/schemas.py`

把占位的：

- `PredictionParams`
- `PredictionInputFiles`
- `PredictionResult`

替换为真实模型的输入输出结构。

### `app/adapter.py`

把占位的：

- `load_model()`
- `predict()`

替换为真实模型加载和推理逻辑。

## 3. 本地运行

```bash
pip install -r "requirements.txt"
uvicorn "app.main:app" --host 0.0.0.0 --port 8000 --reload
```

访问：

- `http://localhost:8000/health`
- `http://localhost:8000/docs`

## 4. 生成平台导入配置

如果修改过 `app/schemas.py`，建议重新导出平台配置：

```bash
python "export_platform_tool.py"
```

该命令会更新：

- `platform_tool.json`

## 5. 导入平台

在仓库根目录执行：

```bash
python "create_tool.py" --config "example/remote-api-tool-template/platform_tool.json"
```

## 6. AI 使用建议

管理员可以把该模板目录和学生提交的 `MODEL_DELIVERY.md` 一起交给 AI，并使用类似以下指令：

```text
请以当前模板目录为基础，不改变整体目录结构。
请读取学生提交的 MODEL_DELIVERY.md、代码目录、权重目录和示例数据。
请只修改与实际模型相关的 schema、adapter、README、requirements 和 platform_tool.json。
请保持 /health 和 /predict 的接口约定不变。
```

## 7. 平台兼容约束

本模板默认兼容当前仓库平台侧的 `remote_api` 接入方式：

- 使用 `POST /predict`
- 请求体包含 `task_id`
- 参数放在 `params`
- 文件 URL 放在 `input_files`
- `platform_tool.json` 中的 `input_schema` / `output_schema` 位于 `tool_config` 内部
