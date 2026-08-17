# Remote Tool v1 自注册服务编写指南

Remote Tool v1 用于把内部自托管模型服务注册为平台工具。管理员只需要在前端填写服务根 URL 和分类，平台会读取固定 manifest、创建草稿版本，并可自动创建 smoke test 任务。

## 服务入口

远端服务必须在服务根 URL 下提供固定发现端点：

```text
GET /.well-known/sciminer-tool.json
```

manifest 中的所有 endpoint 都必须是同服务相对路径，例如 `/invoke`、`/runs/{remote_run_id}`。v1 不支持任意请求映射，也不支持远端认证；服务应部署在平台可信内网中。

## 最小 Manifest

```json
{
  "api_version": "aidd.sciminer/remote-tool.v1",
  "kind": "RemoteTool",
  "metadata": {
    "slug": "lvpocket-api",
    "name": "LVpocket API",
    "version": "1.0.0",
    "description": "Predict ligand binding pockets"
  },
  "artifacts": {
    "inputs": [
      {"name": "protein", "type": "protein_structure@1", "required": true}
    ],
    "outputs": [
      {"name": "pocket", "type": "binding_pocket@1", "cardinality": "one", "required": true}
    ]
  },
  "parameters_schema": {
    "type": "object",
    "properties": {"threshold": {"type": "number"}},
    "additionalProperties": false
  },
  "endpoints": {
    "invoke": "/invoke",
    "status": "/runs/{remote_run_id}",
    "logs": "/runs/{remote_run_id}/logs",
    "cancel": "/runs/{remote_run_id}/cancel",
    "artifacts": "/runs/{remote_run_id}/artifacts",
    "examples": "/examples",
    "health": "/health"
  },
  "capabilities": {"async": true, "logs": true, "cancel": true, "progress": true}
}
```

## Invoke Envelope

平台调用 `POST /invoke`，请求体固定为：

```json
{
  "request_id": "uuid",
  "task": {"id": "task-id", "tool_slug": "lvpocket-api", "tool_version": "1.0.0"},
  "inputs": {
    "protein": {
      "artifact_version_id": "artifact-version-id",
      "type": "protein_structure@1",
      "files": {
        "structure_file": {
          "url": "https://platform.example.com/api/v1/files/file-id/download?token=...",
          "filename": "protein.pdb",
          "sha256": "64-hex-sha256",
          "content_type": "chemical/x-pdb"
        }
      },
      "metadata": {}
    }
  },
  "parameters": {"threshold": 0.5},
  "context": {"project_id": "project-id", "user_id": "user-id"}
}
```

远端服务应通过 `files.*.url` 拉取输入文件。平台生成的下载 token 绑定单个 `file_id + task_id`，并短期有效。部署时要设置 `PUBLIC_API_BASE_URL`，确保远端服务能访问这些下载 URL。

## 异步任务协议

- `POST /invoke` 返回 `{"remote_run_id":"run-1","status":"queued"}`。
- `GET /runs/{remote_run_id}` 返回 `queued | running | success | failure | canceled`，可带 `phase`、`progress`、`message`、`error`。
- `GET /runs/{remote_run_id}/logs` 返回增量日志，建议支持 `cursor`。
- `POST /runs/{remote_run_id}/cancel` 终止远端任务。
- `GET /runs/{remote_run_id}/artifacts` 在成功后返回 `aidd.sciminer/result.v2`。

## 输出要求

远端结果必须是平台标准 `result.v2`。示例：

```json
{
  "result_version": "aidd.sciminer/result.v2",
  "artifacts": {
    "pocket": {
      "name": "Top pocket",
      "type": "binding_pocket@1",
      "files": {
        "residue_pocket_pdb": {
          "path": "artifacts/pocket/residue.pdb",
          "url": "/runs/run-1/files/residue.pdb",
          "sha256": "64-hex-sha256",
          "content_type": "chemical/x-pdb"
        }
      },
      "metadata": {}
    }
  },
  "relations": []
}
```

平台会下载 `url` 指向的输出文件、校验 `sha256`、复制到平台存储，并根据 manifest 的 `artifacts.outputs` 持久化标准 ArtifactVersion。

## Smoke Example

`GET /examples` 或 manifest 内的 `examples` 应至少提供一个可运行样例。发布工具前必须有成功且 manifest hash 匹配的 smoke test。

```json
{
  "examples": [
    {
      "name": "default",
      "smoke": true,
      "parameters": {"threshold": 0.5},
      "input_artifacts": {
        "protein": {
          "type": "protein_structure@1",
          "metadata": {"chain_ids": ["A"]},
          "files": {
            "structure_file": {
              "filename": "protein.pdb",
              "content_type": "chemical/x-pdb",
              "url": "/examples/default/protein.pdb",
              "sha256": "64-hex-sha256"
            }
          }
        }
      }
    }
  ]
}
```

样例文件可以提供相对 URL、绝对 URL，或小文件 inline `content`。平台注册 smoke test 时会把样例文件复制进平台文件存储，再通过同一套远端执行器进行测试。
