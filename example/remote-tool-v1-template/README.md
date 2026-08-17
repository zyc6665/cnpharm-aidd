# Remote Tool v1 Template

这是一个最小可运行的 `aidd.sciminer/remote-tool.v1` 远端服务参考实现。模型服务方可以复制本目录，把 `service.py` 中的 demo 逻辑替换为真实模型推理逻辑。

## 运行

```bash
pip install -r requirements.txt
uvicorn service:create_app --factory --host 0.0.0.0 --port 8000
```

平台管理员注册时填写服务根 URL，例如：

```text
http://remote-tool-demo:8000
```

平台会自动访问：

```text
GET /.well-known/sciminer-tool.json
```

## 端点

- `GET /.well-known/sciminer-tool.json`：返回 Remote Tool v1 manifest。
- `GET /health`：健康检查。
- `GET /examples`：返回 smoke test 样例。
- `POST /invoke`：创建远端异步任务。
- `GET /runs/{remote_run_id}`：查询任务状态。
- `GET /runs/{remote_run_id}/logs`：查询任务日志。
- `GET /runs/{remote_run_id}/artifacts`：返回 `aidd.sciminer/result.v2`。
- `POST /runs/{remote_run_id}/cancel`：取消远端任务。

## 接入真实模型时需要替换的部分

1. `MANIFEST.metadata`：改成真实模型的 slug、名称和版本。
2. `MANIFEST.artifacts`：声明标准 Artifact 输入/输出槽。
3. `MANIFEST.parameters_schema`：声明普通 JSON 参数。
4. `/invoke`：把请求入队到真实模型任务系统。
5. `/runs/{remote_run_id}`、`/logs`、`/cancel`：接入真实任务状态、日志和终止逻辑。
6. `/artifacts` 和文件下载端点：返回标准 `result.v2`，并提供可由平台下载的输出文件 URL。

## 本地测试

```bash
pytest tests/test_remote_tool_v1_contract.py
```

这个模板不包含认证逻辑。第一版假设远端服务部署在可信内网，由平台侧统一控制访问权限。
